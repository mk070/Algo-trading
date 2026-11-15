"""Telemetry and Egress Tracking Module for Neon PostgreSQL and HTTP API.

Tracks:
- SQL query counts, row counts, and estimated result bytes returned by route and tag.
- HTTP response bytes and status codes by route.
- Cache hit/miss rates.
- Quota alerts at 60% and 85% of Neon Free tier (5 GB monthly limit).

Guarantees:
- Never logs query parameters, credentials, tokens, or sensitive payloads.
- Thread-safe and asynchronous context-aware using ContextVars.
"""

import contextvars
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Request Context Variables
current_route_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("current_route", default="background")
current_tag_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("current_query_tag", default="general")


def estimate_value_bytes(val: Any) -> int:
    """Estimates wire-format byte size of a Python value returned from PostgreSQL cursor."""
    if val is None:
        return 1
    if isinstance(val, (int, float)):
        return 8
    if isinstance(val, bool):
        return 1
    if isinstance(val, str):
        return len(val.encode("utf-8", errors="ignore"))
    if isinstance(val, (bytes, bytearray)):
        return len(val)
    if isinstance(val, (datetime,)):
        return 16
    return len(str(val).encode("utf-8", errors="ignore"))


def estimate_row_bytes(row: Any) -> int:
    """Estimates PostgreSQL wire protocol framing size for a single row:
    ~16 bytes row tuple header + ~8 bytes per column descriptor/offset + column data bytes.
    """
    try:
        col_count = len(row)
        data_bytes = sum(estimate_value_bytes(v) for v in row)
        return 16 + (8 * col_count) + data_bytes
    except Exception:
        return 32


class EgressTracker:
    """Thread-safe aggregator for SQL and HTTP egress metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = datetime.now(timezone.utc)
        self.quota_limit_bytes = 5 * 1024 * 1024 * 1024  # 5 GB monthly
        self.warning_60_bytes = int(0.60 * self.quota_limit_bytes)
        self.warning_85_bytes = int(0.85 * self.quota_limit_bytes)

        # Route-level stats: route -> dict
        self._routes: Dict[str, Dict[str, Any]] = {}
        # Tag-level stats: tag -> dict
        self._tags: Dict[str, Dict[str, Any]] = {}

        self.total_sql_queries = 0
        self.total_sql_rows = 0
        self.total_sql_bytes = 0
        self.total_http_bytes = 0
        self.total_cache_hits = 0
        self.total_cache_misses = 0

    def record_query(
        self,
        duration_sec: float,
        row_count: int,
        row_bytes: int,
        route: Optional[str] = None,
        tag: Optional[str] = None,
    ):
        target_route = route or current_route_ctx.get()
        target_tag = tag or current_tag_ctx.get()

        with self._lock:
            self.total_sql_queries += 1
            self.total_sql_rows += row_count
            self.total_sql_bytes += row_bytes

            # Update route stats
            r_stat = self._routes.setdefault(
                target_route,
                {
                    "route": target_route,
                    "sql_queries": 0,
                    "sql_rows": 0,
                    "sql_bytes": 0,
                    "http_calls": 0,
                    "http_bytes": 0,
                    "total_duration_ms": 0.0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                },
            )
            r_stat["sql_queries"] += 1
            r_stat["sql_rows"] += row_count
            r_stat["sql_bytes"] += row_bytes
            r_stat["total_duration_ms"] += duration_sec * 1000.0

            # Update tag stats
            t_stat = self._tags.setdefault(
                target_tag,
                {
                    "tag": target_tag,
                    "sql_queries": 0,
                    "sql_rows": 0,
                    "sql_bytes": 0,
                },
            )
            t_stat["sql_queries"] += 1
            t_stat["sql_rows"] += row_count
            t_stat["sql_bytes"] += row_bytes

    def record_http(self, route: str, status_code: int, bytes_sent: int, duration_sec: float):
        with self._lock:
            self.total_http_bytes += bytes_sent
            r_stat = self._routes.setdefault(
                route,
                {
                    "route": route,
                    "sql_queries": 0,
                    "sql_rows": 0,
                    "sql_bytes": 0,
                    "http_calls": 0,
                    "http_bytes": 0,
                    "total_duration_ms": 0.0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                },
            )
            r_stat["http_calls"] += 1
            r_stat["http_bytes"] += bytes_sent
            r_stat["total_duration_ms"] += duration_sec * 1000.0

    def record_cache_hit(self, route: Optional[str] = None):
        target = route or current_route_ctx.get()
        with self._lock:
            self.total_cache_hits += 1
            r_stat = self._routes.setdefault(
                target,
                {
                    "route": target,
                    "sql_queries": 0,
                    "sql_rows": 0,
                    "sql_bytes": 0,
                    "http_calls": 0,
                    "http_bytes": 0,
                    "total_duration_ms": 0.0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                },
            )
            r_stat["cache_hits"] += 1

    def record_cache_miss(self, route: Optional[str] = None):
        target = route or current_route_ctx.get()
        with self._lock:
            self.total_cache_misses += 1
            r_stat = self._routes.setdefault(
                target,
                {
                    "route": target,
                    "sql_queries": 0,
                    "sql_rows": 0,
                    "sql_bytes": 0,
                    "http_calls": 0,
                    "http_bytes": 0,
                    "total_duration_ms": 0.0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                },
            )
            r_stat["cache_misses"] += 1

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            routes_list = list(self._routes.values())
            tags_list = list(self._tags.values())

            # Top 10 endpoints by estimated SQL bytes
            top_sql = sorted(routes_list, key=lambda x: x["sql_bytes"], reverse=True)[:10]
            # Top 10 endpoints by HTTP response bytes
            top_http = sorted(routes_list, key=lambda x: x["http_bytes"], reverse=True)[:10]

            pct_used = (self.total_sql_bytes / self.quota_limit_bytes) * 100.0
            warning_level = "NORMAL"
            if self.total_sql_bytes >= self.warning_85_bytes:
                warning_level = "CRITICAL_85"
            elif self.total_sql_bytes >= self.warning_60_bytes:
                warning_level = "WARNING_60"

            return {
                "started_at": self.started_at.isoformat(),
                "uptime_seconds": (datetime.now(timezone.utc) - self.started_at).total_seconds(),
                "neon_quota_bytes": self.quota_limit_bytes,
                "total_estimated_sql_bytes": self.total_sql_bytes,
                "total_sql_queries": self.total_sql_queries,
                "total_sql_rows": self.total_sql_rows,
                "total_http_bytes_sent": self.total_http_bytes,
                "total_cache_hits": self.total_cache_hits,
                "total_cache_misses": self.total_cache_misses,
                "cache_hit_rate_pct": (
                    (self.total_cache_hits / (self.total_cache_hits + self.total_cache_misses) * 100.0)
                    if (self.total_cache_hits + self.total_cache_misses) > 0
                    else 0.0
                ),
                "quota_consumed_pct": round(pct_used, 4),
                "warning_level": warning_level,
                "top_10_by_sql_bytes": top_sql,
                "top_10_by_http_bytes": top_http,
                "query_tags": sorted(tags_list, key=lambda x: x["sql_bytes"], reverse=True)[:10],
            }


# Singleton Egress Tracker
tracker = EgressTracker()


def setup_sqlalchemy_telemetry(engine):
    """Registers SQLAlchemy event listeners on the engine to monitor SQL result rows and bytes."""
    from sqlalchemy import event

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._query_start_time = time.perf_counter()

    @event.listens_for(engine, "after_execute")
    def after_execute(conn, clauseelement, multiparams, params, execution_options, result):
        context = getattr(result, "context", None)
        start_time = getattr(context, "_query_start_time", time.perf_counter()) if context else time.perf_counter()
        duration = max(0.0, time.perf_counter() - start_time)

        if not getattr(result, "returns_rows", False):
            # Non-SELECT statement (INSERT, UPDATE, DELETE)
            affected_rows = max(0, getattr(result, "rowcount", 0))
            tracker.record_query(duration_sec=duration, row_count=affected_rows, row_bytes=affected_rows * 16)
            return

        # Wrap result fetching to track exact rows and bytes as they stream/read
        orig_one = result._fetchone_impl
        orig_all = result._fetchall_impl
        orig_many = result._fetchmany_impl
        orig_iter = result._iter_impl

        def tracking_fetchone(hard_close=False):
            row = orig_one(hard_close=hard_close)
            if row is not None:
                b = estimate_row_bytes(row)
                tracker.record_query(duration_sec=duration, row_count=1, row_bytes=b)
            return row

        def tracking_fetchall():
            rows = orig_all()
            total_b = sum(estimate_row_bytes(r) for r in rows)
            tracker.record_query(duration_sec=duration, row_count=len(rows), row_bytes=total_b)
            return rows

        def tracking_fetchmany(size=None):
            rows = orig_many(size) if size is not None else orig_many()
            total_b = sum(estimate_row_bytes(r) for r in rows)
            tracker.record_query(duration_sec=duration, row_count=len(rows), row_bytes=total_b)
            return rows

        def tracking_iter():
            for row in orig_iter():
                b = estimate_row_bytes(row)
                tracker.record_query(duration_sec=duration, row_count=1, row_bytes=b)
                yield row

        result._fetchone_impl = tracking_fetchone
        result._fetchall_impl = tracking_fetchall
        result._fetchmany_impl = tracking_fetchmany
        result._iter_impl = tracking_iter
