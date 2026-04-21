"""HeartbeatChecker — periodic heartbeat detection for Kiro Health Monitor."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

from src.types import HeartbeatResult

logger = logging.getLogger(__name__)


class HeartbeatChecker:
    """Periodically pings the event loop and tracks consecutive timeouts.

    Satisfies the ``IHeartbeatChecker`` protocol defined in ``src.types``.
    """

    def __init__(
        self,
        response_timeout: int = 5,
        on_result: Optional[Callable[[HeartbeatResult], None]] = None,
    ) -> None:
        self._response_timeout = response_timeout
        self._on_result = on_result

        # internal state
        self._consecutive_timeouts: int = 0
        self._task: Optional[asyncio.Task[None]] = None
        self._running: bool = False
        self._last_result: Optional[HeartbeatResult] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, interval: int) -> None:
        """Start the heartbeat detection timer.

        Creates an ``asyncio`` background task that calls :meth:`ping` every
        *interval* seconds.
        """
        if self._running:
            logger.warning("HeartbeatChecker is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop(interval))
        logger.info("HeartbeatChecker started with interval=%ds", interval)

    async def stop(self) -> None:
        """Stop heartbeat detection by cancelling the background task."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HeartbeatChecker stopped")

    async def ping(self) -> HeartbeatResult:
        """Execute a single heartbeat check.

        Measures event-loop responsiveness by scheduling a short ``asyncio.sleep``
        and timing how long it actually takes.  If the measured latency is below
        ``response_timeout`` the check succeeds; otherwise it is treated as a
        timeout.
        """
        start = time.monotonic()
        try:
            # Use asyncio.wait_for to enforce the timeout.  The inner
            # coroutine is a minimal sleep(0) — if the event loop is
            # responsive it completes almost instantly.
            await asyncio.wait_for(asyncio.sleep(0), timeout=self._response_timeout)
            end = time.monotonic()
            latency_ms = (end - start) * 1000

            if latency_ms < self._response_timeout * 1000:
                # Success — reset consecutive timeout counter
                self._consecutive_timeouts = 0
                result = HeartbeatResult(
                    success=True,
                    latency=latency_ms,
                    timestamp=time.time(),
                )
            else:
                # Latency exceeded the threshold
                self._consecutive_timeouts += 1
                result = HeartbeatResult(
                    success=False,
                    latency=latency_ms,
                    timestamp=time.time(),
                    error=f"Latency {latency_ms:.1f}ms >= timeout {self._response_timeout * 1000}ms",
                )
        except asyncio.TimeoutError:
            end = time.monotonic()
            latency_ms = (end - start) * 1000
            self._consecutive_timeouts += 1
            result = HeartbeatResult(
                success=False,
                latency=latency_ms,
                timestamp=time.time(),
                error="Heartbeat timed out",
            )
        except Exception as exc:  # noqa: BLE001
            end = time.monotonic()
            latency_ms = (end - start) * 1000
            self._consecutive_timeouts += 1
            result = HeartbeatResult(
                success=False,
                latency=latency_ms,
                timestamp=time.time(),
                error=str(exc),
            )

        self._last_result = result

        # Invoke the callback if one was provided
        if self._on_result is not None:
            try:
                self._on_result(result)
            except Exception:  # noqa: BLE001
                logger.exception("on_result callback raised an exception")

        return result

    def get_consecutive_timeouts(self) -> int:
        """Return the current consecutive timeout count."""
        return self._consecutive_timeouts

    def reset_timeout_count(self) -> None:
        """Reset the consecutive timeout counter to zero."""
        self._consecutive_timeouts = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self, interval: int) -> None:
        """Background loop that calls :meth:`ping` every *interval* seconds."""
        try:
            while self._running:
                await self.ping()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
            raise
