# 需求文档

## 简介

Kiro Health Monitor 是一个 Kiro Power，用于检测 Kiro IDE 的健康状态和响应性。在实际使用中，用户经常遇到以下问题：任务执行时 UI 显示加载动画但实际已卡顿无响应；最小化 IDE 一段时间后切回界面时后台服务已无响应。本 Power 旨在通过主动健康检测机制，及时发现并提示用户 IDE 的异常状态，从而提升用户体验。

## 术语表

- **Health_Monitor**: 健康监控核心模块，负责执行健康检查逻辑并汇总检测结果
- **Heartbeat_Checker**: 心跳检测器，通过定期发送心跳探测来判断 Kiro 后台服务是否存活和响应
- **Task_Status_Detector**: 任务状态检测器，负责检测当前正在执行的任务是否处于卡顿或无响应状态
- **Notification_Manager**: 通知管理器，负责向用户发送健康状态告警和建议操作
- **Health_Report**: 健康报告，包含 IDE 各项健康指标的结构化数据
- **Heartbeat_Interval**: 心跳间隔，两次心跳检测之间的时间间隔（默认 30 秒）
- **Response_Timeout**: 响应超时阈值，判定服务无响应的等待时间上限（默认 5 秒）
- **Stall_Threshold**: 卡顿阈值，任务在无进度更新情况下被判定为卡顿的时间上限（默认 60 秒）
- **MCP_Server**: MCP 服务端，Power 中提供工具能力的后端服务进程
- **Health_Status**: 健康状态枚举值，包含 healthy（健康）、degraded（降级）、unresponsive（无响应）三种状态
- **Auto_Retry**: 自动重试功能开关，一个简单的 on/off 可配置项，控制当检测到 Kiro 无响应时是否自动重新执行当前任务（默认 off）

## 需求

### 需求 1：后台服务心跳检测

**用户故事：** 作为一名 Kiro 用户，我希望 Power 能定期检测后台服务的存活状态，以便在服务无响应时及时获得提醒。

#### 验收标准

1. WHILE Health_Monitor 处于运行状态, THE Heartbeat_Checker SHALL 按照 Heartbeat_Interval 定期向 MCP_Server 发送心跳探测请求
2. WHEN Heartbeat_Checker 在 Response_Timeout 内收到 MCP_Server 的心跳响应, THE Health_Monitor SHALL 将 Health_Status 标记为 healthy
3. WHEN Heartbeat_Checker 在 Response_Timeout 内未收到 MCP_Server 的心跳响应, THE Health_Monitor SHALL 将 Health_Status 标记为 unresponsive
4. WHEN Health_Monitor 连续检测到 2 次心跳超时, THE Notification_Manager SHALL 向用户发送服务无响应的告警通知
5. IF Heartbeat_Checker 发送心跳探测请求时发生网络异常, THEN THE Health_Monitor SHALL 记录异常信息并将 Health_Status 标记为 degraded

### 需求 2：任务卡顿检测

**用户故事：** 作为一名 Kiro 用户，我希望 Power 能检测当前任务是否处于卡顿状态，以便我可以及时取消并重新执行任务。

#### 验收标准

1. WHILE 存在正在执行的任务, THE Task_Status_Detector SHALL 监控任务的进度更新时间戳
2. WHEN 任务在 Stall_Threshold 时间内没有产生任何进度更新, THE Task_Status_Detector SHALL 将该任务标记为疑似卡顿状态
3. WHEN Task_Status_Detector 检测到任务处于疑似卡顿状态, THE Notification_Manager SHALL 向用户发送任务卡顿告警，并建议用户取消当前任务后重新执行
4. THE Task_Status_Detector SHALL 区分正常的长时间运行任务和真正的卡顿任务，通过检查任务是否仍在产生日志输出或资源消耗变化来判断
5. IF 任务在被标记为卡顿后恢复了进度更新, THEN THE Task_Status_Detector SHALL 自动撤销卡顿标记并通知用户任务已恢复正常

### 需求 3：IDE 窗口恢复检测

**用户故事：** 作为一名 Kiro 用户，我希望在最小化 IDE 一段时间后切回时，Power 能自动检测后台服务状态并提示我是否需要重新连接。

#### 验收标准

1. WHEN 用户将 Kiro IDE 窗口从最小化或后台状态切换回前台, THE Health_Monitor SHALL 立即执行一次完整的健康检查
2. WHEN 窗口恢复后的健康检查发现 MCP_Server 无响应, THE Notification_Manager SHALL 向用户显示服务无响应提示，并提供重新连接的建议操作
3. WHEN 窗口恢复后的健康检查确认所有服务正常, THE Health_Monitor SHALL 静默记录检查结果，不打扰用户
4. THE Health_Monitor SHALL 记录 IDE 窗口进入后台的时间戳，以便在窗口恢复时计算离开时长
5. WHEN IDE 窗口离开时长超过 10 分钟, THE Health_Monitor SHALL 在窗口恢复时执行深度健康检查，包括验证所有已注册的 MCP 工具是否仍可用

### 需求 4：健康报告生成

**用户故事：** 作为一名 Kiro 用户，我希望能随时查看 IDE 的健康状态报告，以便了解当前系统的整体运行情况。

#### 验收标准

1. WHEN 用户通过 MCP 工具调用请求健康报告, THE Health_Monitor SHALL 在 Response_Timeout 内返回包含所有健康指标的 Health_Report
2. THE Health_Report SHALL 包含以下信息：当前 Health_Status、最近一次心跳检测时间、最近一次心跳响应延迟、当前任务执行状态、IDE 窗口活跃时长、历史告警记录摘要
3. THE Health_Report SHALL 使用结构化的 JSON 格式输出，便于程序化处理和展示
4. WHEN Health_Report 中存在异常指标, THE Health_Monitor SHALL 在报告中附带针对每个异常的建议修复操作

### 需求 5：MCP 工具接口

**用户故事：** 作为一名 Kiro 用户，我希望通过标准的 MCP 工具接口与 Health Monitor 交互，以便在对话中直接查询和管理健康监控。

#### 验收标准

1. THE MCP_Server SHALL 提供 `check_health` 工具，用于执行一次即时健康检查并返回 Health_Report
2. THE MCP_Server SHALL 提供 `get_status` 工具，用于获取当前 Health_Status 和最近的检测摘要信息
3. THE MCP_Server SHALL 提供 `configure_monitor` 工具，用于动态调整 Heartbeat_Interval、Response_Timeout 和 Stall_Threshold 参数
4. WHEN 用户通过 `configure_monitor` 工具设置的参数值超出合理范围, THE MCP_Server SHALL 拒绝该配置并返回参数有效范围说明
5. THE MCP_Server SHALL 提供 `get_alert_history` 工具，用于查询历史告警记录，支持按时间范围和告警类型筛选

### 需求 6：告警通知管理

**用户故事：** 作为一名 Kiro 用户，我希望告警通知清晰且不过度打扰，以便我能在需要时获得有用信息而不被频繁干扰。

#### 验收标准

1. THE Notification_Manager SHALL 对同一类型的告警实施去重机制，在 5 分钟内不重复发送相同类型的告警
2. WHEN 发送告警通知时, THE Notification_Manager SHALL 在通知内容中包含：问题描述、检测时间、建议操作步骤
3. THE Notification_Manager SHALL 支持三种告警级别：info（信息）、warning（警告）、critical（严重），并根据 Health_Status 自动选择对应级别
4. WHEN Health_Status 从 unresponsive 恢复为 healthy, THE Notification_Manager SHALL 发送一条恢复通知，告知用户服务已恢复正常

### 需求 7：无响应自动重试

**用户故事：** 作为一名 Kiro 用户，我希望在 Health Monitor 检测到 Kiro 实际无响应时，能够自动重新执行当前任务，以便减少手动干预的操作成本。

#### 验收标准

1. THE MCP_Server SHALL 通过 `configure_monitor` 工具支持 Auto_Retry 参数的配置，接受 on 或 off 两个值
2. THE Health_Monitor SHALL 将 Auto_Retry 的默认值设置为 off
3. WHERE Auto_Retry 配置为 on, WHEN Health_Monitor 检测到 Health_Status 为 unresponsive 且存在正在执行的任务, THE Health_Monitor SHALL 自动取消当前卡顿任务并重新执行该任务
4. WHERE Auto_Retry 配置为 off, WHEN Health_Monitor 检测到 Health_Status 为 unresponsive, THE Notification_Manager SHALL 仅向用户发送告警通知，由用户自行决定后续操作
5. WHEN Auto_Retry 触发自动重新执行任务时, THE Notification_Manager SHALL 向用户发送一条 info 级别的通知，说明已自动重新执行任务及原因
6. THE Health_Monitor SHALL 对同一任务的自动重试次数限制为最多 3 次，超过限制后将 Auto_Retry 对该任务临时禁用并通知用户手动处理
7. IF Auto_Retry 触发重新执行任务时发生异常, THEN THE Health_Monitor SHALL 记录异常信息并通知用户手动介入
