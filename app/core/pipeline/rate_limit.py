"""Rate limit gate for async batch operations."""

import asyncio
import time


class RateLimitGate:
    """Pauses all tasks when any one hits a rate limit.

    Safe without locks because asyncio is single-threaded — only one
    coroutine runs at a time between await points.
    """

    def __init__(self) -> None:
        self._resume_at: float = 0

    async def wait_if_paused(self) -> None:
        """Wait until any active rate limit pause expires."""
        remaining = self._resume_at - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)

    def pause(self, seconds: float) -> None:
        """Pause all tasks for at least *seconds* from now."""
        self._resume_at = max(self._resume_at, time.monotonic() + seconds)
