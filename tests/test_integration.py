"""Integration tests — verify all modules work together end-to-end.

Covers:
1. Heartbeat timeout → alert → auto retry flow
2. Window resume → health check → deep check flow
3. Config change → modules reflect new values
4. Task stall detection → notification flow
5. Alert dedup verification
6. Auto retry limit
7. Recovery notification
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from kiro_health_monitor.config.config_manager import ConfigManager
from kiro_health_monitor.core.health_monitor_core import HealthMonitorCore
from kiro_health_monitor.detectors.heartbeat_checker import HeartbeatChecker
from kiro_health_monitor.detectors.task_status_detector import TaskStatusDetector
from kiro_health_monitor.detectors.window_resume_detector import WindowResumeDetector
from kiro_health_monitor.notifications.notification_manager import NotificationManager
from kiro_health_monitor.types import (
    AlertType,
    CheckSource,
    HealthStatus,
    HeartbeatResult,
    TrackedTask,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def components():
    """Create all components wired together, returning a dict for easy access."""
    config_manager = ConfigManager()
    notification_manager = NotificationManager()
    config = config_manager.get_config()
    heartbeat_checker = HeartbeatChecker(response_timeout=config.response_timeout)
    task_status_detector = TaskStatusDetector(stall_threshold=config.stall_threshold)
    window_resume_detector = WindowResumeDetector()

    core = HealthMonitorCore(
        config_manager=config_manager,
        notification_manager=notification_manager,
        heartbeat_checker=heartbeat_checker,
        task_status_detector=task_status_detector,
        window_resume_detector=window_resume_detector,
    )

    return {
        "core": core,
        "config_manager": config_manager,
        "notification_manager": notification_manager,
        "heartbeat_checker": heartbeat_checker,
        "task_status_detector": task_status_detector,
        "window_resume_detector": window_resume_detector,
    }


# ---------------------------------------------------------------------------
# 1. Heartbeat timeout → alert → auto retry flow
# ---------------------------------------------------------------------------

class TestHeartbeatTimeoutAlertAutoRetry:
    """Heartbeat consecutive timeouts trigger alert; auto_retry triggers retry."""

    def test_alert_after_two_consecutive_timeouts(self, components):
        core = components["core"]
        hb = components["heartbeat_checker"]
        nm = components["notification_manager"]

        # First timeout — no alert yet
        hb._consecutive_timeouts = 1
        failed_result = HeartbeatResult(
            success=False, latency=6000.0, timestamp=time.time(),
            error="Heartbeat timed out",
        )
        core.update_status(CheckSource.HEARTBEAT, failed_result)

        # After first update, consecutive_timeouts was already 1 before update,
        # but _handle_heartbeat_result reads from heartbeat_checker.
        # Manually set to simulate two consecutive timeouts.
        hb._consecutive_timeouts = 2
        core.update_status(CheckSource.HEARTBEAT, failed_result)

        # Should have at least one HEARTBEAT_TIMEOUT alert
        alerts = nm.get_alert_history()
        timeout_alerts = [a for a in alerts if a.type == AlertType.HEARTBEAT_TIMEOUT]
        assert len(timeout_alerts) >= 1

    def test_auto_retry_triggered_on_unresponsive(self, components):
        core = components["core"]
        hb = components["heartbeat_checker"]
        nm = components["notification_manager"]
        tsd = components["task_status_detector"]
        cm = components["config_manager"]

        # Enable auto_retry
        cm.update_config({"auto_retry": "on"})

        # Track a task with old progress (will be stalled)
        now = time.time()
        task = TrackedTask(
            task_id="t1", name="Test Task",
            start_time=now - 200,
            last_progress_update=now - 200,
        )
        tsd.track_task(task)

        # Simulate 2 consecutive timeouts → unresponsive + auto retry
        hb._consecutive_timeouts = 2
        failed_result = HeartbeatResult(
            success=False, latency=6000.0, timestamp=now,
            error="Heartbeat timed out",
        )
        core.update_status(CheckSource.HEARTBEAT, failed_result)

        alerts = nm.get_alert_history()
        retry_alerts = [a for a in alerts if a.type == AlertType.AUTO_RETRY_TRIGGERED]
        assert len(retry_alerts) >= 1
        assert retry_alerts[0].related_task_id == "t1"


# ---------------------------------------------------------------------------
# 2. Window resume → health check → deep check flow
# ---------------------------------------------------------------------------

class TestWindowResumeHealthCheck:
    """Window resume triggers regular or deep health check based on duration."""

    def test_short_resume_triggers_regular_check(self, components):
        core = components["core"]
        wrd = components["window_resume_detector"]

        # Wire up the resume callback (same as core.start would do)
        wrd.on_resume(core._on_window_resume)

        # Record background timestamp, then simulate a short absence (< 10 min)
        with patch("kiro_health_monitor.detectors.window_resume_detector.time") as mock_time:
            mock_time.time.return_value = 1000.0
            wrd.record_background_timestamp()

            # Resume after 60 seconds (60_000 ms < 600_000 ms)
            mock_time.time.return_value = 1060.0
            with patch.object(core, "perform_health_check", wraps=core.perform_health_check) as mock_check, \
                 patch.object(core, "perform_deep_health_check", wraps=core.perform_deep_health_check) as mock_deep:
                wrd.simulate_resume()
                mock_check.assert_called_once()
                mock_deep.assert_not_called()

    def test_long_resume_triggers_deep_check(self, components):
        core = components["core"]
        wrd = components["window_resume_detector"]

        wrd.on_resume(core._on_window_resume)

        # Record background timestamp, then simulate >10 min absence
        with patch("kiro_health_monitor.detectors.window_resume_detector.time") as mock_time:
            mock_time.time.return_value = 1000.0
            wrd.record_background_timestamp()

            # Resume after 11 minutes (660_000 ms > 600_000 ms)
            mock_time.time.return_value = 1660.0
            with patch.object(core, "perform_deep_health_check", wraps=core.perform_deep_health_check) as mock_deep:
                wrd.simulate_resume()
                mock_deep.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Config change → modules reflect new values
# ---------------------------------------------------------------------------

class TestConfigChangeReflected:
    """Updating config via config_manager is visible to all consumers."""

    def test_config_update_returns_new_values(self, components):
        cm = components["config_manager"]

        result = cm.update_config({
            "heartbeat_interval": 60,
            "stall_threshold": 120,
            "auto_retry": "on",
        })

        assert result.success is True
        cfg = cm.get_config()
        assert cfg.heartbeat_interval == 60
        assert cfg.stall_threshold == 120
        assert cfg.auto_retry == "on"

    def test_core_reads_updated_config(self, components):
        cm = components["config_manager"]
        core = components["core"]

        cm.update_config({"auto_retry": "on"})
        # Core reads config dynamically in _handle_auto_retry
        cfg = core._config_manager.get_config()
        assert cfg.auto_retry == "on"


# ---------------------------------------------------------------------------
# 4. Task stall detection → notification flow
# ---------------------------------------------------------------------------

class TestTaskStallNotification:
    """Stall detection produces alerts; progress update clears stall."""

    def test_stall_detected_and_cleared(self, components):
        tsd = components["task_status_detector"]

        now = time.time()
        # Track a task with old progress timestamp (stalled)
        task = TrackedTask(
            task_id="stall-1", name="Stalling Task",
            start_time=now - 200,
            last_progress_update=now - 200,  # 200s ago, well past 60s threshold
        )
        tsd.track_task(task)

        results = tsd.check_for_stalls()
        stalled = [r for r in results if r.task_id == "stall-1"]
        assert len(stalled) == 1
        assert stalled[0].is_stalled is True

        # Update progress → stall should clear
        tsd.update_task_progress("stall-1", time.time())
        results_after = tsd.check_for_stalls()
        stalled_after = [r for r in results_after if r.task_id == "stall-1"]
        assert stalled_after[0].is_stalled is False

    def test_stall_triggers_alert_via_core(self, components):
        core = components["core"]
        tsd = components["task_status_detector"]
        nm = components["notification_manager"]

        now = time.time()
        task = TrackedTask(
            task_id="stall-2", name="Another Stalling Task",
            start_time=now - 200,
            last_progress_update=now - 200,
        )
        tsd.track_task(task)

        stall_results = tsd.check_for_stalls()
        for r in stall_results:
            if r.is_stalled:
                core.update_status(CheckSource.TASK_DETECTOR, r)

        alerts = nm.get_alert_history()
        stall_alerts = [a for a in alerts if a.type == AlertType.TASK_STALL]
        assert len(stall_alerts) >= 1
        assert stall_alerts[0].related_task_id == "stall-2"


# ---------------------------------------------------------------------------
# 5. Alert dedup verification
# ---------------------------------------------------------------------------

class TestAlertDedup:
    """Same alert type within 5 minutes is suppressed."""

    def test_duplicate_suppressed_within_window(self, components):
        nm = components["notification_manager"]
        from kiro_health_monitor.types import Alert, AlertLevel

        alert = Alert(
            type=AlertType.HEARTBEAT_TIMEOUT,
            level=AlertLevel.CRITICAL,
            message="timeout",
            description="desc",
            suggested_action="action",
        )

        first = nm.send_alert(alert)
        second = nm.send_alert(alert)

        assert first is True
        assert second is False  # suppressed

    def test_alert_sent_after_dedup_window(self, components):
        nm = components["notification_manager"]
        from kiro_health_monitor.types import Alert, AlertLevel

        alert = Alert(
            type=AlertType.TASK_STALL,
            level=AlertLevel.WARNING,
            message="stall",
            description="desc",
            suggested_action="action",
        )

        first = nm.send_alert(alert)
        assert first is True

        # Simulate time passing beyond 5-minute window
        with patch("kiro_health_monitor.notifications.notification_manager.time") as mock_time:
            mock_time.time.return_value = time.time() + 301  # > 300s
            second = nm.send_alert(alert)
            assert second is True


# ---------------------------------------------------------------------------
# 6. Auto retry limit
# ---------------------------------------------------------------------------

class TestAutoRetryLimit:
    """Auto retry is blocked after 3 attempts for the same task."""

    def test_fourth_retry_blocked(self, components):
        core = components["core"]
        hb = components["heartbeat_checker"]
        nm = components["notification_manager"]
        tsd = components["task_status_detector"]
        cm = components["config_manager"]

        cm.update_config({"auto_retry": "on"})

        now = time.time()
        task = TrackedTask(
            task_id="retry-task", name="Retry Task",
            start_time=now - 300,
            last_progress_update=now - 300,
        )
        tsd.track_task(task)

        failed_result = HeartbeatResult(
            success=False, latency=6000.0, timestamp=now,
            error="Heartbeat timed out",
        )

        # Trigger 3 retries — each call to update_status with consecutive >= 2
        # will attempt auto retry for stalled tasks.
        for i in range(3):
            hb._consecutive_timeouts = 2
            # Clear dedup so heartbeat alert goes through each time
            nm._last_sent.pop(AlertType.HEARTBEAT_TIMEOUT.value, None)
            core.update_status(CheckSource.HEARTBEAT, failed_result)

        # After 3 retries, retry_count should be 3
        tracked = tsd._tasks["retry-task"]
        assert tracked.retry_count == 3

        # 4th attempt — should be blocked
        hb._consecutive_timeouts = 2
        nm._last_sent.pop(AlertType.HEARTBEAT_TIMEOUT.value, None)
        core.update_status(CheckSource.HEARTBEAT, failed_result)

        assert tracked.auto_retry_disabled is True

        # Verify AUTO_RETRY_LIMIT_REACHED alert was sent
        alerts = nm.get_alert_history()
        limit_alerts = [a for a in alerts if a.type == AlertType.AUTO_RETRY_LIMIT_REACHED]
        assert len(limit_alerts) >= 1


# ---------------------------------------------------------------------------
# 7. Recovery notification
# ---------------------------------------------------------------------------

class TestRecoveryNotification:
    """Transition from unresponsive → healthy sends recovery notification."""

    def test_recovery_after_unresponsive(self, components):
        core = components["core"]
        hb = components["heartbeat_checker"]
        nm = components["notification_manager"]

        now = time.time()

        # Drive status to unresponsive via heartbeat timeout
        hb._consecutive_timeouts = 2
        failed_result = HeartbeatResult(
            success=False, latency=6000.0, timestamp=now,
            error="Heartbeat timed out",
        )
        core.update_status(CheckSource.HEARTBEAT, failed_result)
        assert core.get_health_status() == HealthStatus.UNRESPONSIVE

        # Now send a successful heartbeat
        success_result = HeartbeatResult(
            success=True, latency=10.0, timestamp=now + 30,
        )
        core.update_status(CheckSource.HEARTBEAT, success_result)
        assert core.get_health_status() == HealthStatus.HEALTHY

        # Verify recovery notification was sent
        alerts = nm.get_alert_history()
        recovery_alerts = [a for a in alerts if a.type == AlertType.SERVICE_RECOVERED]
        assert len(recovery_alerts) >= 1
