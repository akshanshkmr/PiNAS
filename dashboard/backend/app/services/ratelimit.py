"""In-process sliding-window rate limiter for auth-style abuse.

Single-uvicorn-worker deployment, so a dict + deque is enough and there's
no need to reach for Redis. State is intentionally not persisted across
restarts — an attacker who can bounce the backend can already do worse.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock

log = logging.getLogger(__name__)


class SlidingCounter:
    """Track failures per opaque key inside a rolling window.

    When the window fills up the key enters a cool-off during which
    `retry_after` returns a positive number of seconds and the caller
    is expected to reject the request with 429.
    """

    def __init__(self, max_hits: int, window_s: int, cool_off_s: int, label: str):
        self.max = max_hits
        self.window = window_s
        self.cool_off = cool_off_s
        self.label = label
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._locked_until: dict[str, float] = {}
        self._lock = Lock()

    def _prune(self, q: deque[float], now: float) -> None:
        cutoff = now - self.window
        while q and q[0] < cutoff:
            q.popleft()

    def record_failure(self, key: str) -> None:
        now = time.time()
        with self._lock:
            q = self._events[key]
            q.append(now)
            self._prune(q, now)
            if len(q) >= self.max and self._locked_until.get(key, 0) <= now:
                self._locked_until[key] = now + self.cool_off
                log.warning("ratelimit: %s=%s locked out for %ds after %d failures",
                            self.label, key, self.cool_off, len(q))

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)
            self._locked_until.pop(key, None)

    def retry_after(self, key: str) -> float:
        """Seconds until this key may try again. 0.0 means "allowed now"."""
        now = time.time()
        with self._lock:
            until = self._locked_until.get(key, 0)
            if until > now:
                return until - now
            # Cool-off expired — drop stale state and let them through.
            self._locked_until.pop(key, None)
            q = self._events.get(key)
            if q:
                self._prune(q, now)
            return 0.0


# Two independent counters — attacker breaching either gets stopped.
# Per-IP is generous (users on shared LAN, typo-storms).
# Per-username is stricter, and hits before an attacker even knows if the
# username is real — reduces the value of account enumeration.
login_ip = SlidingCounter(max_hits=15, window_s=15 * 60, cool_off_s=15 * 60, label="login-ip")
login_user = SlidingCounter(max_hits=8, window_s=15 * 60, cool_off_s=30 * 60, label="login-user")
