import os
import sys
import json
import time
import requests
from dotenv import dotenv_values

env = dotenv_values(".env")
gemini_key = env.get("GEMINI_API_KEY")
nvidia_key = env.get("NVIDIA_API_KEY")

print(f"Gemini Key Present: {bool(gemini_key)}")
print(f"NVIDIA Key Present: {bool(nvidia_key)}")

models = [
    ("gemini", "gemini-4-hydrogen"),
    ("gemini", "gemini-3.8-flash"),
    ("gemini", "gemini-3.1-flash-lite"),
    ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b"),
    ("nvidia", "nvidia/nemotron-3.5-super-vl-120b-a12b")
]

for provider, model_id in models:
    print(f"\n==========================================")
    print(f"Testing {provider}: {model_id}")
    print(f"==========================================")
    start_time = time.time()
    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={gemini_key}"
        payload = {
            "contents": [{
                "parts": [{"text": "Analyze: 'Tata Motors reports 20% jump in EV sales for Q2'. Return JSON with keys: company_name, sentiment."}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.0,
                "maxOutputTokens": 200
            }
        }
        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
            latency = time.time() - start_time
            print(f"HTTP Status: {resp.status_code} (Latency: {latency:.2f}s)")
            if resp.status_code == 200:
                data = resp.json()
                cand = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                print(f"Response: {cand}")
                print(f"Usage: {data.get('usageMetadata')}")
            else:
                print(f"Error: {resp.text[:300]}")
        except Exception as e:
            print(f"Exception: {e}")

    elif provider == "nvidia":
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {nvidia_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": "You are a financial analyst. You must return ONLY a valid JSON object with keys: company_name, sentiment."},
                {"role": "user", "content": "Analyze: 'Tata Motors reports 20% jump in EV sales for Q2'."}
            ],
            "max_tokens": 1024,
            "temperature": 0.0
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            latency = time.time() - start_time
            print(f"HTTP Status: {resp.status_code} (Latency: {latency:.2f}s)")
            if resp.status_code == 200:
                data = resp.json()
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                print(f"Content: {msg.get('content')}")
                print(f"Reasoning snippet: {(msg.get('reasoning_content') or '')[:120]}...")
                print(f"Usage: {data.get('usage')}")
            else:
                print(f"Error: {resp.text[:300]}")
        except Exception as e:
            print(f"Exception: {e}")

    time.sleep(1)
