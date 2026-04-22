# 实现计划：Kiro Health Monitor

## 概述

基于需求文档和技术设计文档，将 Kiro Health Monitor 功能拆分为增量式编码任务。采用 Python + fastmcp 实现 MCP Server，使用 pytest 作为测试框架，hypothesis 作为属性测试库。用户只需安装 Python，即可通过 `uvx` 直接运行。每个任务逐步构建，最终将所有模块串联集成。

## 任务

- [x] 1. 搭建项目结构与核心数据模型
  - [x] 1.1 初始化项目目录结构，配置 `pyproject.toml`、pytest 配置
    - 创建 `src/` 目录及子模块：`src/types.py`、`src/core/`、`src/detectors/`、`src/notifications/`、`src/config/`、`src/tools/`
    - 配置依赖：`mcp[cli]`（fastmcp）、`pytest`、`hypothesis`、`pytest-asyncio`
    - 配置 `pyproject.toml` 中的 `[project.scripts]` 入口点，支持 `uvx` 运行
    - _需求: 5.1, 5.2, 5.3, 5.5_

  - [x] 1.2 定义所有 Python 数据模型与协议类
    - 在 `src/types.py` 中定义 `HealthStatus`、`CheckSource`、`AlertType`、`AlertLevel`（Enum）、`HeartbeatResult`、`TrackedTask`、`StallCheckResult`、`Alert`、`AlertRecord`、`AlertFilter`、`HealthReport`、`MonitorConfig`、`ConfigUpdateResult`、`ValidationResult`、`CONFIG_RANGES` 等所有 dataclass 数据模型
    - 定义 `IHealthMonitorCore`、`IHeartbeatChecker`、`ITaskStatusDetector`、`IWindowResumeDetector`、`INotificationManager`、`IConfigManager` Protocol 类
    - _需求: 4.2, 4.3_

- [x] 2. 实现 ConfigManager 配置管理模块
  - [x] 2.1 实现 ConfigManager 类
    - 在 `src/config/config_manager.py` 中实现 `get_config()`、`update_config()`、`validate_param()` 方法
    - 默认配置：heartbeat_interval=30, response_timeout=5, stall_threshold=60, auto_retry='off'
    - 参数校验范围：heartbeat_interval [10,300]、response_timeout [1,30]、stall_threshold [10,600]
    - _需求: 5.3, 5.4, 7.1, 7.2_

  - [ ]* 2.2 编写 ConfigManager 属性测试
    - **Property 8: 配置参数范围校验**
    - 使用 hypothesis 的 `st.integers()` 和 `st.floats()` 生成随机参数值（含越界值），验证超出范围时返回 success=False 并包含有效范围说明
    - **验证: 需求 5.4**

  - [ ]* 2.3 编写 ConfigManager 单元测试
    - 测试默认配置值正确（auto_retry 默认 off）
    - 测试接受 on/off 值
    - 测试未知参数被忽略
    - _需求: 7.1, 7.2_

- [x] 3. 实现 NotificationManager 告警通知模块
  - [x] 3.1 实现 NotificationManager 类
    - 在 `src/notifications/notification_manager.py` 中实现 `send_alert()`、`send_recovery_notification()`、`get_alert_history()`、`is_duplicate()` 方法
    - 实现 5 分钟滑动窗口去重机制
    - 实现 FIFO 策略，保留最近 1000 条告警记录
    - 实现按时间范围和告警类型筛选历史告警
    - _需求: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 3.2 编写告警去重属性测试
    - **Property 9: 告警去重窗口**
    - 使用 hypothesis 生成随机告警类型和时间间隔，验证 5 分钟内同类告警被抑制
    - **验证: 需求 6.1**

  - [ ]* 3.3 编写告警内容完整性属性测试
    - **Property 10: 告警内容完整性**
    - 使用 hypothesis 的 `st.builds()` 生成随机 Alert 对象，验证必须包含 description、timestamp、suggested_action
    - **验证: 需求 6.2**

  - [ ]* 3.4 编写告警级别映射属性测试
    - **Property 11: 健康状态到告警级别映射**
    - 使用 `st.sampled_from()` 枚举所有 HealthStatus 值，验证 healthy→info、degraded→warning、unresponsive→critical
    - **验证: 需求 6.3**

  - [ ]* 3.5 编写状态恢复通知属性测试
    - **Property 12: 状态恢复通知**
    - 使用 hypothesis 生成随机状态转换对，验证仅 unresponsive→healthy 时发送恢复通知
    - **验证: 需求 6.4**

- [x] 4. 检查点 - 确保所有测试通过
  - 运行 `pytest` 确保所有测试通过，如有问题请询问用户。

- [x] 5. 实现 HeartbeatChecker 心跳检测模块
  - [x] 5.1 实现 HeartbeatChecker 类
    - 在 `src/detectors/heartbeat_checker.py` 中实现 `start()`、`stop()`、`ping()`、`get_consecutive_timeouts()`、`reset_timeout_count()` 方法
    - 使用 `asyncio` 任务调度实现定时心跳检测
    - 实现连续超时计数逻辑
    - _需求: 1.1, 1.2, 1.3, 1.5_

  - [ ]* 5.2 编写心跳状态判定属性测试
    - **Property 1: 心跳状态判定**
    - 使用 hypothesis 的 `st.floats()` 生成随机延迟值和超时阈值，验证状态判定逻辑
    - **验证: 需求 1.2, 1.3, 1.5**

  - [ ]* 5.3 编写连续超时告警属性测试
    - **Property 2: 连续超时告警阈值**
    - 使用 hypothesis 的 `st.lists(st.booleans())` 生成随机心跳结果序列，验证连续超时 >= 2 时才发送告警
    - **验证: 需求 1.4**

  - [ ]* 5.4 编写 HeartbeatChecker 单元测试
    - 测试定时器按配置间隔触发
    - 测试心跳响应格式异常时视为超时处理
    - _需求: 1.1_

- [x] 6. 实现 TaskStatusDetector 任务卡顿检测模块
  - [x] 6.1 实现 TaskStatusDetector 类
    - 在 `src/detectors/task_status_detector.py` 中实现 `track_task()`、`untrack_task()`、`update_task_progress()`、`check_for_stalls()`、`is_task_active()` 方法
    - 实现基于 stall_threshold 和活动判断的卡顿检测逻辑
    - 实现卡顿恢复自动撤销机制
    - _需求: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 6.2 编写任务卡顿检测属性测试
    - **Property 3: 任务卡顿检测（含活动判断）**
    - 使用 hypothesis 的 `st.builds()` 生成随机任务状态，验证卡顿判定逻辑
    - **验证: 需求 2.2, 2.4**

  - [ ]* 6.3 编写卡顿恢复往返属性测试
    - **Property 4: 卡顿恢复往返**
    - 使用 hypothesis 生成随机卡顿任务并应用进度更新，验证卡顿标记自动撤销
    - **验证: 需求 2.5**

  - [ ]* 6.4 编写卡顿告警内容单元测试
    - 测试告警包含取消重试建议
    - _需求: 2.3_

- [x] 7. 实现 WindowResumeDetector 窗口恢复检测模块
  - [x] 7.1 实现 WindowResumeDetector 类
    - 在 `src/detectors/window_resume_detector.py` 中实现 `start_listening()`、`stop_listening()`、`record_background_timestamp()`、`get_background_duration()`、`on_resume()` 方法
    - 实现窗口进入后台时间戳记录
    - 实现窗口恢复回调机制
    - _需求: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 7.2 编写深度检查阈值属性测试
    - **Property 5: 深度检查阈值判定**
    - 使用 hypothesis 的 `st.floats()` 生成随机窗口离开时长，验证仅 > 10 分钟时执行深度检查
    - **验证: 需求 3.5**

  - [ ]* 7.3 编写窗口恢复单元测试
    - 测试窗口恢复时触发健康检查
    - 测试无响应时显示提示、正常时静默
    - 测试进入后台时记录时间戳
    - _需求: 3.1, 3.2, 3.3, 3.4_

- [x] 8. 检查点 - 确保所有测试通过
  - 运行 `pytest` 确保所有测试通过，如有问题请询问用户。

- [x] 9. 实现 HealthMonitorCore 核心协调模块
  - [x] 9.1 实现 HealthMonitorCore 类
    - 在 `src/core/health_monitor_core.py` 中实现 `get_health_status()`、`perform_health_check()`、`perform_deep_health_check()`、`update_status()`、`start()`、`stop()` 方法
    - 整合 HeartbeatChecker、TaskStatusDetector、WindowResumeDetector、NotificationManager、ConfigManager
    - 实现健康报告生成逻辑，包含所有必需字段
    - 实现异常指标建议生成逻辑
    - 实现自动重试逻辑（auto_retry 为 on 时自动取消并重新执行任务）
    - 实现单任务最多 3 次重试限制
    - _需求: 1.4, 4.1, 4.2, 4.3, 4.4, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 9.2 编写健康报告完整性属性测试
    - **Property 6: 健康报告完整性与 JSON 往返**
    - 使用 hypothesis 的 `st.builds()` 生成随机系统状态组合，验证 JSON 序列化/反序列化往返一致性及必需字段完整性
    - **验证: 需求 4.2, 4.3**

  - [ ]* 9.3 编写异常指标建议属性测试
    - **Property 7: 异常指标建议**
    - 使用 hypothesis 生成包含随机异常指标的报告，验证 recommendations 非空且每个异常有对应建议
    - **验证: 需求 4.4**

  - [ ]* 9.4 编写自动重试行为属性测试
    - **Property 13: 自动重试行为**
    - 使用 hypothesis 生成随机场景（config + status + tasks），验证 on 时自动重试、off 时仅告警
    - **验证: 需求 7.3, 7.4, 7.5**

  - [ ]* 9.5 编写自动重试次数限制属性测试
    - **Property 14: 自动重试次数限制**
    - 使用 hypothesis 的 `st.integers()` 生成随机 retry_count 值，验证 retry_count < 3 时允许重试、达到 3 时禁用
    - **验证: 需求 7.6**

  - [ ]* 9.6 编写 HealthMonitorCore 单元测试
    - 测试报告在超时时间内返回
    - 测试自动重试异常时记录并通知
    - _需求: 4.1, 7.7_

- [x] 10. 检查点 - 确保所有测试通过
  - 运行 `pytest` 确保所有测试通过，如有问题请询问用户。

- [x] 11. 实现 MCP Server 与工具注册
  - [x] 11.1 实现 MCP Server 入口与四个工具注册
    - 在 `src/tools/mcp_server.py` 中使用 fastmcp 创建 MCP Server 实例
    - 注册 `check_health` 工具：调用 `HealthMonitorCore.perform_health_check()` 返回 HealthReport
    - 注册 `get_status` 工具：返回当前 HealthStatus、最近心跳时间、延迟、活跃/卡顿任务数
    - 注册 `configure_monitor` 工具：调用 ConfigManager 更新配置，含参数校验
    - 注册 `get_alert_history` 工具：调用 NotificationManager 查询历史告警，支持筛选
    - 创建 `src/__main__.py` 入口文件，启动 MCP Server 并初始化所有模块
    - _需求: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 11.2 编写 MCP 工具注册单元测试
    - 测试四个工具均已注册
    - 测试 configure_monitor 参数校验拒绝越界值
    - 测试 get_alert_history 支持按时间范围和类型筛选
    - _需求: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 12. 集成串联与端到端验证
  - [x] 12.1 串联所有模块并编写集成测试
    - 确保 HealthMonitorCore 正确协调所有子模块
    - 验证心跳超时 → 告警 → 自动重试的完整流程
    - 验证窗口恢复 → 健康检查 → 深度检查的完整流程
    - 验证配置变更 → 各模块参数生效的完整流程
    - _需求: 1.1-1.5, 2.1-2.5, 3.1-3.5, 4.1-4.4, 5.1-5.5, 6.1-6.4, 7.1-7.7_

  - [x] 12.2 创建 Kiro Power 配置文件
    - 创建 `POWER.md` 文档，描述 Power 功能和使用方式
    - 创建 Power 配置清单（如 `power.json` 或相关配置），声明 MCP Server 入口和工具列表
    - 配置 `pyproject.toml` 确保 `uvx` 可直接运行
    - _需求: 5.1, 5.2, 5.3, 5.5_

- [x] 13. 最终检查点 - 确保所有测试通过
  - 运行 `pytest` 确保所有测试通过，如有问题请询问用户。

## 备注

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号，确保可追溯性
- 检查点任务确保增量验证，及时发现问题
- 属性测试验证设计文档中定义的 14 个正确性属性
- 单元测试验证具体示例和边界条件
