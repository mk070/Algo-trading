"""
Quota Guard — DB-backed atomic quota reservations + in-memory per-minute smoothing.

Safety properties:
  - Restart-safe: daily usage is persisted in `ai_provider_usage`.
  - Concurrency-safe: daily slot reservation uses an atomic SQL conditional UPDATE
    (`WHERE reserved_count < :daily_limit`) so concurrent requests / workers cannot
    exceed the configured daily allowance.
  - Failed requests are recorded in `failed_count` and NEVER counted as successful
    generations (`request_count`).
  - Individual agent flags are enforced; `AI_AGENTS_ENABLED=False` overrides all.
  - Hard stop when quota exhausted: NO paid fallback, NO NVIDIA fallback for live
    production requests.
  - Conservative local accounting: NOT authoritative over Google's provider-side quota.

Feature flags (all default OFF):
  AI_AGENTS_ENABLED, AI_GEMINI_ENABLED, AI_ZERO_COST_ONLY,
  AI_MAX_DAILY_REQUESTS, AI_MAX_REQUESTS_PER_MINUTE,
  AI_NEWS_AGENT_ENABLED, AI_COMPANY_AGENT_ENABLED, AI_MARKET_AGENT_ENABLED,
  AI_TECHNICAL_AGENT_ENABLED, AI_RISK_AGENT_ENABLED, AI_DECISION_AGENT_ENABLED
"""

from __future__ import annotations

import datetime
import logging
import threading
from collections import deque
from typing import Dict, Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.schemas import QuotaStatus

logger = logging.getLogger(__name__)

# Mapping from canonical agent_name -> env/settings flag name
_AGENT_FLAG_MAP: Dict[str, str] = {
    "news_intelligence": "AI_NEWS_AGENT_ENABLED",
    "company_research": "AI_COMPANY_AGENT_ENABLED",
    "market_context": "AI_MARKET_AGENT_ENABLED",
    "technical_research": "AI_TECHNICAL_AGENT_ENABLED",
    "risk_review": "AI_RISK_AGENT_ENABLED",
    "final_decision": "AI_DECISION_AGENT_ENABLED",
}


# ---------------------------------------------------------------------------
# Feature flags with safe defaults (all OFF)
# ---------------------------------------------------------------------------

class _Flags:
    """Lazy flag reader that sources values from env + settings, with safe defaults."""

    @property
    def ai_agents_enabled(self) -> bool:
        return self._bool("AI_AGENTS_ENABLED", False)

    @property
    def ai_gemini_enabled(self) -> bool:
        return self._bool("AI_GEMINI_ENABLED", False)

    @property
    def ai_nvidia_research_enabled(self) -> bool:
        return self._bool("AI_NVIDIA_RESEARCH_ENABLED", False)

    @property
    def ai_zero_cost_only(self) -> bool:
        return self._bool("AI_ZERO_COST_ONLY", True)  # Hard default: cost-safe

    @property
    def ai_max_daily_requests(self) -> int:
        return self._int("AI_MAX_DAILY_REQUESTS", 100)

    @property
    def ai_max_requests_per_minute(self) -> int:
        return self._int("AI_MAX_REQUESTS_PER_MINUTE", 10)

    @property
    def ai_news_agent_enabled(self) -> bool:
        return self._bool("AI_NEWS_AGENT_ENABLED", False)

    @property
    def ai_company_agent_enabled(self) -> bool:
        return self._bool("AI_COMPANY_AGENT_ENABLED", False)

    @property
    def ai_market_agent_enabled(self) -> bool:
        return self._bool("AI_MARKET_AGENT_ENABLED", False)

    @property
    def ai_technical_agent_enabled(self) -> bool:
        return self._bool("AI_TECHNICAL_AGENT_ENABLED", False)

    @property
    def ai_risk_agent_enabled(self) -> bool:
        return self._bool("AI_RISK_AGENT_ENABLED", False)

    @property
    def ai_decision_agent_enabled(self) -> bool:
        return self._bool("AI_DECISION_AGENT_ENABLED", False)

    def agent_flag(self, agent_name: str) -> bool:
        env_key = _AGENT_FLAG_MAP.get(agent_name)
        if not env_key:
            return False
        return self._bool(env_key, False)

    def all_agent_flags(self) -> Dict[str, bool]:
        return {name: self.agent_flag(name) for name in _AGENT_FLAG_MAP}

    @staticmethod
    def _bool(key: str, default: bool) -> bool:
        import os
        val = os.environ.get(key, "").strip().lower()
        if val in ("1", "true", "yes"):
            return True
        if val in ("0", "false", "no"):
            return False
        try:
            from app.settings import settings
            return bool(getattr(settings, key.lower(), default))
        except Exception:
            return default

    @staticmethod
    def _int(key: str, default: int) -> int:
        import os
        val = os.environ.get(key, "").strip()
        if val.isdigit():
            return int(val)
        try:
            from app.settings import settings
            return int(getattr(settings, key.lower(), default))
        except Exception:
            return default


flags = _Flags()


# ---------------------------------------------------------------------------
# Quota Guard (DB-backed atomic reservations + in-memory RPM window)
# ---------------------------------------------------------------------------

class QuotaGuard:
    """
    Thread-safe, restart-safe quota tracker.
    Uses atomic DB updates on `ai_provider_usage` when a Session is supplied,
    and an in-memory sliding window for per-minute rate smoothing.
    Conservative: counts requests locally; NOT authoritative vs. Google billing counters.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._today: Optional[datetime.date] = None
        self._daily_count: int = 0
        self._successful_count: int = 0
        self._failed_count: int = 0
        self._exhausted_at: Optional[datetime.datetime] = None
        self._minute_window: deque = deque()

    def _utc_today(self) -> datetime.date:
        return datetime.datetime.now(datetime.timezone.utc).date()

    def _reset_if_new_day(self) -> None:
        today = self._utc_today()
        if self._today != today:
            self._today = today
            self._daily_count = 0
            self._successful_count = 0
            self._failed_count = 0
            self._exhausted_at = None
            logger.info("[QuotaGuard] Daily counter reset for new UTC day.")

    def _prune_minute_window(self) -> None:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=60)
        while self._minute_window and self._minute_window[0] < cutoff:
            self._minute_window.popleft()

    def is_agent_enabled(self, agent_name: str) -> bool:
        """
        Global AI_AGENTS_ENABLED overrides all individual flags.
        Both AI_AGENTS_ENABLED, AI_GEMINI_ENABLED, and the agent's own flag must be True.
        """
        if not flags.ai_agents_enabled:
            return False
        if not flags.ai_gemini_enabled:
            return False
        if agent_name in _AGENT_FLAG_MAP:
            return flags.agent_flag(agent_name)
        return True

    def _ensure_usage_row(
        self,
        db: Session,
        today: datetime.date,
        provider: str,
        model_id: str,
    ) -> None:
        from app.ai.models import AiProviderUsage

        existing = (
            db.query(AiProviderUsage)
            .filter(
                AiProviderUsage.date == today,
                AiProviderUsage.provider == provider,
                AiProviderUsage.model_id == model_id,
            )
            .first()
        )
        if existing is not None:
            return

        # Use a savepoint so an IntegrityError from a concurrent insert does not
        # roll back the caller's outer transaction.
        try:
            with db.begin_nested():
                db.add(
                    AiProviderUsage(
                        date=today,
                        provider=provider,
                        model_id=model_id,
                        reserved_count=0,
                        request_count=0,
                        failed_count=0,
                        total_input_tokens=0,
                        total_output_tokens=0,
                    )
                )
                db.flush()
        except IntegrityError:
            # Another worker inserted the row concurrently — safe to continue.
            pass

    def check_and_consume(
        self,
        agent_name: str,
        db: Optional[Session] = None,
        provider: str = "google_gemini",
        model_id: str = "gemini-3.1-flash-lite",
    ) -> bool:
        """
        Atomically reserve 1 request slot if permitted.
        Returns False if:
          - Global AI_AGENTS_ENABLED is False
          - AI_GEMINI_ENABLED is False
          - Individual agent flag is False
          - Per-minute rate limit is reached
          - Daily quota is exhausted (checked atomically in DB when `db` is provided)
        Never raises; fails closed.
        """
        try:
            if not self.is_agent_enabled(agent_name):
                logger.debug(f"[QuotaGuard] BLOCKED: agent '{agent_name}' disabled by feature flags")
                return False

            daily_limit = flags.ai_max_daily_requests
            rpm_limit = flags.ai_max_requests_per_minute

            if daily_limit <= 0:
                return False

            with self._lock:
                self._reset_if_new_day()
                self._prune_minute_window()

                if len(self._minute_window) >= rpm_limit:
                    logger.warning(
                        f"[QuotaGuard] Per-minute rate limit ({rpm_limit} RPM) reached "
                        f"for agent '{agent_name}'. Request blocked."
                    )
                    return False

                if db is None:
                    if self._daily_count >= daily_limit:
                        if not self._exhausted_at:
                            self._exhausted_at = datetime.datetime.now(datetime.timezone.utc)
                        return False
                    self._daily_count += 1
                    self._minute_window.append(datetime.datetime.now(datetime.timezone.utc))
                    return True

            # DB-backed atomic reservation outside the in-memory lock so SQLite/Postgres
            # row locking serializes concurrent threads/processes cleanly.
            today = self._utc_today()
            self._ensure_usage_row(db, today, provider, model_id)

            from app.ai.models import AiProviderUsage
            stmt = (
                update(AiProviderUsage)
                .where(
                    AiProviderUsage.date == today,
                    AiProviderUsage.provider == provider,
                    AiProviderUsage.model_id == model_id,
                    AiProviderUsage.reserved_count < daily_limit,
                )
                .values(reserved_count=AiProviderUsage.reserved_count + 1)
            )
            res = db.execute(stmt)
            db.flush()

            if res.rowcount == 0:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                db.execute(
                    update(AiProviderUsage)
                    .where(
                        AiProviderUsage.date == today,
                        AiProviderUsage.provider == provider,
                        AiProviderUsage.model_id == model_id,
                        AiProviderUsage.quota_exhausted_at.is_(None),
                    )
                    .values(quota_exhausted_at=now_utc)
                )
                db.flush()
                with self._lock:
                    if not self._exhausted_at:
                        self._exhausted_at = now_utc
                logger.warning(
                    f"[QuotaGuard] Persistent daily quota ({daily_limit}) exhausted for {model_id}."
                )
                return False

            with self._lock:
                self._reset_if_new_day()
                self._daily_count += 1
                self._minute_window.append(datetime.datetime.now(datetime.timezone.utc))
            return True

        except Exception as exc:
            logger.error(f"[QuotaGuard] Unexpected error in check_and_consume: {exc}")
            return False  # Fail closed

    def record_outcome(
        self,
        *,
        success: bool,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        error_code: Optional[str] = None,
        db: Optional[Session] = None,
        provider: str = "google_gemini",
        model_id: str = "gemini-3.1-flash-lite",
    ) -> None:
        """
        Record actual outcome of a provider call.
        Failed requests increment `failed_count`, never `request_count`.
        """
        try:
            in_tok = max(0, int(input_tokens or 0))
            out_tok = max(0, int(output_tokens or 0))
            is_quota_err = error_code in ("HTTP_429", "QUOTA_EXHAUSTED")

            with self._lock:
                self._reset_if_new_day()
                if success:
                    self._successful_count += 1
                else:
                    self._failed_count += 1
                if is_quota_err and not self._exhausted_at:
                    self._exhausted_at = datetime.datetime.now(datetime.timezone.utc)

            if db is not None:
                from app.ai.models import AiProviderUsage
                today = self._utc_today()
                self._ensure_usage_row(db, today, provider, model_id)

                values: Dict[str, object] = {
                    "total_input_tokens": AiProviderUsage.total_input_tokens + in_tok,
                    "total_output_tokens": AiProviderUsage.total_output_tokens + out_tok,
                }
                if success:
                    values["request_count"] = AiProviderUsage.request_count + 1
                else:
                    values["failed_count"] = AiProviderUsage.failed_count + 1

                db.execute(
                    update(AiProviderUsage)
                    .where(
                        AiProviderUsage.date == today,
                        AiProviderUsage.provider == provider,
                        AiProviderUsage.model_id == model_id,
                    )
                    .values(**values)
                )
                if is_quota_err:
                    db.execute(
                        update(AiProviderUsage)
                        .where(
                            AiProviderUsage.date == today,
                            AiProviderUsage.provider == provider,
                            AiProviderUsage.model_id == model_id,
                            AiProviderUsage.quota_exhausted_at.is_(None),
                        )
                        .values(quota_exhausted_at=datetime.datetime.now(datetime.timezone.utc))
                    )
                db.flush()
        except Exception as exc:
            logger.warning(f"[QuotaGuard] Could not record outcome: {exc}")

    def get_status(self, db: Optional[Session] = None) -> QuotaStatus:
        daily_limit = flags.ai_max_daily_requests
        rpm_limit = flags.ai_max_requests_per_minute

        with self._lock:
            self._reset_if_new_day()
            self._prune_minute_window()
            used_today = self._daily_count
            successful_today = self._successful_count
            failed_today = self._failed_count
            used_minute = len(self._minute_window)
            exhausted_at = self._exhausted_at

        if db is not None:
            try:
                from app.ai.models import AiProviderUsage
                from app.ai.gemini_adapter import gemini_adapter
                today = self._utc_today()
                row = (
                    db.query(AiProviderUsage)
                    .filter(
                        AiProviderUsage.date == today,
                        AiProviderUsage.provider == gemini_adapter.provider_name,
                        AiProviderUsage.model_id == gemini_adapter.model_id,
                    )
                    .first()
                )
                if row is not None:
                    used_today = row.reserved_count
                    successful_today = row.request_count
                    failed_today = row.failed_count
                    if row.quota_exhausted_at:
                        exhausted_at = row.quota_exhausted_at
            except Exception as exc:
                logger.debug(f"[QuotaGuard] DB status lookup failed, using in-memory: {exc}")

        remaining = max(0, daily_limit - used_today)
        from app.ai.gemini_adapter import gemini_adapter

        return QuotaStatus(
            enabled=flags.ai_agents_enabled,
            gemini_enabled=flags.ai_gemini_enabled,
            nvidia_research_enabled=flags.ai_nvidia_research_enabled,
            zero_cost_only=flags.ai_zero_cost_only,
            daily_limit=daily_limit,
            per_minute_limit=rpm_limit,
            used_today=used_today,
            successful_today=successful_today,
            failed_today=failed_today,
            used_this_minute=used_minute,
            remaining_today=remaining,
            quota_exhausted=(used_today >= daily_limit),
            exhausted_at=exhausted_at,
            agent_flags=flags.all_agent_flags(),
            provider_status={
                "gemini_configured": gemini_adapter.is_available(),
                "gemini_model": gemini_adapter.model_id,
                "nvidia_policy": "OFFLINE_DEV_EVALUATION_ONLY",
                "blocked_free_tier": ["gemini-4-hydrogen", "gemini-3.8-flash"],
                "accounting_note": "Local accounting is conservative and not authoritative over Google provider-side quota.",
            },
        )


# Singleton
quota_guard = QuotaGuard()
