# Kiro Health Monitor

Kiro IDE 健康状态监控 Power — 一个基于 MCP Server 的 Kiro Power，用于主动检测 Kiro IDE 的健康状态和响应性。

## 解决的问题

在实际使用 Kiro IDE 时，经常遇到以下问题：

1. **任务假死**：UI 显示加载动画（转圈），但实际任务已卡顿无响应，需要手动取消并重新执行
2. **后台休眠**：最小化 IDE 一段时间后切回，界面无响应（后台服务可能已断开）
3. **缺乏感知**：用户无法及时知道 IDE 是否处于正常工作状态

本 Power 通过心跳检测、任务卡顿监控和窗口恢复检测，主动发现并提示异常状态。

## 功能特性

- **心跳检测** — 定期探测后台服务存活状态，连续 2 次超时自动告警
- **任务卡顿检测** — 监控任务进度，区分正常长时间运行与真正卡顿
- **窗口恢复检测** — 切回 IDE 时自动检查服务状态，离开超 10 分钟执行深度检查
- **健康报告** — 结构化 JSON 报告，异常指标附带修复建议
- **自动重试** — 可选功能（默认关闭），检测到无响应时自动重新执行任务，单任务最多 3 次
- **告警去重** — 5 分钟内同类告警不重复发送，避免打扰

## 技术栈

- Python 3.10+
- [FastMCP](https://github.com/jlowin/fastmcp) (MCP Python SDK)
- asyncio 异步任务调度
- pytest + hypothesis (测试)

## 项目结构

```
kiro-health-monitor/
├── src/
│   ├── __init__.py
│   ├── __main__.py              # 入口文件
│   ├── types.py                 # 数据模型与接口定义
│   ├── config/
│   │   └── config_manager.py    # 配置管理（参数校验）
│   ├── core/
│   │   └── health_monitor_core.py  # 核心协调模块
│   ├── detectors/
│   │   ├── heartbeat_checker.py    # 心跳检测
│   │   ├── task_status_detector.py # 任务卡顿检测
│   │   └── window_resume_detector.py # 窗口恢复检测
│   ├── notifications/
│   │   └── notification_manager.py # 告警通知管理
│   └── tools/
│       └── mcp_server.py        # MCP Server + 工具注册
├── tests/
│   └── test_integration.py      # 集成测试（12 个测试用例）
├── pyproject.toml               # 项目配置
├── power.json                   # Kiro Power 清单
├── POWER.md                     # Power 功能文档
└── README.md
```

## MCP 工具

| 工具 | 说明 |
|------|------|
| `check_health` | 执行即时健康检查，返回完整健康报告 |
| `get_status` | 获取当前状态摘要（状态、心跳延迟、任务数） |
| `configure_monitor` | 动态调整配置参数 |
| `get_alert_history` | 查询历史告警，支持按时间和类型筛选 |

## 配置参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `heartbeat_interval` | 30 | [10, 300] | 心跳间隔（秒） |
| `response_timeout` | 5 | [1, 30] | 响应超时（秒） |
| `stall_threshold` | 60 | [10, 600] | 卡顿判定阈值（秒） |
| `auto_retry` | `off` | `on`/`off` | 自动重试开关 |

## 安装与使用

### 前置条件

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 包管理器)

### 运行

```bash
# 通过 uvx 直接运行（自动下载依赖）
uvx kiro-health-monitor

# 或本地开发运行
cd kiro-health-monitor
pip install -e ".[dev]"
python -m src
```

### 在 Kiro 中配置

在 `.kiro/settings/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "kiro-health-monitor": {
      "command": "uvx",
      "args": ["kiro-health-monitor"],
      "disabled": false,
      "autoApprove": ["check_health", "get_status"]
    }
  }
}
```

### 运行测试

```bash
cd kiro-health-monitor
pip install -e ".[dev]"
pytest -v
```

## 架构概览

```
Kiro IDE ──→ MCP Server (kiro-health-monitor)
              ├── HeartbeatChecker (asyncio 定时心跳)
              ├── TaskStatusDetector (任务进度监控)
              ├── WindowResumeDetector (窗口焦点事件)
              ├── HealthMonitorCore (核心协调)
              ├── NotificationManager (告警去重+历史)
              └── ConfigManager (参数校验+动态配置)
```

## License

MIT
