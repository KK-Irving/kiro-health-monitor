---
name: "kiro-health-monitor"
displayName: "Kiro Health Monitor"
description: "Kiro IDE health monitor Power with background heartbeat detection, stall detection, and auto-alerting via MCP Logs"
keywords: ["kiro", "health", "monitor", "heartbeat", "stall", "responsive", "watchdog"]
author: "KK-Irving"
---

# Kiro Health Monitor

Background health monitoring for Kiro IDE. Automatically detects unresponsive or degraded states and alerts via MCP Logs panel.

## How It Works

Once installed, the MCP server starts a background heartbeat loop automatically. Every `heartbeat_interval` seconds (default 5 minutes) it runs a health check and outputs status to the MCP Logs panel:

- **Healthy**: `Heartbeat OK`
- **Degraded**: `DEGRADED - backend responding slowly`
- **Unresponsive**: `UNRESPONSIVE - N consecutive failures, IDE may be frozen, consider retry or restart`
- **Recovered**: `RECOVERED after N failures`
- **Stalled tasks**: `N stalled task(s): task-id-1, task-id-2`

No manual action needed. Just install and it runs.

## MCP Tools

| Tool | Description |
|------|-------------|
| `check_health` | Full health report (status, heartbeat, tasks, window, alerts, recommendations) |
| `get_status` | Quick status summary (status, latency, active/stalled task counts) |
| `configure_monitor` | Adjust config at runtime (heartbeat interval, timeout, stall threshold, auto-retry) |
| `get_alert_history` | Query alert history with optional time range and type filters |

## Configuration

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `heartbeat_interval` | int | 300 | [10, 300] | Heartbeat check interval in seconds (default 5 min) |
| `response_timeout` | int | 5 | [1, 30] | Response timeout threshold in seconds |
| `stall_threshold` | int | 60 | [10, 600] | Task stall detection threshold in seconds |
| `auto_retry` | string | `off` | `on` / `off` | Alert notifications for stalled tasks when enabled |

Use `configure_monitor` to adjust at runtime. Out-of-range values are rejected with error messages.

## Optional: One-Click Health Check Hook

Create `.kiro/hooks/manual-health-check.json` in your workspace for a manual trigger button:

```json
{
  "name": "One-Click Health Check",
  "version": "1.0.0",
  "description": "Manual health check trigger from sidebar",
  "when": { "type": "userTriggered" },
  "then": {
    "type": "askAgent",
    "prompt": "Run check_health and report the results. If status is not healthy, provide diagnosis and suggested actions."
  }
}
```

## Install

Requires Python >= 3.10.

```bash
pip install kiro-health-monitor
```

## Keywords

kiro, health, monitor, heartbeat, stall, responsive, watchdog
