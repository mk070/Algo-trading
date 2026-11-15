"""Server-Side Shared In-Process Memory Cache with Single-Flight Locking and ETag Support.

Features:
- Single-flight concurrency locks: Prevents thundering-herd database queries when multiple clients poll the same key.
- Per-market cache keys (e.g. regime:IN, pulse:US).
- Time-to-Live (TTL) expiration with max-stale serving during database outages.
- ETag generation with HTTP 304 Not Modified support to avoid redundant network payload transfers.
- Explicit cache invalidation upon EOD scan completion or manual user edits.
"""

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple
from starlette.responses import JSONResponse, Response

from app.telemetry import tracker

logger = logging.getLogger(__name__)


class CacheEntry:
    def __init__(self, data: Any, ttl_sec: float):
        self.data = data
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_sec
        # Precompute JSON bytes and ETag
        self.serialized_json = json.dumps(data, default=str)
        self.etag = f'"{hashlib.sha256(self.serialized_json.encode("utf-8")).hexdigest()[:16]}"'

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class SharedMemoryCache:
    """Thread-safe in-memory cache with single-flight mutex per key."""

    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._key_locks: Dict[str, threading.Lock] = {}

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def get(self, key: str, allow_stale: bool = True) -> Tuple[Optional[Any], Optional[str], bool, float]:
        """Returns (data, etag, is_stale, age_seconds)."""
        with self._lock:
            entry = self._cache.get(key)

        if not entry:
            tracker.record_cache_miss()
            return None, None, False, 0.0

        if not entry.is_expired:
            tracker.record_cache_hit()
            return entry.data, entry.etag, False, entry.age_seconds

        if allow_stale:
            # Expired but available as fallback
            tracker.record_cache_hit()
            return entry.data, entry.etag, True, entry.age_seconds

        tracker.record_cache_miss()
        return None, None, False, 0.0

    def set(self, key: str, data: Any, ttl_sec: float = 60.0):
        entry = CacheEntry(data, ttl_sec)
        with self._lock:
            self._cache[key] = entry

    def invalidate(self, prefix_or_key: str):
        """Invalidates all cache entries matching prefix or key."""
        with self._lock:
            keys_to_del = [k for k in self._cache if k == prefix_or_key or k.startswith(prefix_or_key)]
            for k in keys_to_del:
                self._cache.pop(k, None)
            logger.debug(f"Invalidated {len(keys_to_del)} cache keys for prefix '{prefix_or_key}'")

    def invalidate_prefix(self, prefix: str):
        self.invalidate(prefix)

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl_sec: float = 60.0,
        allow_stale_on_error: bool = True,
    ) -> Tuple[Any, str, bool, float]:
        """Single-flight fetch or compute pattern:
        If cache is warm and fresh, returns cached data immediately.
        If cache is cold/expired, only ONE thread executes compute_fn while others wait.
        If compute_fn raises an exception (e.g. Neon quota or connection error), serves stale data if available.
        """
        # Fast path
        with self._lock:
            entry = self._cache.get(key)
        if entry and not entry.is_expired:
            tracker.record_cache_hit()
            return entry.data, entry.etag, False, entry.age_seconds

        # Slow path under per-key lock
        key_lock = self._get_key_lock(key)
        with key_lock:
            # Double-check inside lock
            with self._lock:
                entry = self._cache.get(key)
            if entry and not entry.is_expired:
                tracker.record_cache_hit()
                return entry.data, entry.etag, False, entry.age_seconds

            tracker.record_cache_miss()
            try:
                computed_data = compute_fn()
                new_entry = CacheEntry(computed_data, ttl_sec)
                with self._lock:
                    self._cache[key] = new_entry
                return new_entry.data, new_entry.etag, False, 0.0
            except Exception as e:
                if allow_stale_on_error and entry is not None:
                    logger.warning(f"Error computing '{key}' ({e}); serving stale cached data ({entry.age_seconds:.1f}s old).")
                    return entry.data, entry.etag, True, entry.age_seconds
                raise


# Global singleton cache
shared_cache = SharedMemoryCache()


def cached_json_response(
    data: Any,
    etag: str,
    if_none_match: Optional[str] = None,
    max_age_sec: int = 60,
    is_stale: bool = False,
) -> Response:
    """Builds standard FastAPI Response with ETag and Cache-Control headers.
    Returns HTTP 304 Not Modified if if_none_match matches etag.
    """
    headers = {
        "ETag": etag,
        "Cache-Control": f"public, max-age={max_age_sec}, stale-while-revalidate=300",
    }
    if is_stale:
        headers["X-Data-Stale"] = "true"

    if if_none_match and if_none_match.strip() == etag.strip():
        # HTTP 304 Not Modified: send 0-byte body across the network!
        return Response(status_code=304, headers=headers)

    return JSONResponse(content=data, headers=headers)
