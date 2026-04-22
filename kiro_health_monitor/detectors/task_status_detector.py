"""TaskStatusDetector — task stall detection for Kiro Health Monitor."""

from __future__ import annotations

import time

from kiro_health_monitor.log import log
from kiro_health_monitor.types import StallCheckResult, TrackedTask



class TaskStatusDetector:
    """Monitors tracked tasks for stalls based on progress timestamps.

    Satisfies the ``ITaskStatusDetector`` protocol defined in ``src.types``.
    """

    def __init__(self, stall_threshold: int = 60) -> None:
        self._stall_threshold: int = stall_threshold
        self._tasks: dict[str, TrackedTask] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def track_task(self, task: TrackedTask) -> None:
        """Register a task for monitoring."""
        self._tasks[task.task_id] = task
        log.info("Tracking task %s (%s)", task.task_id, task.name)

    def untrack_task(self, task_id: str) -> None:
        """Remove a task from monitoring."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            log.info("Untracked task %s", task_id)
        else:
            log.warning("Attempted to untrack unknown task %s", task_id)

    def update_task_progress(self, task_id: str, timestamp: float) -> None:
        """Update the last progress timestamp for a tracked task."""
        if task_id not in self._tasks:
            log.warning("Cannot update progress for unknown task %s", task_id)
            return
        self._tasks[task_id].last_progress_update = timestamp
        log.debug("Updated progress for task %s at %.3f", task_id, timestamp)

    def update_task_log_output(self, task_id: str, timestamp: float) -> None:
        """Update the last log output timestamp for a tracked task."""
        if task_id not in self._tasks:
            log.warning("Cannot update log output for unknown task %s", task_id)
            return
        self._tasks[task_id].last_log_output = timestamp
        log.debug("Updated log output for task %s at %.3f", task_id, timestamp)

    def check_for_stalls(self) -> list[StallCheckResult]:
        """Check all tracked tasks for stalls.

        A task is considered stalled when:
        - stall_duration > stall_threshold (in seconds) AND
        - the task is NOT active (no recent log output)

        Returns a list of :class:`StallCheckResult` for every tracked task.
        """
        now = time.time()
        results: list[StallCheckResult] = []

        for task_id, task in self._tasks.items():
            stall_duration_ms = (now - task.last_progress_update) * 1000
            active = self.is_task_active(task_id)
            is_stalled = (
                stall_duration_ms > self._stall_threshold * 1000 and not active
            )

            results.append(
                StallCheckResult(
                    task_id=task_id,
                    is_stalled=is_stalled,
                    stall_duration=stall_duration_ms,
                    is_active=active,
                )
            )

        return results

    def is_task_active(self, task_id: str) -> bool:
        """Check if a task has recent log output.

        A task is considered active if ``last_log_output`` is not ``None`` and
        the time since the last log output is less than ``stall_threshold``.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.last_log_output is None:
            return False

        now = time.time()
        return (now - task.last_log_output) < self._stall_threshold
