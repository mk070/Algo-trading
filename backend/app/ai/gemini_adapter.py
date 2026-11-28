"""
Gemini Provider Adapter — gemini-3.1-flash-lite (free tier, zero-cost only)

Verified metadata (2026-11-28):
  - Model ID: gemini-3.1-flash-lite
  - Input token limit: 1,048,576 | Output token limit: 65,536
  - Free tier limits: 15 RPM, 1,500 RPD, 1M TPM
  - Cost: $0 / request on free tier

BLOCKED_FREE_TIER models (do not use):
  - gemini-4-hydrogen  (paid only / HTTP 503 on free tier)
  - gemini-3.8-flash   (paid only / HTTP 503 on free tier)

Security rules:
  - API key read from environment via settings; sent via x-goog-api-key header
    (never in URL query string, never logged, committed, or exposed in errors).
  - User prompts must contain only public market data and permitted filings.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.ai.provider_interface import AIProvider
from app.ai.schemas import AIResponse
from app.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_MODEL_ID = "gemini-3.1-flash-lite"  # Benchmarked free-tier eligible model
_MAX_RETRIES = 2
_BACKOFF_BASE = 2.0  # seconds


class GeminiAdapter(AIProvider):
    """
    Gemini 3.1 Flash-Lite provider adapter.

    Implements bounded retry (max 2) with exponential backoff for 429/503.
    Hard timeout: 45 s.
    Structured JSON output via responseMimeType application/json.
    Records token usage and latency.
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = getattr(settings, "gemini_api_key", None)
        if not self._api_key:
            import os
            self._api_key = os.environ.get("GEMINI_API_KEY")

    @property
    def provider_name(self) -> str:
        return "google_gemini"

    @property
    def model_id(self) -> str:
        return _MODEL_ID

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _sanitize_error(self, text: str) -> str:
        if self._api_key and self._api_key in text:
            return text.replace(self._api_key, "[REDACTED]")
        return text

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        timeout: float = 45.0,
        max_tokens: int = 1024,
    ) -> AIResponse:
        if not self._api_key:
            return AIResponse(
                success=False,
                model_id=_MODEL_ID,
                provider=self.provider_name,
                error_code="NO_API_KEY",
                error_message="GEMINI_API_KEY not configured",
                latency_sec=0.0,
            )

        url = f"{_GEMINI_API_BASE}/{_MODEL_ID}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        contents = []
        if system:
            contents.append({
                "role": "user",
                "parts": [{"text": f"[SYSTEM INSTRUCTION]\n{system}\n\n[USER REQUEST]\n{prompt}"}],
            })
        else:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        generation_config: Dict[str, Any] = {
            "maxOutputTokens": max_tokens,
            "temperature": 0.1,
        }
        if schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = schema

        payload = {
            "contents": contents,
            "generationConfig": generation_config,
        }

        attempt = 0
        last_error: Optional[str] = None
        last_code: Optional[str] = None
        t_start = time.perf_counter()

        while attempt <= _MAX_RETRIES:
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
                latency = time.perf_counter() - t_start

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                    content_text = (parts[0].get("text", "") if parts else "") or ""
                    usage = data.get("usageMetadata", {})

                    if not content_text.strip():
                        finish_reason = candidates[0].get("finishReason", "EMPTY") if candidates else "NO_CANDIDATES"
                        return AIResponse(
                            success=False,
                            model_id=_MODEL_ID,
                            provider=self.provider_name,
                            input_tokens=usage.get("promptTokenCount"),
                            output_tokens=usage.get("candidatesTokenCount"),
                            error_code=f"EMPTY_RESPONSE_{finish_reason}",
                            error_message="Provider returned empty content",
                            latency_sec=round(latency, 3),
                        )

                    return AIResponse(
                        success=True,
                        content=content_text,
                        raw_text=content_text,
                        model_id=_MODEL_ID,
                        provider=self.provider_name,
                        input_tokens=usage.get("promptTokenCount"),
                        output_tokens=usage.get("candidatesTokenCount"),
                        latency_sec=round(latency, 3),
                    )

                elif resp.status_code in (429, 503):
                    last_code = f"HTTP_{resp.status_code}"
                    last_error = self._sanitize_error(resp.text[:200])
                    wait = _BACKOFF_BASE ** attempt
                    logger.warning(
                        f"[Gemini] {resp.status_code} on attempt {attempt + 1}; "
                        f"retrying in {wait:.1f}s"
                    )
                    if attempt < _MAX_RETRIES:
                        time.sleep(wait)
                    attempt += 1
                    continue

                else:
                    latency = time.perf_counter() - t_start
                    return AIResponse(
                        success=False,
                        model_id=_MODEL_ID,
                        provider=self.provider_name,
                        error_code=f"HTTP_{resp.status_code}",
                        error_message=self._sanitize_error(resp.text[:300]),
                        latency_sec=round(latency, 3),
                    )

            except httpx.TimeoutException:
                latency = time.perf_counter() - t_start
                last_code = "TIMEOUT"
                last_error = f"Request timed out after {timeout}s"
                attempt += 1
                if attempt > _MAX_RETRIES:
                    break
                logger.warning(f"[Gemini] Timeout on attempt {attempt}; retrying")
                time.sleep(_BACKOFF_BASE ** (attempt - 1))

            except Exception as exc:
                latency = time.perf_counter() - t_start
                return AIResponse(
                    success=False,
                    model_id=_MODEL_ID,
                    provider=self.provider_name,
                    error_code="UNEXPECTED_ERROR",
                    error_message=self._sanitize_error(str(exc)[:300]),
                    latency_sec=round(latency, 3),
                )

        latency = time.perf_counter() - t_start
        return AIResponse(
            success=False,
            model_id=_MODEL_ID,
            provider=self.provider_name,
            error_code=last_code or "RETRIES_EXHAUSTED",
            error_message=last_error or "Max retries exceeded",
            latency_sec=round(latency, 3),
        )


# Singleton
gemini_adapter = GeminiAdapter()
