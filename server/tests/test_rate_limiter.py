"""Tests for rate limiter."""

from code_monet.rate_limiter import RateLimiter, RateLimiterConfig


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_allows_requests_under_limit(self) -> None:
        """Requests under the limit should be allowed."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=5, window_seconds=60.0))
        user_id = "1"

        for i in range(5):
            assert limiter.is_allowed(user_id, now=float(i)), f"Request {i + 1} should be allowed"

    def test_blocks_requests_over_limit(self) -> None:
        """Requests over the limit should be blocked."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=3, window_seconds=60.0))
        user_id = "1"

        # First 3 should pass
        for i in range(3):
            assert limiter.is_allowed(user_id, now=float(i))

        # 4th should be blocked
        assert not limiter.is_allowed(user_id, now=3.0)

    def test_window_expiration(self) -> None:
        """Old requests should expire and allow new ones."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=2, window_seconds=10.0))
        user_id = "1"

        # Use up the limit at t=0
        assert limiter.is_allowed(user_id, now=0.0)
        assert limiter.is_allowed(user_id, now=1.0)
        assert not limiter.is_allowed(user_id, now=2.0)

        # After window expires, should be allowed again
        assert limiter.is_allowed(user_id, now=11.0)  # First request expired
        assert limiter.is_allowed(user_id, now=12.0)  # Second request expired
        assert not limiter.is_allowed(user_id, now=12.5)  # Back at limit

    def test_separate_keys(self) -> None:
        """Different keys should have separate limits."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=2, window_seconds=60.0))

        # User 1 uses their limit
        assert limiter.is_allowed("1", now=0.0)
        assert limiter.is_allowed("1", now=1.0)
        assert not limiter.is_allowed("1", now=2.0)

        # User 2 should still be allowed
        assert limiter.is_allowed("2", now=2.0)
        assert limiter.is_allowed("2", now=3.0)
        assert not limiter.is_allowed("2", now=4.0)

    def test_remaining_count(self) -> None:
        """Remaining should accurately report available requests."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=5, window_seconds=60.0))
        user_id = "1"

        assert limiter.remaining(user_id, now=0.0) == 5

        limiter.is_allowed(user_id, now=1.0)
        assert limiter.remaining(user_id, now=1.0) == 4

        limiter.is_allowed(user_id, now=2.0)
        limiter.is_allowed(user_id, now=3.0)
        assert limiter.remaining(user_id, now=3.0) == 2

    def test_remaining_after_expiration(self) -> None:
        """Remaining should account for expired requests."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=3, window_seconds=10.0))
        user_id = "1"

        limiter.is_allowed(user_id, now=0.0)
        limiter.is_allowed(user_id, now=5.0)
        assert limiter.remaining(user_id, now=5.0) == 1

        # After first request expires
        assert limiter.remaining(user_id, now=11.0) == 2

    def test_reset_key(self) -> None:
        """Reset should clear limits for a specific key."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=2, window_seconds=60.0))

        limiter.is_allowed("1", now=0.0)
        limiter.is_allowed("1", now=1.0)
        assert not limiter.is_allowed("1", now=2.0)

        limiter.reset("1")
        assert limiter.is_allowed("1", now=3.0)

    def test_reset_all(self) -> None:
        """Reset all should clear all limits."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=1, window_seconds=60.0))

        limiter.is_allowed("1", now=0.0)
        limiter.is_allowed("2", now=0.0)
        assert not limiter.is_allowed("1", now=1.0)
        assert not limiter.is_allowed("2", now=1.0)

        limiter.reset_all()
        assert limiter.is_allowed("1", now=2.0)
        assert limiter.is_allowed("2", now=2.0)

    def test_zero_remaining_at_limit(self) -> None:
        """Remaining should be zero when at limit."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=2, window_seconds=60.0))
        user_id = "1"

        limiter.is_allowed(user_id, now=0.0)
        limiter.is_allowed(user_id, now=1.0)
        assert limiter.remaining(user_id, now=1.0) == 0

    def test_sliding_window_partial_expiration(self) -> None:
        """Window should slide, expiring requests one by one."""
        limiter = RateLimiter(RateLimiterConfig(max_requests=3, window_seconds=10.0))
        user_id = "1"

        # Requests at t=0, t=5, t=8
        limiter.is_allowed(user_id, now=0.0)
        limiter.is_allowed(user_id, now=5.0)
        limiter.is_allowed(user_id, now=8.0)
        assert not limiter.is_allowed(user_id, now=9.0)

        # At t=11, first request expired (t=0), so one slot available
        assert limiter.is_allowed(user_id, now=11.0)
        assert not limiter.is_allowed(user_id, now=11.5)

        # At t=16, second request expired (t=5), so one slot available
        assert limiter.is_allowed(user_id, now=16.0)
