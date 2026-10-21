import pytest

from webapp.ratelimit import RateLimiter


class Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_requests_under_the_limit_are_allowed():
    limiter = RateLimiter(limit=5, window=10, clock=Clock())
    assert all(limiter.allow("1.2.3.4") for _ in range(3))


def test_keys_are_counted_separately():
    limiter = RateLimiter(limit=2, window=10, clock=Clock())
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert limiter.allow("a")
    assert limiter.allow("b")


def test_a_flood_is_cut_off():
    limiter = RateLimiter(limit=2, window=10, clock=Clock())
    results = [limiter.allow("a") for _ in range(10)]
    assert not results[-1]


def test_old_requests_leave_the_window():
    clock = Clock()
    limiter = RateLimiter(limit=2, window=10, clock=clock)
    for _ in range(10):
        limiter.allow("a")
    clock.now = 10
    assert limiter.allow("a")
    assert limiter.retry_after("b") == 0.0


def test_reset_forgets_a_key():
    limiter = RateLimiter(limit=1, window=10, clock=Clock())
    for _ in range(5):
        limiter.allow("a")
    limiter.reset("a")
    assert limiter.allow("a")


def test_bad_settings_are_rejected():
    with pytest.raises(ValueError):
        RateLimiter(limit=0, window=1)
    with pytest.raises(ValueError):
        RateLimiter(limit=1, window=0)
