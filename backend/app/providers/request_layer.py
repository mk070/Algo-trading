import datetime
import enum
import logging
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when request is rejected because circuit breaker is in OPEN/cooldown state."""
    pass


class SingleFlight:
    """Coalesces duplicate concurrent in-flight requests for the same key so only 1 executes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls: Dict[str, Tuple[threading.Event, Dict[str, Any]]] = {}

    def execute(self, key: str, fn: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._calls:
                event, result_box = self._calls[key]
                is_leader = False
            else:
                event = threading.Event()
                result_box = {}
                self._calls[key] = (event, result_box)
                is_leader = True

        if is_leader:
            try:
                val = fn()
                result_box["value"] = val
                return val
            except Exception as e:
                result_box["error"] = e
                raise
            finally:
                event.set()
                with self._lock:
                    self._calls.pop(key, None)
        else:
            # Follower: wait for the leader's execution to complete
            event.wait(timeout=30.0)
            if "error" in result_box:
                raise result_box["error"]
            return result_box.get("value")


class ProviderRequestLayer:
    """Robust request layer for REST/HTTP providers.
    Features:
    - Single-flight in-flight deduplication per request key.
    - Per-provider in-memory TTL caching.
    - Bounded concurrency per provider via semaphore.
    - 429 / Retry-After handling with exponential backoff and randomized jitter.
    - Circuit-breaker state machine with cooldown.
    - Sliding-window latency (p50, p95) and success rate metrics.
    """

    def __init__(
        self,
        name: str,
        max_concurrency: int = 5,
        default_timeout: float = 10.0,
        failure_threshold: int = 5,
        cooldown_sec: float = 60.0,
    ):
        self.name = name
        self.semaphore = threading.Semaphore(max_concurrency)
        self.default_timeout = default_timeout
        self.failure_threshold = failure_threshold
        self.cooldown_sec = cooldown_sec

        self.single_flight = SingleFlight()
        self._ttl_cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()

        # Circuit breaker state
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._cooldown_until: Optional[float] = None
        self._state_lock = threading.RLock()

        # Metrics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.latencies_ms: List[float] = []
        self.last_error: Optional[str] = None
        self.last_error_ts: Optional[datetime.datetime] = None

    @property
    def circuit_state(self) -> str:
        with self._state_lock:
            if self._state == CircuitState.OPEN and self._cooldown_until:
                if time.time() >= self._cooldown_until:
                    self._state = CircuitState.HALF_OPEN
            return self._state.value

    def get_cooldown_until_iso(self) -> Optional[str]:
        with self._state_lock:
            if self._cooldown_until and self._state == CircuitState.OPEN:
                return datetime.datetime.fromtimestamp(
                    self._cooldown_until, tz=datetime.timezone.utc
                ).isoformat()
            return None

    def get_metrics(self) -> Dict[str, Any]:
        with self._state_lock:
            p50 = 0.0
            p95 = 0.0
            if self.latencies_ms:
                sorted_l = sorted(self.latencies_ms)
                p50 = sorted_l[int(len(sorted_l) * 0.5)]
                p95 = sorted_l[min(int(len(sorted_l) * 0.95), len(sorted_l) - 1)]

            succ_rate = (
                self.successful_requests / self.total_requests
                if self.total_requests > 0
                else 1.0
            )

            return {
                "success_rate": round(succ_rate, 3),
                "p50_latency_ms": round(p50, 1),
                "p95_latency_ms": round(p95, 1),
                "circuit_state": self.circuit_state,
                "cooldown_until": self.get_cooldown_until_iso(),
                "last_error": self.last_error,
            }

    def _record_success(self, latency_ms: float):
        with self._state_lock:
            self.total_requests += 1
            self.successful_requests += 1
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            self._cooldown_until = None
            self.latencies_ms.append(latency_ms)
            if len(self.latencies_ms) > 100:
                self.latencies_ms.pop(0)

    def _record_failure(self, err_msg: str, latency_ms: float):
        with self._state_lock:
            self.total_requests += 1
            self.failed_requests += 1
            self._consecutive_failures += 1
            self.last_error = err_msg
            self.last_error_ts = datetime.datetime.now(datetime.timezone.utc)
            self.latencies_ms.append(latency_ms)
            if len(self.latencies_ms) > 100:
                self.latencies_ms.pop(0)

            if self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._cooldown_until = time.time() + self.cooldown_sec
                logger.error(
                    f"Circuit breaker tripped to OPEN for {self.name} for {self.cooldown_sec}s: {err_msg}"
                )

    def execute(
        self,
        request_key: str,
        fn: Callable[[], Any],
        ttl_sec: Optional[float] = None,
        max_retries: int = 2,
    ) -> Any:
        """Executes a provider operation through the guarded request layer."""
        # 1. Check TTL cache
        if ttl_sec and ttl_sec > 0:
            with self._cache_lock:
                cached = self._ttl_cache.get(request_key)
                if cached:
                    exp, val = cached
                    if time.time() < exp:
                        return val

        # 2. Check Circuit Breaker
        state = self.circuit_state
        if state == CircuitState.OPEN:
            # Check if cached fallback exists even if expired
            with self._cache_lock:
                cached = self._ttl_cache.get(request_key)
                if cached:
                    return cached[1]
            raise CircuitBreakerOpenError(
                f"Provider {self.name} is in cooldown (OPEN). Next probe at {self.get_cooldown_until_iso()}."
            )

        # 3. Single-Flight Coalescing
        def wrapped_run():
            attempt = 0
            while attempt <= max_retries:
                acquired = self.semaphore.acquire(timeout=self.default_timeout)
                if not acquired:
                    raise TimeoutError(f"Concurrency queue timeout for {self.name}")

                t0 = time.time()
                try:
                    res = fn()
                    dur_ms = (time.time() - t0) * 1000.0
                    self._record_success(dur_ms)

                    if ttl_sec and ttl_sec > 0:
                        with self._cache_lock:
                            self._ttl_cache[request_key] = (time.time() + ttl_sec, res)

                    return res
                except Exception as e:
                    dur_ms = (time.time() - t0) * 1000.0
                    err_str = str(e)
                    is_rate_limited = "429" in err_str or "Rate limit" in err_str or "Too Many Requests" in err_str

                    attempt += 1
                    if attempt > max_retries:
                        self._record_failure(err_str, dur_ms)
                        raise

                    # 429 backoff with exponential backoff & jitter
                    base_delay = 1.0 * (2 ** (attempt - 1))
                    jitter = random.uniform(0.1, 0.5)
                    delay = base_delay + jitter
                    logger.warning(
                        f"Retrying {self.name} operation for {request_key} in {delay:.2f}s (Attempt {attempt}/{max_retries}): {e}"
                    )
                    time.sleep(delay)
                finally:
                    self.semaphore.release()

        return self.single_flight.execute(request_key, wrapped_run)


# Global provider request layer registries
request_layers: Dict[str, ProviderRequestLayer] = {
    "angelone": ProviderRequestLayer("angelone", max_concurrency=5, default_timeout=8.0, failure_threshold=5, cooldown_sec=45.0),
    "yfinance": ProviderRequestLayer("yfinance", max_concurrency=4, default_timeout=12.0, failure_threshold=4, cooldown_sec=60.0),
    "alpaca": ProviderRequestLayer("alpaca", max_concurrency=5, default_timeout=10.0, failure_threshold=5, cooldown_sec=60.0),
    "kite_personal": ProviderRequestLayer("kite_personal", max_concurrency=3, default_timeout=10.0, failure_threshold=5, cooldown_sec=60.0),
}

