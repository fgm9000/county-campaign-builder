"""Rate limiter and client IP extraction."""

from county_campaign_builder.limits import StrictRateLimiter, client_ip

DAY = 86400.0


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_sliding_window_allows_up_to_the_limit_then_denies_with_retry_after() -> None:
    clock = Clock(1000.0)
    limiter = StrictRateLimiter(2, 100, clock)
    assert limiter.check("a").is_allowed
    clock.now = 1010.0
    assert limiter.check("a").is_allowed
    clock.now = 1020.0
    denied = limiter.check("a")
    assert not denied.is_allowed
    assert denied.retry_after_seconds == 40
    clock.now = 1060.0
    assert limiter.check("a").is_allowed


def test_each_key_has_its_own_window() -> None:
    limiter = StrictRateLimiter(1, 100, Clock(5.0))
    assert limiter.check("a").is_allowed
    assert limiter.check("b").is_allowed
    assert not limiter.check("a").is_allowed


def test_retry_after_is_at_least_one_second() -> None:
    clock = Clock(100.0)
    limiter = StrictRateLimiter(1, 100, clock)
    limiter.check("a")
    clock.now = 159.9999
    assert limiter.check("a").retry_after_seconds == 1


def test_daily_quota_is_global_and_resets_on_the_next_utc_day() -> None:
    clock = Clock(DAY * 10 + 3600)
    limiter = StrictRateLimiter(10, 2, clock)
    assert limiter.check("a").is_allowed
    assert limiter.check("b").is_allowed
    denied = limiter.check("c")
    assert not denied.is_allowed
    assert denied.retry_after_seconds == int(DAY - 3600)
    clock.now = DAY * 11 + 1
    assert limiter.check("c").is_allowed


def test_a_denied_request_does_not_use_the_quota() -> None:
    limiter = StrictRateLimiter(1, 2, Clock(1.0))
    assert limiter.check("a").is_allowed
    assert not limiter.check("a").is_allowed
    assert limiter.check("b").is_allowed


def test_idle_keys_are_pruned_when_too_many_are_tracked() -> None:
    clock = Clock(0.0)
    limiter = StrictRateLimiter(1, 1000, clock, max_keys=2)
    for key in ("a", "b"):
        limiter.check(key)
    clock.now = 120.0
    limiter.check("c")
    assert limiter.check("a").is_allowed


def test_client_ip_uses_the_last_non_empty_forwarded_value() -> None:
    assert client_ip("6.6.6.6, 1.1.1.1 ,2.2.2.2", "9.9.9.9") == "2.2.2.2"
    assert client_ip("1.1.1.1, ,", "9.9.9.9") == "1.1.1.1"


def test_client_ip_falls_back_to_peer_then_unknown() -> None:
    assert client_ip(None, "9.9.9.9") == "9.9.9.9"
    assert client_ip(" , ", "9.9.9.9") == "9.9.9.9"
    assert client_ip("", None) == "unknown"
