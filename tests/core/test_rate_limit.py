"""Tests for app.core.rate_limit.RateLimitGate."""

import pytest


class TestRateLimitGate:
    """Tests for RateLimitGate."""

    @pytest.mark.asyncio
    async def test_no_pause_by_default(self):
        """Gate does not block when no pause has been set."""
        import time

        from app.core.rate_limit import RateLimitGate

        gate = RateLimitGate()
        before = time.monotonic()
        await gate.wait_if_paused()
        elapsed = time.monotonic() - before
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_pause_causes_wait(self):
        """Gate waits for the paused duration."""
        import time

        from app.core.rate_limit import RateLimitGate

        gate = RateLimitGate()
        gate.pause(0.2)
        before = time.monotonic()
        await gate.wait_if_paused()
        elapsed = time.monotonic() - before
        assert elapsed >= 0.15  # Allow small tolerance

    @pytest.mark.asyncio
    async def test_pause_coalesces(self):
        """Multiple pauses keep the longest remaining duration."""
        import time

        from app.core.rate_limit import RateLimitGate

        gate = RateLimitGate()
        gate.pause(0.1)
        gate.pause(0.3)  # Longer — should win
        gate.pause(0.05)  # Shorter — should not shorten
        before = time.monotonic()
        await gate.wait_if_paused()
        elapsed = time.monotonic() - before
        assert elapsed >= 0.2  # At least ~0.3s from the longest pause
