"""MCP Server setup and tool registration for Kiro Health Monitor."""

from __future__ import annotations

import asyncio
import dataclasses
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

from kiro_health_monitor.config.config_manager import ConfigManager
from kiro_health_monitor.core.health_monitor_core import HealthMonitorCore
from kiro_health_monitor.detectors.heartbeat_checker import HeartbeatChecker
from kiro_health_monitor.detectors.task_status_detector import TaskStatusDetector
from kiro_health_monitor.detectors.window_resume_detector import WindowResumeDetector
from kiro_health_monitor.notifications.notification_manager import NotificationManager
from kiro_health_monitor.types import AlertFilter, AlertType, HealthStatus

from kiro_health_monitor.log import log


async def _background_heartbeat_loop(
    health_monitor_core: HealthMonitorCore,
    config_manager: ConfigManager,
) -> None:
    """Background loop that periodically performs health checks.

    Uses Python logging (stderr) which Kiro captures and
    displays in the MCP Logs panel as server log messages.
    """
    await asyncio.sleep(3)
    log.info("Heartbeat loop started")

    consecutive_failures = 0

    while True:
        try:
            interval = config_manager.get_config().heartbeat_interval
            await asyncio.sleep(interval)

            report = health_monitor_core.perform_health_check()
            status = report.status

            if status == HealthStatus.UNRESPONSIVE:
                consecutive_failures += 1
                log.info(
                    "UNRESPONSIVE - %d consecutive failures, "
                    "IDE may be frozen, consider retry or restart",
                    consecutive_failures,
                )
            elif status == HealthStatus.DEGRADED:
                consecutive_failures += 1
                log.info(
                    "DEGRADED - backend responding slowly"
                )
            else:
                if consecutive_failures > 0:
                    log.info(
                        "RECOVERED after %d failures",
                        consecutive_failures,
                    )
                    consecutive_failures = 0
                else:
                    # TODO: testing only, change to debug before release
                    log.info("Heartbeat OK")

            stall_results = report.tasks.stalled_tasks
            if stall_results:
                stalled_ids = [
                    s.task_id for s in stall_results if s.is_stalled
                ]
                if stalled_ids:
                    log.info(
                        "%d stalled task(s): %s",
                        len(stalled_ids),
                        ", ".join(stalled_ids),
                    )

        except asyncio.CancelledError:
            log.info("Heartbeat loop stopped")
            break
        except Exception as e:
            log.info("Heartbeat error: %s", e)
            await asyncio.sleep(10)


# 用于在 lifespan 和 create_server 之间传递组件实例
_lifespan_context: dict = {}


@asynccontextmanager
async def _health_monitor_lifespan(server):
    """Lifespan handler: starts background heartbeat on server startup."""
    ctx = _lifespan_context
    task = asyncio.create_task(
        _background_heartbeat_loop(
            ctx["health_monitor_core"],
            ctx["config_manager"],
        )
    )
    log.info("Health monitor background task started")
    try:
        yield {"background_task": task}
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("Health monitor background task stopped")


def create_server() -> FastMCP:
    """Create and configure the MCP server with all tools registered.

    Starts a background heartbeat loop via lifespan that logs
    health status to stderr (visible in Kiro MCP Logs panel).
    """
    global _lifespan_context

    config_manager = ConfigManager()
    notification_manager = NotificationManager()
    config = config_manager.get_config()
    heartbeat_checker = HeartbeatChecker(response_timeout=config.response_timeout)
    task_status_detector = TaskStatusDetector(stall_threshold=config.stall_threshold)
    window_resume_detector = WindowResumeDetector()

    health_monitor_core = HealthMonitorCore(
        config_manager=config_manager,
        notification_manager=notification_manager,
        heartbeat_checker=heartbeat_checker,
        task_status_detector=task_status_detector,
        window_resume_detector=window_resume_detector,
    )

    _lifespan_context.update({
        "health_monitor_core": health_monitor_core,
        "config_manager": config_manager,
    })

    mcp = FastMCP("kiro-health-monitor", lifespan=_health_monitor_lifespan)

    @mcp.tool()
    def check_health() -> dict:
        """Execute an instant health check and return the full health report.

        Returns a complete HealthReport including status, heartbeat info,
        task info, window info, alert summary, and recommendations.
        """
        report = health_monitor_core.perform_health_check()
        return dataclasses.asdict(report)

    @mcp.tool()
    def get_status() -> dict:
        """Get a concise status summary of the health monitor.

        Returns the current health status, last heartbeat timestamp (ISO),
        last heartbeat latency, active task count, and stalled task count.
        """
        status = health_monitor_core.get_health_status()
        heartbeat_info = health_monitor_core._get_heartbeat_info()
        stall_results = task_status_detector.check_for_stalls()

        last_heartbeat_iso = (
            datetime.fromtimestamp(heartbeat_info.last_check_time, tz=timezone.utc).isoformat()
            if heartbeat_info.last_check_time > 0
            else datetime.fromtimestamp(0, tz=timezone.utc).isoformat()
        )

        return {
            "status": status.value,
            "last_heartbeat": last_heartbeat_iso,
            "last_heartbeat_latency": heartbeat_info.last_latency,
            "active_task_count": sum(1 for r in stall_results if not r.is_stalled),
            "stalled_task_count": sum(1 for r in stall_results if r.is_stalled),
        }

    @mcp.tool()
    def configure_monitor(
        heartbeat_interval: Optional[int] = None,
        response_timeout: Optional[int] = None,
        stall_threshold: Optional[int] = None,
        auto_retry: Optional[str] = None,
    ) -> dict:
        """Dynamically update monitor configuration parameters.

        All parameters are optional. Only provided parameters will be updated.
        Values are validated against allowed ranges before applying.

        Args:
            heartbeat_interval: Heartbeat interval in seconds [10, 300].
            response_timeout: Response timeout in seconds [1, 30].
            stall_threshold: Stall detection threshold in seconds [10, 600].
            auto_retry: Auto-retry mode, 'on' or 'off'.
        """
        partial: dict = {}
        if heartbeat_interval is not None:
            partial["heartbeat_interval"] = heartbeat_interval
        if response_timeout is not None:
            partial["response_timeout"] = response_timeout
        if stall_threshold is not None:
            partial["stall_threshold"] = stall_threshold
        if auto_retry is not None:
            partial["auto_retry"] = auto_retry

        result = config_manager.update_config(partial)
        return dataclasses.asdict(result)

    @mcp.tool()
    def get_alert_history(
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        alert_type: Optional[str] = None,
    ) -> dict:
        """Query historical alert records with optional filtering.

        Args:
            start_time: ISO timestamp for range start (inclusive).
            end_time: ISO timestamp for range end (inclusive).
            alert_type: Filter by alert type (e.g. 'heartbeat_timeout').
        """
        alert_filter = AlertFilter()

        if start_time is not None:
            alert_filter.start_time = datetime.fromisoformat(start_time).timestamp()
        if end_time is not None:
            alert_filter.end_time = datetime.fromisoformat(end_time).timestamp()
        if alert_type is not None:
            alert_filter.alert_type = AlertType(alert_type)

        alerts = notification_manager.get_alert_history(alert_filter)
        return {
            "alerts": [dataclasses.asdict(a) for a in alerts],
            "total": len(alerts),
        }

    return mcp
