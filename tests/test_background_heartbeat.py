"""Test background heartbeat loop logging behavior."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kiro_health_monitor.config.config_manager import ConfigManager
from kiro_health_monitor.core.health_monitor_core import HealthMonitorCore
from kiro_health_monitor.detectors.heartbeat_checker import HeartbeatChecker
from kiro_health_monitor.detectors.task_status_detector import TaskStatusDetector
from kiro_health_monitor.detectors.window_resume_detector import WindowResumeDetector
from kiro_health_monitor.notifications.notification_manager import NotificationManager
from kiro_health_monitor.types import HealthStatus


def _make_components():
    config_mgr = ConfigManager()
    config_mgr.update_config({"heartbeat_interval": 10})
    notif_mgr = NotificationManager()
    config = config_mgr.get_config()
    hb = HeartbeatChecker(response_timeout=config.response_timeout)
    tsd = TaskStatusDetector(stall_threshold=config.stall_threshold)
    wrd = WindowResumeDetector()
    core = HealthMonitorCore(
        config_manager=config_mgr,
        notification_manager=notif_mgr,
        heartbeat_checker=hb,
        task_status_detector=tsd,
        window_resume_detector=wrd,
    )
    return core, config_mgr


@patch("kiro_health_monitor.tools.mcp_server.asyncio.sleep", new_callable=AsyncMock)
@patch("kiro_health_monitor.tools.mcp_server.log")
def test_sends_info_on_unresponsive(mock_log, mock_sleep):
    from kiro_health_monitor.tools.mcp_server import _background_heartbeat_loop

    core, config_mgr = _make_components()
    mock_report = MagicMock()
    mock_report.status = HealthStatus.UNRESPONSIVE
    mock_report.tasks.stalled_tasks = []
    core.perform_health_check = MagicMock(return_value=mock_report)

    call_count = 0
    async def limited_sleep(s):
        nonlocal call_count
        call_count += 1
        if call_count > 2:
            raise asyncio.CancelledError()
    mock_sleep.side_effect = limited_sleep

    async def run():
        try:
            await _background_heartbeat_loop(core, config_mgr)
        except asyncio.CancelledError:
            pass
        calls = [str(c) for c in mock_log.info.call_args_list]
        assert any("UNRESPONSIVE" in c for c in calls), f"Expected UNRESPONSIVE log, got: {calls}"

    asyncio.run(run())


@patch("kiro_health_monitor.tools.mcp_server.asyncio.sleep", new_callable=AsyncMock)
@patch("kiro_health_monitor.tools.mcp_server.log")
def test_sends_info_on_degraded(mock_log, mock_sleep):
    from kiro_health_monitor.tools.mcp_server import _background_heartbeat_loop

    core, config_mgr = _make_components()
    mock_report = MagicMock()
    mock_report.status = HealthStatus.DEGRADED
    mock_report.tasks.stalled_tasks = []
    core.perform_health_check = MagicMock(return_value=mock_report)

    call_count = 0
    async def limited_sleep(s):
        nonlocal call_count
        call_count += 1
        if call_count > 2:
            raise asyncio.CancelledError()
    mock_sleep.side_effect = limited_sleep

    async def run():
        try:
            await _background_heartbeat_loop(core, config_mgr)
        except asyncio.CancelledError:
            pass
        calls = [str(c) for c in mock_log.info.call_args_list]
        assert any("DEGRADED" in c for c in calls), f"Expected DEGRADED log, got: {calls}"

    asyncio.run(run())


@patch("kiro_health_monitor.tools.mcp_server.asyncio.sleep", new_callable=AsyncMock)
@patch("kiro_health_monitor.tools.mcp_server.log")
def test_sends_heartbeat_ok_on_healthy(mock_log, mock_sleep):
    from kiro_health_monitor.tools.mcp_server import _background_heartbeat_loop

    core, config_mgr = _make_components()
    mock_report = MagicMock()
    mock_report.status = HealthStatus.HEALTHY
    mock_report.tasks.stalled_tasks = []
    core.perform_health_check = MagicMock(return_value=mock_report)

    call_count = 0
    async def limited_sleep(s):
        nonlocal call_count
        call_count += 1
        if call_count > 2:
            raise asyncio.CancelledError()
    mock_sleep.side_effect = limited_sleep

    async def run():
        try:
            await _background_heartbeat_loop(core, config_mgr)
        except asyncio.CancelledError:
            pass
        calls = [str(c) for c in mock_log.info.call_args_list]
        assert any("Heartbeat OK" in c for c in calls), f"Expected Heartbeat OK log, got: {calls}"

    asyncio.run(run())


@patch("kiro_health_monitor.tools.mcp_server.asyncio.sleep", new_callable=AsyncMock)
@patch("kiro_health_monitor.tools.mcp_server.log")
def test_sends_recovery_after_failure(mock_log, mock_sleep):
    from kiro_health_monitor.tools.mcp_server import _background_heartbeat_loop

    core, config_mgr = _make_components()
    bad = MagicMock()
    bad.status = HealthStatus.UNRESPONSIVE
    bad.tasks.stalled_tasks = []
    good = MagicMock()
    good.status = HealthStatus.HEALTHY
    good.tasks.stalled_tasks = []
    core.perform_health_check = MagicMock(side_effect=[bad, good])

    call_count = 0
    async def limited_sleep(s):
        nonlocal call_count
        call_count += 1
        if call_count > 3:
            raise asyncio.CancelledError()
    mock_sleep.side_effect = limited_sleep

    async def run():
        try:
            await _background_heartbeat_loop(core, config_mgr)
        except asyncio.CancelledError:
            pass
        calls = [str(c) for c in mock_log.info.call_args_list]
        assert any("UNRESPONSIVE" in c for c in calls), f"Expected UNRESPONSIVE: {calls}"
        assert any("RECOVERED" in c for c in calls), f"Expected RECOVERED: {calls}"

    asyncio.run(run())
