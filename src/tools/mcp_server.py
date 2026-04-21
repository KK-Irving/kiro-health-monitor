"""MCP Server setup and tool registration for Kiro Health Monitor."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.config.config_manager import ConfigManager
from src.core.health_monitor_core import HealthMonitorCore
from src.detectors.heartbeat_checker import HeartbeatChecker
from src.detectors.task_status_detector import TaskStatusDetector
from src.detectors.window_resume_detector import WindowResumeDetector
from src.notifications.notification_manager import NotificationManager
from src.types import AlertFilter, AlertType


def create_server() -> FastMCP:
    """Create and configure the MCP server with all tools registered.

    Instantiates all component modules and registers four MCP tools:
    check_health, get_status, configure_monitor, get_alert_history.
    """
    # -- Instantiate components --
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

    # -- Create MCP server --
    mcp = FastMCP("kiro-health-monitor")

    # -- Tool: check_health --
    @mcp.tool()
    def check_health() -> dict:
        """Execute an instant health check and return the full health report.

        Returns a complete HealthReport including status, heartbeat info,
        task info, window info, alert summary, and recommendations.
        """
        report = health_monitor_core.perform_health_check()
        return dataclasses.asdict(report)

    # -- Tool: get_status --
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

        active_count = sum(1 for r in stall_results if not r.is_stalled)
        stalled_count = sum(1 for r in stall_results if r.is_stalled)

        return {
            "status": status.value,
            "last_heartbeat": last_heartbeat_iso,
            "last_heartbeat_latency": heartbeat_info.last_latency,
            "active_task_count": active_count,
            "stalled_task_count": stalled_count,
        }

    # -- Tool: configure_monitor --
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

    # -- Tool: get_alert_history --
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
