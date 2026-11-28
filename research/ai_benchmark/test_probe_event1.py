import requests, json, time, re
from dotenv import dotenv_values

env = dotenv_values(".env")
gemini_key = env.get("GEMINI_API_KEY")
nvidia_key = env.get("NVIDIA_API_KEY")

prompt_text = """Company: Titan Company Limited (TITAN)
Headline: Titan Q2 Net Profit Jumps 23% to Rs 940 Crore on Strong Festive Jewellery Demand
Source: Financial Media
URL: https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol=TITAN
Announcement Text: Titan Company Limited reported a 23% YoY increase in standalone net profit at Rs 940 crore for the second quarter, driven by robust jewellery sales during the festive season. Revenue grew 18% YoY to Rs 11,650 crore. EBITDA margins remained resilient at 11.2%."""

schema = """Return ONLY valid JSON matching this schema:
{"company_name": "...", "canonical_symbol": "...", "event_category": "...", "event_summary": "...", "sentiment": "POSITIVE", "materiality": "HIGH", "potential_business_impact": "...", "potential_stock_impact": "...", "impact_time_horizon": "SHORT_TERM_1_4_WEEKS", "supporting_evidence": "...", "source_urls": ["..."], "uncertainties": ["..."], "missing_information": ["..."], "confidence": 0.9}"""

# Test Gemini 3.1 Flash-Lite
print("Testing Gemini 3.1 Flash-Lite...")
t0 = time.time()
url_g = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={gemini_key}"
resp_g = requests.post(
    url_g,
    json={
        "contents": [{"parts": [{"text": f"{schema}\n\nInput:\n{prompt_text}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0}
    },
    timeout=45
)
print(f"Gemini: status={resp_g.status_code}, time={time.time()-t0:.2f}s")
if resp_g.status_code == 200:
    print("Gemini json:", resp_g.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")[:120])

# Test Nemotron 3.5 Super VL
print("\nTesting Nemotron 3.5 Super VL...")
t0 = time.time()
url_nv = "https://integrate.api.nvidia.com/v1/chat/completions"
headers_nv = {"Authorization": f"Bearer {nvidia_key}", "Content-Type": "application/json"}
payload_nv2 = {
    "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "messages": [
        {"role": "system", "content": "You are a financial analyst. Keep reasoning brief and concise. Return ONLY valid JSON matching the schema."},
        {"role": "user", "content": f"{schema}\n\nInput:\n{prompt_text}"}
    ],
    "max_tokens": 2048,
    "temperature": 0.0
}
resp_nv2 = requests.post(url_nv, json=payload_nv2, headers=headers_nv, timeout=60)
print(f"Nemotron 3.5: status={resp_nv2.status_code}, time={time.time()-t0:.2f}s")
if resp_nv2.status_code == 200:
    msg = resp_nv2.json().get("choices", [{}])[0].get("message", {})
    print("Nemotron 3.5 content:", (msg.get("content") or "")[:150])
    print("Nemotron 3.5 reasoning tokens:", resp_nv2.json().get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens"))

# Test Nemotron 3 Ultra
print("\nTesting Nemotron 3 Ultra...")
t0 = time.time()
payload_nv1 = {
    "model": "nvidia/nemotron-3-ultra-550b-a55b",
    "messages": [
        {"role": "system", "content": "You are a financial analyst. Keep reasoning brief and concise. Return ONLY valid JSON matching the schema."},
        {"role": "user", "content": f"{schema}\n\nInput:\n{prompt_text}"}
    ],
    "max_tokens": 2048,
    "temperature": 0.0
}
resp_nv1 = requests.post(url_nv, json=payload_nv1, headers=headers_nv, timeout=80)
print(f"Nemotron 3 Ultra: status={resp_nv1.status_code}, time={time.time()-t0:.2f}s")
if resp_nv1.status_code == 200:
    msg = resp_nv1.json().get("choices", [{}])[0].get("message", {})
    print("Nemotron 3 Ultra content:", (msg.get("content") or "")[:150])
    print("Nemotron 3 Ultra reasoning tokens:", resp_nv1.json().get("usage", {}).get("completion_tokens_details", {}).get("reasoning_tokens"))
