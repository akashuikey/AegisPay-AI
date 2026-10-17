"""Unit tests for the in-process sliding-window rate limiter (P2-A9)."""

from app.core.rate_limit import SlidingWindowRateLimiter


def test_allows_up_to_limit_then_blocks() -> None:
    limiter = SlidingWindowRateLimiter()
    assert all(limiter.check_and_record("ip-1", max_events=3, window_seconds=60) for _ in range(3))
    # Fourth event in the window is blocked.
    assert limiter.check_and_record("ip-1", max_events=3, window_seconds=60) is False


def test_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter()
    assert limiter.check_and_record("ip-1", 1, 60) is True
    assert limiter.check_and_record("ip-1", 1, 60) is False
    # A different client key is unaffected.
    assert limiter.check_and_record("ip-2", 1, 60) is True


def test_zero_limit_disables_throttle() -> None:
    limiter = SlidingWindowRateLimiter()
    assert all(limiter.check_and_record("ip-1", max_events=0, window_seconds=60) for _ in range(50))


def test_reset_clears_state() -> None:
    limiter = SlidingWindowRateLimiter()
    assert limiter.check_and_record("ip-1", 1, 60) is True
    assert limiter.check_and_record("ip-1", 1, 60) is False
    limiter.reset()
    assert limiter.check_and_record("ip-1", 1, 60) is True
