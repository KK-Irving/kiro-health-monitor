# Kiro Health Monitor

Kiro IDE health monitor Power — an MCP Server-based Power that proactively detects IDE health status and responsiveness.

## The Problem

Common issues when using Kiro IDE:

1. **Frozen tasks** — UI shows loading spinner but the task is actually stuck, requiring manual cancel and retry
2. **Background sleep** — Minimizing IDE for a while then switching back, services may have disconnected
3. **No visibility** — Users can't tell if the IDE is working normally or stuck

This Power uses background heartbeat detection, task stall monitoring, and window resume detection to proactively discover and alert on abnormal states.

## Features

- **Background heartbeat** — Automatic health check loop runs every 5 minutes (configurable), outputs status to MCP Logs panel
- **Task stall detection** — Monitors task progress, distinguishes normal long-running tasks from truly stuck ones
- **Window resume detection** — Auto-checks service status when switching back to IDE, deep check if away > 10 minutes
- **Health reports** — Structured JSON reports with recommendations for abnormal indicators
- **Auto-retry** — Optional (off by default), auto-retries stuck tasks up to 3 times
- **Alert dedup** — Same alert type suppressed within 5-minute window

## Project Structure

```
kiro-health-monitor/
├── kiro_health_monitor/
│   ├── __init__.py
│   ├── __main__.py                 # Entry point
│   ├── log.py                      # Unified logging
│   ├── types.py                    # Data models and interfaces
│   ├── config/
│   │   └── config_manager.py       # Config management with validation
│   ├── core/
│   │   └── health_monitor_core.py  # Core coordination module
│   ├── detectors/
│   │   ├── heartbeat_checker.py    # Heartbeat detection
│   │   ├── task_status_detector.py # Task stall detection
│   │   └── window_resume_detector.py # Window resume detection
│   ├── notifications/
│   │   └── notification_manager.py # Alert notification with dedup
│   └── tools/
│       └── mcp_server.py           # MCP Server + tool registration + background loop
├── tests/
│   ├── test_background_heartbeat.py # Background heartbeat tests
│   └── test_integration.py          # Integration tests
├── mcp.json                         # MCP server config for Kiro
├── POWER.md                         # Power documentation
├── pyproject.toml                   # Project config
└── README.md
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `check_health` | Full health report (status, heartbeat, tasks, window, alerts, recommendations) |
| `get_status` | Quick status summary (status, latency, active/stalled task counts) |
| `configure_monitor` | Adjust config at runtime |
| `get_alert_history` | Query alert history with optional filters |

## Configuration

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `heartbeat_interval` | 300 | [10, 300] | Heartbeat interval in seconds (5 min default) |
| `response_timeout` | 5 | [1, 30] | Response timeout in seconds |
| `stall_threshold` | 60 | [10, 600] | Stall detection threshold in seconds |
| `auto_retry` | `off` | `on`/`off` | Auto-retry alert switch |

## Install

```bash
pip install kiro-health-monitor
```

### Kiro MCP Config

The `mcp.json` in this repo is automatically used by Kiro when the Power is installed. For manual setup, add to `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "kiro-health-monitor": {
      "command": "python",
      "args": ["-m", "kiro_health_monitor"],
      "disabled": false,
      "autoApprove": ["check_health", "get_status"]
    }
  }
}
```

### Run Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Architecture

```
Kiro IDE ──> MCP Server (kiro-health-monitor)
              ├── Background Heartbeat Loop (stderr logging to MCP Logs)
              ├── HeartbeatChecker (asyncio heartbeat)
              ├── TaskStatusDetector (task progress monitoring)
              ├── WindowResumeDetector (window focus events)
              ├── HealthMonitorCore (core coordination)
              ├── NotificationManager (alert dedup + history)
              └── ConfigManager (validation + dynamic config)
```

## License

MIT
