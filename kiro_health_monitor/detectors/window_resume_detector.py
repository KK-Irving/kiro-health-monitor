"""Window resume detector – tracks when the IDE window goes to/from background."""

import time
from typing import Callable, Optional

from kiro_health_monitor.log import log



class WindowResumeDetector:
    """Detects IDE window resume events and triggers health checks.

    Implements the IWindowResumeDetector protocol defined in src.types.
    """

    def __init__(self) -> None:
        self._listening: bool = False
        self._background_timestamp: Optional[float] = None
        self._callbacks: list[Callable[[float], None]] = []

    # -- IWindowResumeDetector protocol methods --

    def start_listening(self) -> None:
        """Start listening for window events."""
        self._listening = True
        log.info("WindowResumeDetector: started listening")

    def stop_listening(self) -> None:
        """Stop listening for window events."""
        self._listening = False
        log.info("WindowResumeDetector: stopped listening")

    def record_background_timestamp(self) -> None:
        """Record the current time as the moment the window went to background."""
        self._background_timestamp = time.time()
        log.debug(
            "WindowResumeDetector: background timestamp recorded at %s",
            self._background_timestamp,
        )

    def get_background_duration(self) -> Optional[float]:
        """Return how long the window has been in the background (milliseconds).

        Returns None if no background timestamp has been recorded.
        """
        if self._background_timestamp is None:
            return None
        return (time.time() - self._background_timestamp) * 1000

    def on_resume(self, callback: Callable[[float], None]) -> None:
        """Register a callback to be invoked when the window resumes.

        The callback receives the background duration in milliseconds.
        """
        self._callbacks.append(callback)

    # -- Helper / simulation methods --

    def simulate_resume(self) -> None:
        """Simulate a window resume event.

        Calculates the background duration, invokes all registered callbacks,
        and resets the background timestamp.
        """
        if self._background_timestamp is None:
            duration_ms = 0.0
        else:
            duration_ms = (time.time() - self._background_timestamp) * 1000

        log.info(
            "WindowResumeDetector: simulating resume (duration=%.1f ms)",
            duration_ms,
        )

        for cb in self._callbacks:
            try:
                cb(duration_ms)
            except Exception:
                log.exception("WindowResumeDetector: callback error")

        self._background_timestamp = None

    # -- Static utility --

    @staticmethod
    def should_deep_check(duration_ms: float) -> bool:
        """Return True if the background duration warrants a deep health check.

        Threshold: > 600 000 ms (10 minutes).
        """
        return duration_ms > 600_000
