"""Minimal in-process sliding-window rate limiter.

Used to place a bounded protection in front of the operator ``/auth/login``
endpoint. It is keyed by client identifier (IP) rather than username, so it
throttles brute-force attempts from a single source WITHOUT locking any account
(which would enable a trivial targeted denial of service).

Prototype limitations (documented deliberately):
- State is per-process and in-memory: it is not shared across multiple workers
  and resets when the process restarts.
- It is therefore a defense-in-depth speed bump for the demo, not a substitute
  for an edge/gateway rate limiter in a real deployment.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Bounded sliding-window counter keyed by an arbitrary string."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str, max_events: int, window_seconds: float) -> bool:
        """Return True if the event is within the limit (and record it), else False.

        ``max_events <= 0`` disables the limit (always allowed).
        """
        if max_events <= 0:
            return True
        now = time.monotonic()
        cutoff = now - window_seconds
        events = self._events[key]
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= max_events:
            return False
        events.append(now)
        return True

    def reset(self) -> None:
        """Clear all recorded events (used for test isolation)."""
        self._events.clear()


# Shared process-wide limiter instance for the login endpoint.
login_rate_limiter = SlidingWindowRateLimiter()
