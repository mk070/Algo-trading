import os
import sys
import json
import time
import requests
import re
from datetime import datetime
from dotenv import dotenv_values

sys.path.insert(0, os.path.abspath("backend"))

env = dotenv_values(".env")
GEMINI_API_KEY = env.get("GEMINI_API_KEY")
NVIDIA_API_KEY = env.get("NVIDIA_API_KEY")

DECISION_CASES = [
    {
        "case_id": "CASE_01_CONTRADICTORY_EARNINGS",
        "symbol": "TITAN",
        "company_name": "Titan Company Limited",
        "market_regime": "BULLISH (Nifty 50 > 50 EMA & > 200 SMA)",
        "technical_setup": {
            "pattern": "VCP_BREAKOUT",
            "trigger_price": 3450.0,
            "stop_loss": 3320.0,
            "risk_pct": 3.77,
            "trend_template_pass": True,
            "volume_pace_ratio": 1.65,
            "proximity_to_52w_high": "-4.2%"
        },
        "fundamentals": {
            "pe_ratio": 78.4,
            "industry_pe": 45.0,
            "roe": 28.5,
            "debt_to_equity": 0.42,
            "promoter_holding": 52.9
        },
        "news_analyst_output": {
            "headline": "Titan Q2 Net Profit Jumps 23% on Jewellery Demand; Gold Import Duty Cuts Lead to Heavy Inventory Losses of Rs 290 Cr",
            "event_category": "QUARTERLY_RESULTS",
            "sentiment": "MIXED",
            "materiality": "HIGH",
            "verified_facts": "Standalone net profit rose 23% to Rs 940 Cr. Gross jewellery sales grew 18%. However, custom duty reduction on gold forced a one-off inventory loss provision of Rs 290 Cr impacting operating margins.",
            "unverified_claims": "Management confident that Q3 festive demand will erase inventory markdowns completely."
        },
        "invalidation_triggers": "Operating margin contraction below 9.5% or breakdown below 3320.",
        "expected_ground_truth": "MONITOR",
        "test_focus": "Model must recognize the severe contradictory impact of the Rs 290 Cr gold inventory loss despite positive headline profit."
    },
    {
        "case_id": "CASE_02_SEBI_RED_FLAG",
        "symbol": "ADANIENT",
        "company_name": "Adani Enterprises Limited",
        "market_regime": "WEAK (Nifty 50 < 50 EMA)",
        "technical_setup": {
            "pattern": "BREAKOUT",
            "trigger_price": 3120.0,
            "stop_loss": 2980.0,
            "risk_pct": 4.48,
            "trend_template_pass": True,
            "volume_pace_ratio": 2.1,
            "proximity_to_52w_high": "-2.1%"
        },
        "fundamentals": {
            "pe_ratio": 95.2,
            "industry_pe": 28.0,
            "roe": 9.4,
            "debt_to_equity": 2.15,
            "promoter_holding": 74.7
        },
        "news_analyst_output": {
            "headline": "SEBI Issues Show-Cause Notice Regarding Related-Party Compliance Disclosures; Adani Denies All Allegations",
            "event_category": "REGULATORY_LITIGATION",
            "sentiment": "NEGATIVE",
            "materiality": "HIGH",
            "verified_facts": "Capital market regulator SEBI served show-cause notices for undisclosed related-party transactions in overseas subsidiaries.",
            "unverified_claims": "Company claims full regulatory compliance and no adverse financial impact."
        },
        "invalidation_triggers": "Regulatory probe expansion or Weak market regime.",
        "expected_ground_truth": "REJECT",
        "test_focus": "Model must decisively REJECT candidate due to high-severity regulatory risk (RED) and Weak market regime, ignoring technical chart setup."
    },
    {
        "case_id": "CASE_03_CLEAN_DEFENCE_ORDER_WIN",
        "symbol": "BEL",
        "company_name": "Bharat Electronics Limited",
        "market_regime": "BULLISH (Nifty 50 > 50 EMA & > 200 SMA)",
        "technical_setup": {
            "pattern": "VCP_BREAKOUT",
            "trigger_price": 315.0,
            "stop_loss": 298.0,
            "risk_pct": 5.4,
            "trend_template_pass": True,
            "volume_pace_ratio": 1.85,
            "proximity_to_52w_high": "-1.5%"
        },
        "fundamentals": {
            "pe_ratio": 42.0,
            "industry_pe": 40.0,
            "roe": 26.2,
            "debt_to_equity": 0.0,
            "order_book": "Rs 74,500 Cr (3.8x FY26 Revenue)"
        },
        "news_analyst_output": {
            "headline": "BEL Secures Major Export & Domestic Radar Orders Worth Rs 1,150 Crore from MoD",
            "event_category": "ORDER_WIN",
            "sentiment": "POSITIVE",
            "materiality": "HIGH",
            "verified_facts": "Ministry of Defence contract signed for indigenous fire-control radars and EW systems. Execution horizon 24 months. Advance payment 15% guaranteed.",
            "unverified_claims": "None"
        },
        "invalidation_triggers": "Breakdown below 298.0 structural pivot.",
        "expected_ground_truth": "WATCH",
        "test_focus": "Model must select WATCH (high priority research) based on zero-debt balance sheet, strong order book, confirmed contract, and bullish regime alignment."
    },
    {
        "case_id": "CASE_04_UNVERIFIED_RUMOUR_PUMP",
        "symbol": "TATASTEEL",
        "company_name": "Tata Steel Limited",
        "market_regime": "BULLISH (Nifty 50 > 50 EMA)",
        "technical_setup": {
            "pattern": "PULLBACK",
            "trigger_price": 162.0,
            "stop_loss": 154.0,
            "risk_pct": 4.93,
            "trend_template_pass": False,
            "volume_pace_ratio": 0.85,
            "proximity_to_52w_high": "-18.5%"
        },
        "fundamentals": {
            "pe_ratio": 38.5,
            "industry_pe": 16.0,
            "roe": 6.8,
            "debt_to_equity": 1.1,
            "uk_operations": "Ongoing restructuring losses at Port Talbot"
        },
        "news_analyst_output": {
            "headline": "Social Media Speculation Claims UK Government Ready to Double Port Talbot Subsidies to GBP 1 Billion",
            "event_category": "RUMOUR_UNVERIFIED",
            "sentiment": "UNCERTAIN",
            "materiality": "LOW",
            "verified_facts": "No official disclosure from Tata Steel or UK Department for Business and Trade.",
            "unverified_claims": "WhatsApp and Telegram channels circulating unsourced subsidy doubling."
        },
        "invalidation_triggers": "Trend template failure (below 200 SMA) and unverified rumor source.",
        "expected_ground_truth": "REJECT",
        "test_focus": "Model must reject unverified market rumors and recognize the trend template failure (fails Minervini criteria)."
    },
    {
        "case_id": "CASE_05_ROUTINE_ADMINISTRATIVE_NOISE",
        "symbol": "INFY",
        "company_name": "Infosys Limited",
        "market_regime": "BULLISH (Nifty 50 > 50 EMA)",
        "technical_setup": {
            "pattern": "NO_SETUP",
            "trigger_price": 1920.0,
            "stop_loss": 1820.0,
            "risk_pct": 5.2,
            "trend_template_pass": True,
            "volume_pace_ratio": 0.65,
            "proximity_to_52w_high": "-8.0%"
        },
        "fundamentals": {
            "pe_ratio": 26.5,
            "industry_pe": 28.0,
            "roe": 31.0,
            "debt_to_equity": 0.05
        },
        "news_analyst_output": {
            "headline": "Infosys Informs Stock Exchanges of Trading Window Closure for Q3 Financial Results",
            "event_category": "ROUTINE_IMMATERIAL",
            "sentiment": "NEUTRAL",
            "materiality": "LOW",
            "verified_facts": "Routine quarterly compliance disclosure under SEBI PIT regulations closing insider trading window until 48 hours post results announcement.",
            "unverified_claims": "None"
        },
        "invalidation_triggers": "Absence of active technical breakout pivot.",
        "expected_ground_truth": "MONITOR",
        "test_focus": "Model must not overreact to routine compliance filings, separating administrative noise from fundamental catalysts while noting lack of technical trigger."
    }
]

SYSTEM_PROMPT_DECISION = """You are a disciplined senior quantitative swing-trading research judge for Indian equities.
Your objective is to prioritize research candidates into one of three strict research statuses:
1. WATCH: Highest research priority. Clean structural setup, strong fundamental/catalyst alignment, bullish regime, zero disqualifying risks.
2. MONITOR: Secondary priority. Constructive setup or high-quality business, but contains pending uncertainties, contradictory data, or incomplete technical confirmation.
3. REJECT: Disqualified. Serious red flags (fraud, SEBI investigation, auditor resignation), weak market regime, trend template failure, or unverified rumors.

Evaluation Rules:
- Separate verified facts from speculative assumptions.
- Separate technical setup from fundamental business impact.
- Recognize contradictory evidence (e.g. inventory write-downs offsetting headline revenue).
- Immediately discard rumors and unverified channel checks.
- Return ONLY a valid JSON object matching the requested schema."""

SCHEMA_DECISION = """{
  "case_id": "...",
  "symbol": "...",
  "research_decision": "WATCH | MONITOR | REJECT",
  "confidence": 0.0 to 1.0,
  "contradiction_identified": true | false,
  "contradiction_details": "...",
  "missing_data_identified": true | false,
  "missing_data_details": "...",
  "regime_and_technical_alignment": "ALIGNED | CONFLICTING | DISQUALIFIED",
  "fundamental_soundness": "SOUND | MIXED | IMPAIRED",
  "final_reasoning": "Clear 2-3 sentence justification explaining the priority ranking."
}"""

def run_decision_benchmark():
    print("Executing Final Research Decision Comparison across reasoning models...", flush=True)
    models = [
        ("gemini-3.1-flash-lite", "google"),
        ("nvidia/nemotron-3-ultra-550b-a55b", "nvidia"),
        ("nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia")
    ]
    
    results = []
    
    for case in DECISION_CASES:
        cid = case["case_id"]
        sym = case["symbol"]
        print(f"\nEvaluating Case {cid} ({sym})...", flush=True)
        
        prompt_body = f"""CASE DOSSIER:
Symbol: {sym} ({case['company_name']})
Market Regime: {case['market_regime']}
Technical Setup: {json.dumps(case['technical_setup'], indent=2)}
Fundamentals: {json.dumps(case['fundamentals'], indent=2)}
News Intelligence Output: {json.dumps(case['news_analyst_output'], indent=2)}
Key Invalidation Triggers: {case['invalidation_triggers']}

Output Schema:
{SCHEMA_DECISION}"""

        for mid, provider in models:
            t0 = time.time()
            parsed = None
            raw_text = ""
            error = None
            
            if provider == "google":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mid}:generateContent?key={GEMINI_API_KEY}"
                payload = {
                    "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT_DECISION}\n\n{prompt_body}"}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0, "maxOutputTokens": 1500}
                }
                try:
                    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
                    if resp.status_code == 200:
                        cand = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        raw_text = cand
                        parsed = json.loads(re.sub(r"```json\s*", "", re.sub(r"```\s*", "", cand)).strip())
                    else:
                        error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                except Exception as e:
                    error = str(e)
            else:
                url = "https://integrate.api.nvidia.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": mid,
                    "messages": [
                        {"role": "system", "content": f"{SYSTEM_PROMPT_DECISION}\n\nKeep reasoning concise."},
                        {"role": "user", "content": f"Analyze and return valid JSON:\n\n{prompt_body}"}
                    ],
                    "max_tokens": 2048,
                    "temperature": 0.0
                }
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=80)
                    if resp.status_code == 200:
                        msg = resp.json().get("choices", [{}])[0].get("message", {})
                        raw_text = msg.get("content") or ""
                        clean = re.sub(r"```json\s*", "", re.sub(r"```\s*", "", raw_text)).strip()
                        m = re.search(r"(\{.*\})", clean, re.DOTALL)
                        parsed = json.loads(m.group(1)) if m else json.loads(clean)
                    else:
                        error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                except Exception as e:
                    error = str(e)
                    
            latency = time.time() - t0
            decision = parsed.get("research_decision") if parsed else "FAILED"
            matched_gt = decision == case["expected_ground_truth"]
            print(f"  [{mid}] Decision: {decision} (Ground Truth: {case['expected_ground_truth']}, Match: {matched_gt}) in {latency:.2f}s", flush=True)
            
            results.append({
                "case_id": cid,
                "symbol": sym,
                "model_id": mid,
                "expected_ground_truth": case["expected_ground_truth"],
                "decision": decision,
                "matched_ground_truth": matched_gt,
                "contradiction_identified": parsed.get("contradiction_identified") if parsed else None,
                "missing_data_identified": parsed.get("missing_data_identified") if parsed else None,
                "final_reasoning": parsed.get("final_reasoning") if parsed else raw_text[:200],
                "latency_sec": round(latency, 2),
                "error": error
            })
            time.sleep(1.5)
            
    out_path = "research/ai_benchmark/decision_benchmark_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nFinal Research Decision benchmark complete! Saved to {out_path}", flush=True)

if __name__ == "__main__":
    run_decision_benchmark()
