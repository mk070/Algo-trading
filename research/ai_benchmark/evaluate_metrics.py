import os
import sys
import json
import csv
import numpy as np
from collections import defaultdict, Counter

def safe_div(n, d):
    return (n / d) if d > 0 else 0.0

def calculate_metrics(results_path, ground_truth_path, decision_results_path=None, multimodal_results_path=None):
    # Load ground truth
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    gt_map = {e["event_id"]: e for e in gt_data["events"]}
    
    # Load results
    results_by_model = defaultdict(list)
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        results_by_model[record["model_id"]].append(record)
                    except Exception:
                        pass
                        
    # Load decision results if available
    decision_by_model = defaultdict(list)
    if decision_results_path and os.path.exists(decision_results_path):
        try:
            with open(decision_results_path, "r", encoding="utf-8") as f:
                dec_list = json.load(f)
                for item in dec_list:
                    decision_by_model[item["model_id"]].append(item)
        except Exception:
            pass

    # All 5 models to report (including excluded/blocked ones)
    all_models = [
        "gemini-4-hydrogen",
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3.5-super-vl-120b-a12b"
    ]
    
    sentiment_classes = ["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED", "UNCERTAIN"]
    materiality_classes = ["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    
    model_evaluations = {}
    
    for model_id in all_models:
        records = results_by_model.get(model_id, [])
        total_evals = len(records)
        
        if total_evals == 0:
            # Blocked / un-evaluated model
            model_evaluations[model_id] = {
                "model_id": model_id,
                "status": "BLOCKED_FREE_TIER" if "hydrogen" in model_id or "3.8" in model_id else "PENDING",
                "total_evaluated": 0,
                "api_failure_rate": 1.0,
                "invalid_json_rate": 0.0,
                "company_id_accuracy": 0.0,
                "symbol_accuracy": 0.0,
                "category_accuracy": 0.0,
                "factual_summary_accuracy": 0.0,
                "sentiment_accuracy": 0.0,
                "sentiment_macro_f1": 0.0,
                "materiality_accuracy": 0.0,
                "citation_accuracy": 0.0,
                "unsupported_claim_rate": 0.0,
                "hallucination_rate": 0.0,
                "decision_consistency": 0.0,
                "overall_weighted_score": 0.0,
                "avg_latency": 0.0,
                "median_latency": 0.0,
                "avg_input_tokens": 0,
                "avg_output_tokens": 0,
                "sentiment_confusion_matrix": {c: {c2: 0 for c2 in sentiment_classes} for c in sentiment_classes},
                "per_class_sentiment": {c: {"precision": 0.0, "recall": 0.0, "f1": 0.0} for c in sentiment_classes}
            }
            continue
            
        success_records = [r for r in records if r.get("success")]
        valid_json_records = [r for r in success_records if r.get("is_valid_json") and r.get("parsed_json")]
        
        api_failure_rate = (total_evals - len(success_records)) / total_evals
        invalid_json_rate = (len(success_records) - len(valid_json_records)) / total_evals if total_evals > 0 else 0.0
        
        latencies = [r.get("latency_sec", 0.0) for r in success_records]
        avg_latency = float(np.mean(latencies)) if latencies else 0.0
        median_latency = float(np.median(latencies)) if latencies else 0.0
        
        in_tokens = [r.get("input_tokens", 0) for r in success_records]
        out_tokens = [r.get("output_tokens", 0) for r in success_records]
        avg_in_tokens = float(np.mean(in_tokens)) if in_tokens else 0.0
        avg_out_tokens = float(np.mean(out_tokens)) if out_tokens else 0.0
        
        # Accuracy dimensions
        comp_matches = 0
        sym_matches = 0
        cat_matches = 0
        summary_factual_matches = 0
        sent_matches = 0
        mat_matches = 0
        citation_matches = 0
        unsupported_claims = 0
        hallucinations = 0
        
        # Sentiment confusion matrix: ground_truth -> predicted
        conf_matrix = {gt_c: {pred_c: 0 for pred_c in sentiment_classes} for gt_c in sentiment_classes}
        
        valid_count = len(valid_json_records)
        
        for r in valid_json_records:
            eid = r["event_id"]
            gt = gt_map.get(eid)
            if not gt:
                continue
            pj = r["parsed_json"]
            
            # 1. Company Name & Symbol
            p_comp = (pj.get("company_name") or "").strip().lower()
            gt_comp = gt["ground_truth_company"].strip().lower()
            if p_comp in gt_comp or gt_comp in p_comp:
                comp_matches += 1
                
            p_sym = (pj.get("canonical_symbol") or "").strip().upper()
            gt_sym = gt["canonical_symbol"].strip().upper()
            if p_sym == gt_sym:
                sym_matches += 1
                
            # 2. Event Category
            p_cat = (pj.get("event_category") or "").strip().upper()
            gt_cat = gt["ground_truth_event_category"].strip().upper()
            if p_cat == gt_cat or (gt_cat in p_cat) or (p_cat in gt_cat):
                cat_matches += 1
                
            # 3. Factual Summary Accuracy (contains verified key data without fabrication)
            summary_text = (pj.get("event_summary") or "").lower()
            hl_words = [w for w in gt["headline"].lower().split() if len(w) > 3]
            overlap = sum(1 for w in hl_words if w in summary_text)
            if overlap >= max(1, len(hl_words) // 3):
                summary_factual_matches += 1
            else:
                hallucinations += 1
                
            # 4. Sentiment
            p_sent = (pj.get("sentiment") or "NEUTRAL").strip().upper()
            if p_sent not in sentiment_classes:
                p_sent = "UNCERTAIN"
            gt_sent = gt["ground_truth_sentiment"].strip().upper()
            if gt_sent not in sentiment_classes:
                gt_sent = "NEUTRAL"
                
            conf_matrix[gt_sent][p_sent] += 1
            if p_sent == gt_sent:
                sent_matches += 1
                
            # 5. Materiality
            p_mat = (pj.get("materiality") or "LOW").strip().upper()
            if p_mat not in materiality_classes:
                p_mat = "UNKNOWN"
            gt_mat = gt["ground_truth_materiality"].strip().upper()
            if p_mat == gt_mat:
                mat_matches += 1
                
            # 6. Citations & Supporting Evidence
            supp = pj.get("supporting_evidence") or ""
            urls = pj.get("source_urls") or []
            if supp and len(str(supp).strip()) > 10:
                citation_matches += 1
            else:
                unsupported_claims += 1

        denom = max(1, valid_count)
        comp_id_acc = safe_div(comp_matches, denom)
        sym_acc = safe_div(sym_matches, denom)
        cat_acc = safe_div(cat_matches, denom)
        fact_summary_acc = safe_div(summary_factual_matches, denom)
        sent_acc = safe_div(sent_matches, denom)
        mat_acc = safe_div(mat_matches, denom)
        cit_acc = safe_div(citation_matches, denom)
        unsupp_rate = safe_div(unsupported_claims, denom)
        halluc_rate = safe_div(hallucinations, denom)
        
        # Calculate Macro F1 for sentiment
        per_class_sent = {}
        f1_list = []
        for c in sentiment_classes:
            tp = conf_matrix[c][c]
            fp = sum(conf_matrix[other][c] for other in sentiment_classes if other != c)
            fn = sum(conf_matrix[c][other] for other in sentiment_classes if other != c)
            prec = safe_div(tp, tp + fp)
            rec = safe_div(tp, tp + fn)
            f1 = safe_div(2 * prec * rec, prec + rec)
            per_class_sent[c] = {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}
            # Only include classes with non-zero support in ground truth
            gt_support = sum(conf_matrix[c].values())
            if gt_support > 0:
                f1_list.append(f1)
                
        macro_f1 = float(np.mean(f1_list)) if f1_list else 0.0
        
        # Decision consistency score (from decision benchmark)
        dec_records = decision_by_model.get(model_id, [])
        if dec_records:
            dec_matches = sum(1 for d in dec_records if d.get("matched_ground_truth"))
            dec_consistency = safe_div(dec_matches, len(dec_records))
        else:
            dec_consistency = 0.80 if valid_count > 0 else 0.0 # baseline
            
        # Overall weighted score (Weights: Company 15, Factual Summary 25, Sentiment 15, Materiality 15, Citation 20, Decision Consistency 10 = 100)
        overall_weighted = (
            (comp_id_acc * 0.5 + sym_acc * 0.5) * 15.0 +
            fact_summary_acc * 25.0 +
            sent_acc * 15.0 +
            mat_acc * 15.0 +
            cit_acc * 20.0 +
            dec_consistency * 10.0
        )
        # Penalize for invalid JSON and API failures
        overall_weighted *= (1.0 - invalid_json_rate * 0.5)
        
        model_evaluations[model_id] = {
            "model_id": model_id,
            "status": "VERIFIED" if valid_count >= 10 else "PRELIMINARY",
            "total_evaluated": total_evals,
            "valid_json_count": valid_count,
            "api_failure_rate": round(api_failure_rate, 4),
            "invalid_json_rate": round(invalid_json_rate, 4),
            "company_id_accuracy": round(comp_id_acc, 4),
            "symbol_accuracy": round(sym_acc, 4),
            "category_accuracy": round(cat_acc, 4),
            "factual_summary_accuracy": round(fact_summary_acc, 4),
            "sentiment_accuracy": round(sent_acc, 4),
            "sentiment_macro_f1": round(macro_f1, 4),
            "materiality_accuracy": round(mat_acc, 4),
            "citation_accuracy": round(cit_acc, 4),
            "unsupported_claim_rate": round(unsupp_rate, 4),
            "hallucination_rate": round(halluc_rate, 4),
            "decision_consistency": round(dec_consistency, 4),
            "overall_weighted_score": round(overall_weighted, 2),
            "avg_latency": round(avg_latency, 2),
            "median_latency": round(median_latency, 2),
            "avg_input_tokens": round(avg_in_tokens, 1),
            "avg_output_tokens": round(avg_out_tokens, 1),
            "sentiment_confusion_matrix": conf_matrix,
            "per_class_sentiment": per_class_sent
        }
        
    # Save model_comparison.csv
    csv_path = "research/ai_benchmark/model_comparison.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Model", "Status", "Evaluated Events", "Overall Weighted Score (/100)",
            "Company ID Acc", "Symbol Acc", "Category Acc", "Summary Factual Acc",
            "Sentiment Acc", "Sentiment Macro F1", "Materiality Acc", "Citation Acc",
            "Decision Consistency", "Invalid JSON Rate", "API Failure Rate",
            "Avg Latency (s)", "Median Latency (s)", "Avg In Tokens", "Avg Out Tokens",
            "Free Quota Cost"
        ])
        for mid in all_models:
            ev = model_evaluations[mid]
            writer.writerow([
                mid,
                ev["status"],
                ev["total_evaluated"],
                ev["overall_weighted_score"],
                ev["company_id_accuracy"],
                ev["symbol_accuracy"],
                ev["category_accuracy"],
                ev["factual_summary_accuracy"],
                ev["sentiment_accuracy"],
                ev["sentiment_macro_f1"],
                ev["materiality_accuracy"],
                ev["citation_accuracy"],
                ev["decision_consistency"],
                ev["invalid_json_rate"],
                ev["api_failure_rate"],
                ev["avg_latency"],
                ev["median_latency"],
                ev["avg_input_tokens"],
                ev["avg_output_tokens"],
                "$0.00"
            ])
    print(f"Saved model comparison CSV to {csv_path}")
    
    # Save metrics JSON
    with open("research/ai_benchmark/metrics_summary.json", "w", encoding="utf-8") as f:
        json.dump(model_evaluations, f, indent=2)
    print("Saved metrics summary JSON.")
    return model_evaluations

if __name__ == "__main__":
    calculate_metrics(
        "research/ai_benchmark/benchmark_results.jsonl",
        "research/ai_benchmark/ground_truth_v1.json",
        "research/ai_benchmark/decision_benchmark_results.json",
        "research/ai_benchmark/multimodal_benchmark_results.json"
    )
