"""HealthMonitorCore — central coordination module for Kiro Health Monitor."""

from __future__ import annotations

import logging
import time
from typing import Optional

from src.config.config_manager import ConfigManager
from src.detectors.heartbeat_checker import HeartbeatChecker
from src.detectors.task_status_detector import TaskStatusDetector
from src.detectors.window_resume_detector import WindowResumeDetector
from src.notifications.notification_manager import NotificationManager
from src.types import (
    Alert,
    AlertLevel,
    AlertSummary,
    AlertType,
    CheckResult,
    CheckSource,
    HeartbeatInfo,
    HeartbeatResult,
    HealthReport,
    HealthStatus,
    StallCheckResult,
    TaskInfo,
    WindowInfo,
)

logger = logging.getLogger(__name__)


class HealthMonitorCore:
    """Central coordination module integrating all health-check components.

    Satisfies the ``IHealthMonitorCore`` protocol defined in ``src.types``.
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        notification_manager: NotificationManager,
        heartbeat_checker: HeartbeatChecker,
        task_status_detector: TaskStatusDetector,
        window_resume_detector: WindowResumeDetector,
    ) -> None:
        self._config_manager = config_manager
        self._notification_manager = notification_manager
        self._heartbeat_checker = heartbeat_checker
        self._task_status_detector = task_status_detector
        self._window_resume_detector = window_resume_detector

        # Internal state
        self._status: HealthStatus = HealthStatus.HEALTHY
        self._previous_status: HealthStatus = HealthStatus.HEALTHY
        self._start_time: float = 0.0
        self._last_heartbeat_result: Optional[HeartbeatResult] = None

    # ------------------------------------------------------------------
    # Public API — IHealthMonitorCore
    # ------------------------------------------------------------------

    def get_health_status(self) -> HealthStatus:
        """Return the current health status."""
        return self._status

    def perform_health_check(self) -> HealthReport:
        """Execute a full health check and return a HealthReport."""
        heartbeat_info = self._get_heartbeat_info()
        stall_results = self._task_status_detector.check_for_stalls()
        window_info = self._get_window_info()
        alert_summary = self._get_alert_summary()
        recommendations = self._generate_recommendations(
            self._status, heartbeat_info, stall_results
        )

        return HealthReport(
            status=self._status,
            timestamp=time.time(),
            heartbeat=heartbeat_info,
            tasks=TaskInfo(
                active_count=sum(1 for r in stall_results if not r.is_stalled),
                stalled_tasks=[r for r in stall_results if r.is_stalled],
            ),
            window=window_info,
            alert_summary=alert_summary,
            recommendations=recommendations,
        )

    def perform_deep_health_check(self) -> HealthReport:
        """Execute a deep health check (logs that it's a deep check)."""
        logger.info("Performing deep health check")
        return self.perform_health_check()

    def update_status(self, source: CheckSource, result: CheckResult) -> None:
        """Update health status based on a check result."""
        if isinstance(result, HeartbeatResult):
            self._handle_heartbeat_result(result)
        elif isinstance(result, StallCheckResult):
            self._handle_stall_result(result)

    async def start(self) -> None:
        """Start monitoring: heartbeat checker and window resume detector."""
        self._start_time = time.time()
        config = self._config_manager.get_config()

        # Start heartbeat checker with configured interval
        await self._heartbeat_checker.start(config.heartbeat_interval)

        # Start window resume detector
        self._window_resume_detector.start_listening()
        self._window_resume_detector.on_resume(self._on_window_resume)

        logger.info("HealthMonitorCore started")

    async def stop(self) -> None:
        """Stop monitoring."""
        await self._heartbeat_checker.stop()
        self._window_resume_detector.stop_listening()
        logger.info("HealthMonitorCore stopped")

    # ------------------------------------------------------------------
    # Internal — heartbeat handling
    # ------------------------------------------------------------------

    def _handle_heartbeat_result(self, result: HeartbeatResult) -> None:
        """Process a heartbeat check result and update status accordingly."""
        self._last_heartbeat_result = result
        self._previous_status = self._status

        if result.success:
            self._status = HealthStatus.HEALTHY
            # Check for recovery: was previously unresponsive
            if self._previous_status == HealthStatus.UNRESPONSIVE:
                self._notification_manager.send_recovery_notification(
                    "服务已恢复正常响应"
                )
        elif result.error and not result.error.startswith("Heartbeat timed out"):
            # Network exception → degraded
            self._status = HealthStatus.DEGRADED
        else:
            # Timeout → unresponsive
            self._status = HealthStatus.UNRESPONSIVE

        # Send alert if consecutive timeouts >= 2
        consecutive = self._heartbeat_checker.get_consecutive_timeouts()
        if consecutive >= 2:
            self._notification_manager.send_alert(
                Alert(
                    type=AlertType.HEARTBEAT_TIMEOUT,
                    level=AlertLevel.CRITICAL,
                    message=f"连续 {consecutive} 次心跳超时",
                    description=f"后台服务已连续 {consecutive} 次未在超时时间内响应心跳探测",
                    suggested_action="建议检查后台服务状态，必要时重启 Kiro IDE",
                )
            )

        # Handle auto retry for stalled tasks when unresponsive
        if self._status == HealthStatus.UNRESPONSIVE:
            stall_results = self._task_status_detector.check_for_stalls()
            for stall in stall_results:
                if stall.is_stalled:
                    self._handle_auto_retry(stall.task_id)

    def _handle_stall_result(self, result: StallCheckResult) -> None:
        """Process a stall check result."""
        if result.is_stalled:
            self._notification_manager.send_alert(
                Alert(
                    type=AlertType.TASK_STALL,
                    level=AlertLevel.WARNING,
                    message=f"任务 {result.task_id} 疑似卡顿",
                    description=(
                        f"任务 {result.task_id} 已 {result.stall_duration:.0f}ms 无进度更新"
                    ),
                    suggested_action="建议取消当前任务后重新执行",
                    related_task_id=result.task_id,
                )
            )
            self._handle_auto_retry(result.task_id)

    # ------------------------------------------------------------------
    # Internal — auto retry
    # ------------------------------------------------------------------

    def _handle_auto_retry(self, task_id: str) -> None:
        """Handle auto-retry logic for a stalled/unresponsive task."""
        config = self._config_manager.get_config()
        if config.auto_retry != "on":
            return

        # Look up the tracked task to check retry count
        task = self._task_status_detector._tasks.get(task_id)
        if task is None:
            return

        if task.auto_retry_disabled:
            return

        if task.retry_count < 3:
            task.retry_count += 1
            try:
                self._notification_manager.send_alert(
                    Alert(
                        type=AlertType.AUTO_RETRY_TRIGGERED,
                        level=AlertLevel.INFO,
                        message=f"自动重试任务 {task.name}（第 {task.retry_count} 次）",
                        description=(
                            f"检测到任务 {task.name} 无响应，已自动取消并重新执行"
                        ),
                        suggested_action="无需操作，系统已自动处理",
                        related_task_id=task_id,
                    )
                )
            except Exception:
                logger.exception(
                    "Auto retry notification failed for task %s", task_id
                )
                self._notification_manager.send_alert(
                    Alert(
                        type=AlertType.AUTO_RETRY_FAILED,
                        level=AlertLevel.WARNING,
                        message=f"自动重试任务 {task.name} 时发生异常",
                        description=f"自动重试任务 {task.name} 时发生异常，请手动介入",
                        suggested_action="请手动取消任务并重新执行",
                        related_task_id=task_id,
                    )
                )
        else:
            # Retry limit reached
            task.auto_retry_disabled = True
            self._notification_manager.send_alert(
                Alert(
                    type=AlertType.AUTO_RETRY_LIMIT_REACHED,
                    level=AlertLevel.WARNING,
                    message=f"任务 {task.name} 已达到自动重试上限（3 次）",
                    description=(
                        f"任务 {task.name} 已自动重试 3 次仍未恢复，"
                        "已禁用该任务的自动重试"
                    ),
                    suggested_action="请手动检查任务状态并决定后续操作",
                    related_task_id=task_id,
                )
            )

    # ------------------------------------------------------------------
    # Internal — recommendations
    # ------------------------------------------------------------------

    def _generate_recommendations(
        self,
        status: HealthStatus,
        heartbeat_info: HeartbeatInfo,
        stall_results: list[StallCheckResult],
    ) -> list[str]:
        """Generate recommendations based on current anomalies."""
        recommendations: list[str] = []

        if status == HealthStatus.UNRESPONSIVE:
            recommendations.append("建议取消当前任务并重新执行")
        elif status == HealthStatus.DEGRADED:
            recommendations.append("网络连接可能不稳定，建议检查网络状态")

        for result in stall_results:
            if result.is_stalled:
                # Look up task name from detector
                task = self._task_status_detector._tasks.get(result.task_id)
                name = task.name if task else result.task_id
                recommendations.append(
                    f"任务 {name} 疑似卡顿，建议取消后重新执行"
                )

        return recommendations

    # ------------------------------------------------------------------
    # Internal — window resume callback
    # ------------------------------------------------------------------

    def _on_window_resume(self, duration_ms: float) -> None:
        """Handle window resume event."""
        if duration_ms > 600_000:
            report = self.perform_deep_health_check()
        else:
            report = self.perform_health_check()

        if report.status == HealthStatus.UNRESPONSIVE:
            self._notification_manager.send_alert(
                Alert(
                    type=AlertType.SERVICE_UNRESPONSIVE,
                    level=AlertLevel.CRITICAL,
                    message="窗口恢复后检测到服务无响应",
                    description="IDE 窗口恢复后健康检查发现后台服务无响应",
                    suggested_action="建议重新连接或重启 Kiro IDE",
                )
            )
        elif report.status == HealthStatus.HEALTHY:
            logger.info("Window resumed — all services healthy")

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _get_heartbeat_info(self) -> HeartbeatInfo:
        """Build HeartbeatInfo from the latest heartbeat result."""
        if self._last_heartbeat_result is not None:
            return HeartbeatInfo(
                last_check_time=self._last_heartbeat_result.timestamp,
                last_latency=self._last_heartbeat_result.latency,
                consecutive_timeouts=self._heartbeat_checker.get_consecutive_timeouts(),
            )
        return HeartbeatInfo(
            last_check_time=0.0,
            last_latency=0.0,
            consecutive_timeouts=0,
        )

    def _get_window_info(self) -> WindowInfo:
        """Build WindowInfo from the window resume detector."""
        bg_duration = self._window_resume_detector.get_background_duration()
        is_active = bg_duration is None  # no background timestamp means active
        return WindowInfo(
            is_active=is_active,
            active_duration=(time.time() - self._start_time) * 1000
            if self._start_time
            else 0.0,
            last_background_time=self._window_resume_detector._background_timestamp,
        )

    def _get_alert_summary(self) -> AlertSummary:
        """Build AlertSummary from notification manager history."""
        all_alerts = self._notification_manager.get_alert_history()
        # Recent = last 10
        recent = all_alerts[-10:] if len(all_alerts) > 10 else list(all_alerts)
        return AlertSummary(
            recent_alerts=recent,
            total_alerts=len(all_alerts),
        )
