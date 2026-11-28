import os
import sys
import json
import time
import base64
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from dotenv import dotenv_values

sys.path.insert(0, os.path.abspath("backend"))

env = dotenv_values(".env")
GEMINI_API_KEY = env.get("GEMINI_API_KEY")
NVIDIA_API_KEY = env.get("NVIDIA_API_KEY")

IMAGE_PATH = "research/ai_benchmark/nse_announcement_sample.png"

def generate_sample_announcement_image():
    # Create a 1000x1200 white canvas representing an official exchange filing
    width, height = 1000, 1200
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Try using default font or standard font
    try:
        font_header = ImageFont.truetype("arial.ttf", 26)
        font_sub = ImageFont.truetype("arial.ttf", 20)
        font_body = ImageFont.truetype("arial.ttf", 16)
        font_bold = ImageFont.truetype("arialbd.ttf", 18)
    except Exception:
        font_header = ImageFont.load_default()
        font_sub = font_header
        font_body = font_header
        font_bold = font_header

    # Header section
    draw.rectangle([(40, 40), (960, 120)], fill=(245, 247, 250), outline=(200, 205, 215), width=2)
    draw.text((60, 55), "NATIONAL STOCK EXCHANGE OF INDIA LIMITED", fill=(20, 35, 75), font=font_header)
    draw.text((60, 90), "CORPORATE FILING & STATUTORY DISCLOSURE - REGULATION 30 & 33 SEBI (LODR)", fill=(80, 90, 110), font=font_sub)

    # Metadata table
    draw.line([(40, 140), (960, 140)], fill=(200, 200, 200), width=1)
    draw.text((50, 155), "Company Name: Infosys Limited", fill=(0, 0, 0), font=font_bold)
    draw.text((550, 155), "NSE Symbol: INFY | BSE: 500209", fill=(0, 0, 0), font=font_bold)
    draw.text((50, 185), "Filing Date: October 17, 2026", fill=(50, 50, 50), font=font_body)
    draw.text((550, 185), "ISIN: INE009A01021", fill=(50, 50, 50), font=font_body)
    draw.line([(40, 215), (960, 215)], fill=(200, 200, 200), width=1)

    # Subject line
    draw.text((50, 235), "SUBJECT: OUTCOME OF BOARD MEETING - Q2 FINANCIAL RESULTS, DIVIDEND & GUIDANCE", fill=(180, 30, 30), font=font_bold)

    # Paragraph text
    body_text = """Dear Sir / Madam,

We wish to inform you that the Board of Directors of Infosys Limited at its meeting held today, October 17, 2026,
has approved the Unaudited Standalone and Consolidated Financial Results for the quarter and half-year ended
September 30, 2026.

Key Financial Highlights (Consolidated - Ind AS):
1. Revenue from Operations stood at Rs 40,986 Crore, reflecting a Year-on-Year growth of 5.1% (Q2 FY25: Rs 38,994 Cr).
2. Operating Profit (EBIT) was Rs 8,648 Crore, with Operating Margin expanding to 21.1%.
3. Consolidated Net Profit (Profit After Tax) stood at Rs 6,506 Crore, an increase of 4.7% YoY (Q2 FY25: Rs 6,212 Cr).
4. Free Cash Flow generated during the quarter was robust at USD 1,026 Million (Rs 8,550 Crore).

Interim Dividend Announcement:
The Board declared an Interim Dividend of Rs 21.00 per equity share of face value of Rs 5.00 each.
The Record Date for the purpose of payment of the Interim Dividend has been fixed as October 29, 2026.
The dividend will be paid on November 08, 2026.

Guidance Revision for FY 2026-27:
The company has revised its FY27 revenue growth guidance upwards to 3.75% - 4.50% in constant currency terms
(previously guided at 3.00% - 4.00%). Operating margin guidance is maintained at 20.0% - 22.0%.

This is for your information and records.

Yours faithfully,
For Infosys Limited
Sd/-
Company Secretary & Compliance Officer"""

    y_pos = 280
    for line in body_text.split("\n"):
        draw.text((50, y_pos), line, fill=(30, 30, 30), font=font_body)
        y_pos += 26

    # Bottom border
    draw.rectangle([(40, 1130), (960, 1170)], fill=(240, 240, 240))
    draw.text((60, 1142), "NSE Official Verification Hash: 9f8e7d6c5b4a3210e - Clean Primary Source Document", fill=(100, 100, 100), font=font_body)

    os.makedirs(os.path.dirname(IMAGE_PATH), exist_ok=True)
    img.save(IMAGE_PATH)
    print(f"Generated official corporate announcement document image at {IMAGE_PATH}")
    return IMAGE_PATH

MULTIMODAL_SCHEMA = """Return ONLY a valid JSON object with these exact keys:
{
  "company_name": "Full legal name extracted from document",
  "canonical_symbol": "Exchange scrip code/symbol",
  "event_category": "QUARTERLY_RESULTS | DIVIDEND_BUYBACK | GUIDANCE_AND_TARGETS | MIXED",
  "revenue_inr_crore": 40986,
  "net_profit_inr_crore": 6506,
  "operating_margin_pct": 21.1,
  "interim_dividend_per_share": 21.0,
  "record_date": "YYYY-MM-DD",
  "guidance_revision": "Summary of revenue guidance change",
  "materiality": "HIGH | MEDIUM | LOW",
  "sentiment": "POSITIVE | NEGATIVE | NEUTRAL | MIXED",
  "verified_citations": ["Direct quotes of numbers from document"]
}"""

def run_multimodal_benchmark():
    print("Executing Multimodal Document/PDF Benchmark...", flush=True)
    img_path = generate_sample_announcement_image()
    
    with open(img_path, "rb") as f:
        img_bytes = f.read()
    b64_image = base64.b64encode(img_bytes).decode("utf-8")
    
    results = {}
    
    # 1. Gemini 3.1 Flash-Lite Multimodal
    print("\n1. Testing Gemini 3.1 Flash-Lite on document image...", flush=True)
    t0 = time.time()
    url_g = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
    payload_g = {
        "contents": [
            {
                "parts": [
                    {"text": f"You are analyzing an official NSE corporate announcement image. Extract all factual numbers and corporate actions.\n\n{MULTIMODAL_SCHEMA}"},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": b64_image
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0,
            "maxOutputTokens": 1500
        }
    }
    try:
        resp_g = requests.post(url_g, json=payload_g, headers={"Content-Type": "application/json"}, timeout=45)
        lat_g = time.time() - t0
        print(f"Gemini 3.1 Flash-Lite status: {resp_g.status_code} ({lat_g:.2f}s)")
        if resp_g.status_code == 200:
            cand = resp_g.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            results["gemini-3.1-flash-lite"] = {
                "success": True,
                "latency_sec": round(lat_g, 2),
                "parsed_json": json.loads(cand),
                "error": None
            }
        else:
            results["gemini-3.1-flash-lite"] = {
                "success": False,
                "latency_sec": round(lat_g, 2),
                "parsed_json": None,
                "error": resp_g.text[:200]
            }
    except Exception as e:
        results["gemini-3.1-flash-lite"] = {
            "success": False,
            "latency_sec": round(time.time() - t0, 2),
            "parsed_json": None,
            "error": str(e)
        }
        
    # 2. NVIDIA Nemotron 3.5 Super VL
    print("\n2. Testing NVIDIA Nemotron 3.5 Super VL on document image...", flush=True)
    t0 = time.time()
    url_nv = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers_nv = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload_nv = {
        "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"You are analyzing an official NSE corporate announcement image. Extract all factual numbers and corporate actions.\n\n{MULTIMODAL_SCHEMA}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 2048,
        "temperature": 0.0
    }
    try:
        resp_nv = requests.post(url_nv, json=payload_nv, headers=headers_nv, timeout=60)
        lat_nv = time.time() - t0
        print(f"Nemotron 3.5 Super VL status: {resp_nv.status_code} ({lat_nv:.2f}s)")
        if resp_nv.status_code == 200:
            msg = resp_nv.json().get("choices", [{}])[0].get("message", {})
            raw_text = msg.get("content") or ""
            # parse json
            import re
            clean = re.sub(r"```json\s*", "", re.sub(r"```\s*", "", raw_text)).strip()
            m = re.search(r"(\{.*\})", clean, re.DOTALL)
            parsed = json.loads(m.group(1)) if m else json.loads(clean)
            results["nvidia/nemotron-3.5-super-vl-120b-a12b"] = {
                "success": True,
                "latency_sec": round(lat_nv, 2),
                "parsed_json": parsed,
                "error": None
            }
        else:
            results["nvidia/nemotron-3.5-super-vl-120b-a12b"] = {
                "success": False,
                "latency_sec": round(lat_nv, 2),
                "parsed_json": None,
                "error": resp_nv.text[:200]
            }
    except Exception as e:
        results["nvidia/nemotron-3.5-super-vl-120b-a12b"] = {
            "success": False,
            "latency_sec": round(time.time() - t0, 2),
            "parsed_json": None,
            "error": str(e)
        }
        
    out_file = "research/ai_benchmark/multimodal_benchmark_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nMultimodal benchmark complete! Saved to {out_file}", flush=True)

if __name__ == "__main__":
    run_multimodal_benchmark()
