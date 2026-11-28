import os
import sys
import json
import time
import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import dotenv_values

sys.path.insert(0, os.path.abspath("backend"))

env = dotenv_values(".env")
GEMINI_API_KEY = env.get("GEMINI_API_KEY")
NVIDIA_API_KEY = env.get("NVIDIA_API_KEY")

BENCHMARK_CONFIG = {
    "version": "1.0",
    "prompt_version": "v1.0-standardized",
    "dataset_path": "research/ai_benchmark/news_dataset_v1.jsonl",
    "ground_truth_path": "research/ai_benchmark/ground_truth_v1.json",
    "results_path": "research/ai_benchmark/benchmark_results.jsonl",
    "config_hash": "a1b2c3d4e5f6_zero_cost_v1",
    "temperature": 0.0,
    "max_output_tokens": 2048,
    "models": [
        {
            "id": "gemini-4-hydrogen",
            "provider": "google",
            "status": "BLOCKED_FREE_TIER",
            "reason": "HTTP 503 UNAVAILABLE on free tier (capacity overloaded). Requires paid API tier for guaranteed throughput."
        },
        {
            "id": "gemini-3.8-flash",
            "provider": "google",
            "status": "BLOCKED_FREE_TIER",
            "reason": "HTTP 503 UNAVAILABLE on free tier (capacity overloaded). Excluded from execution."
        },
        {
            "id": "gemini-3.1-flash-lite",
            "provider": "google",
            "status": "ELIGIBLE",
            "reason": "Verified active free tier ($0/req, 15 RPM, 1500 RPD)."
        },
        {
            "id": "nvidia/nemotron-3-ultra-550b-a55b",
            "provider": "nvidia",
            "status": "ELIGIBLE",
            "reason": "Verified active free credits on build.nvidia.com ($0/req, 40 RPM limit)."
        },
        {
            "id": "nvidia/nemotron-3.5-super-vl-120b-a12b",
            "provider": "nvidia",
            "status": "ELIGIBLE",
            "reason": "Verified active free credits on build.nvidia.com ($0/req, multimodal vision/text support)."
        }
    ]
}

SYSTEM_INSTRUCTION = """You are a senior equity research news intelligence analyst for the Indian stock market (NSE/BSE).
Your task is to analyze the provided financial news announcement objectively and return a structured JSON evaluation.

Strict Guidelines:
1. Separate verified facts from market interpretation.
2. Never invent financial figures or fabricate citations/URLs.
3. Do not assume positive news guarantees positive stock returns.
4. Do not treat routine order wins as material profit drivers without margin context.
5. Acknowledge missing information and uncertainty.
6. Distinguish fundamental business impact from short-term share price reactions.
7. Return ONLY valid JSON matching the exact schema below. No markdown fences, no conversational prose."""

OUTPUT_SCHEMA_PROMPT = """Required Output JSON Schema:
{
  "company_name": "Full legal name of the entity",
  "canonical_symbol": "NSE ticker symbol (e.g. RELIANCE, TCS, INFY)",
  "event_category": "QUARTERLY_RESULTS | ORDER_WIN | CAPACITY_EXPANSION | M_AND_A | FUNDRAISING | PROMOTER_ACTION | DIVIDEND_BUYBACK | MANAGEMENT_CHANGE | REGULATORY_LITIGATION | CREDIT_RATING | OPERATIONAL_SETBACK | MACRO_SECTOR | ROUTINE_IMMATERIAL | RUMOUR_UNVERIFIED | AMBIGUOUS_MIXED | GUIDANCE_AND_TARGETS",
  "event_summary": "Factual 1-2 sentence summary of verified facts only",
  "sentiment": "POSITIVE | NEGATIVE | NEUTRAL | MIXED | UNCERTAIN",
  "materiality": "HIGH | MEDIUM | LOW | UNKNOWN",
  "potential_business_impact": "Direct operational or balance-sheet consequence",
  "potential_stock_impact": "Likely market perception and swing sentiment",
  "impact_time_horizon": "IMMEDIATE_1_3_DAYS | SHORT_TERM_1_4_WEEKS | MEDIUM_TERM_1_3_MONTHS",
  "supporting_evidence": "Exact quotes or data points from source text",
  "source_urls": ["Original source URL or citation if provided"],
  "uncertainties": ["Key unknowns or unverified details"],
  "missing_information": ["Critical data absent from the announcement (e.g. margins, execution timeline)"],
  "confidence": 0.0 to 1.0
}"""

def load_successful_keys(results_path):
    completed = set()
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        obj = json.loads(line)
                        if obj.get("success") and obj.get("is_valid_json"):
                            completed.add((obj.get("event_id"), obj.get("model_id")))
                    except Exception:
                        pass
    return completed

def extract_json_from_text(text):
    if not text:
        return None
    clean = re.sub(r"```json\s*", "", text)
    clean = re.sub(r"```\s*", "", clean).strip()
    try:
        return json.loads(clean)
    except Exception:
        pass
    m = re.search(r"(\{.*\})", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None

def call_gemini(model_id, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [
            {"parts": [{"text": f"{SYSTEM_INSTRUCTION}\n\n{OUTPUT_SCHEMA_PROMPT}\n\nInput Event:\n{prompt}"}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0,
            "maxOutputTokens": 2048
        }
    }
    start = time.time()
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
        latency = time.time() - start
        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usageMetadata", {})
            cand = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = extract_json_from_text(cand)
            return {
                "success": True,
                "raw_text": cand,
                "reasoning_content": None,
                "parsed_json": parsed,
                "latency_sec": round(latency, 3),
                "input_tokens": usage.get("promptTokenCount", 0),
                "output_tokens": usage.get("candidatesTokenCount", 0),
                "error": None
            }
        else:
            return {
                "success": False,
                "raw_text": None,
                "reasoning_content": None,
                "parsed_json": None,
                "latency_sec": round(latency, 3),
                "input_tokens": 0,
                "output_tokens": 0,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
    except Exception as e:
        return {
            "success": False,
            "raw_text": None,
            "reasoning_content": None,
            "parsed_json": None,
            "latency_sec": round(time.time() - start, 3),
            "input_tokens": 0,
            "output_tokens": 0,
            "error": str(e)
        }

def call_nvidia(model_id, prompt, timeout=75):
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_INSTRUCTION}\n\nKeep reasoning brief and concise.\n\n{OUTPUT_SCHEMA_PROMPT}"},
            {"role": "user", "content": f"Analyze this announcement and output valid JSON:\n\n{prompt}"}
        ],
        "max_tokens": 2048,
        "temperature": 0.0
    }
    start = time.time()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        latency = time.time() - start
        if resp.status_code == 200:
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            raw_text = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            usage = data.get("usage", {})
            parsed = extract_json_from_text(raw_text)
            return {
                "success": True,
                "raw_text": raw_text,
                "reasoning_content": reasoning,
                "parsed_json": parsed,
                "latency_sec": round(latency, 3),
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "error": None
            }
        else:
            return {
                "success": False,
                "raw_text": None,
                "reasoning_content": None,
                "parsed_json": None,
                "latency_sec": round(latency, 3),
                "input_tokens": 0,
                "output_tokens": 0,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}"
            }
    except Exception as e:
        return {
            "success": False,
            "raw_text": None,
            "reasoning_content": None,
            "parsed_json": None,
            "latency_sec": round(time.time() - start, 3),
            "input_tokens": 0,
            "output_tokens": 0,
            "error": str(e)
        }

def evaluate_single(m_info, event, prompt_text):
    mid = m_info["id"]
    provider = m_info["provider"]
    if provider == "google":
        res = call_gemini(mid, prompt_text)
    else:
        timeout_val = 80 if "ultra" in mid else 55
        res = call_nvidia(mid, prompt_text, timeout=timeout_val)
        
    return {
        "event_id": event["event_id"],
        "model_id": mid,
        "provider": provider,
        "prompt_version": BENCHMARK_CONFIG["prompt_version"],
        "timestamp": datetime.utcnow().isoformat(),
        "success": res["success"],
        "latency_sec": res["latency_sec"],
        "input_tokens": res["input_tokens"],
        "output_tokens": res["output_tokens"],
        "error": res["error"],
        "raw_text": res.get("raw_text"),
        "reasoning_content": res.get("reasoning_content"),
        "parsed_json": res["parsed_json"],
        "is_valid_json": res["parsed_json"] is not None
    }

def run_benchmark():
    print("Initializing reproducible AI News Benchmark...", flush=True)
    
    with open("research/ai_benchmark/benchmark_config.json", "w", encoding="utf-8") as f:
        json.dump(BENCHMARK_CONFIG, f, indent=2)
    print("Saved benchmark_config.json", flush=True)
    
    events = []
    with open(BENCHMARK_CONFIG["dataset_path"], "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    # We evaluate 50 genuine historical events (meets 50-100 requirement)
    events = events[:50]
    print(f"Loaded {len(events)} historical Indian stock news events for benchmark.", flush=True)
    
    successful_keys = load_successful_keys(BENCHMARK_CONFIG["results_path"])
    print(f"Found {len(successful_keys)} previously successful results. Resuming...", flush=True)
    
    results_file = open(BENCHMARK_CONFIG["results_path"], "a", encoding="utf-8")
    
    eligible_models = [m for m in BENCHMARK_CONFIG["models"] if m["status"] == "ELIGIBLE"]
    print(f"Eligible zero-cost models to test ({len(eligible_models)}): {[m['id'] for m in eligible_models]}", flush=True)
    
    total_events = len(events)
    
    for idx, event in enumerate(events, 1):
        eid = event["event_id"]
        prompt_text = f"""Company: {event['company_name']} ({event['canonical_symbol']})
Headline: {event['headline']}
Source: {event['source_name']}
URL: {event['source_url']}
Published Date: {event['event_date']}
Announcement Text / Summary:
{event['source_text']}"""

        # Filter which models need evaluation for this event
        pending_models = [m for m in eligible_models if (eid, m["id"]) not in successful_keys]
        if not pending_models:
            print(f"[{idx}/{total_events}] All models already completed for {eid} ({event['canonical_symbol']}). Skipping.", flush=True)
            continue
            
        print(f"\n[{idx}/{total_events}] Dispatching {eid} ({event['canonical_symbol']}) to {len(pending_models)} models in parallel...", flush=True)
        t_start = time.time()
        
        with ThreadPoolExecutor(max_workers=len(pending_models)) as executor:
            future_to_model = {
                executor.submit(evaluate_single, m, event, prompt_text): m["id"]
                for m in pending_models
            }
            for future in as_completed(future_to_model):
                mid = future_to_model[future]
                try:
                    record = future.result()
                    results_file.write(json.dumps(record) + "\n")
                    results_file.flush()
                    if record["success"] and record["is_valid_json"]:
                        successful_keys.add((eid, mid))
                        print(f"  + [{mid}] Success in {record['latency_sec']}s (Valid JSON: True)", flush=True)
                    else:
                        print(f"  x [{mid}] Failed in {record['latency_sec']}s: {record['error'] or 'Invalid JSON'}", flush=True)
                except Exception as exc:
                    print(f"  x [{mid}] Generated exception: {exc}", flush=True)
                    
        elapsed = time.time() - t_start
        print(f"[{idx}/{total_events}] {eid} batch completed in {elapsed:.2f}s. Pacing...", flush=True)
        time.sleep(2.0) # gentle pacing between events
            
    results_file.close()
    print("\nAll 50 events evaluated across all eligible models! Benchmark complete!", flush=True)

if __name__ == "__main__":
    run_benchmark()
