"""Kiro Health Monitor - Data models, Protocol classes, and MCP tool types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Optional, Protocol


# ============================================================
# Enums
# ============================================================

class HealthStatus(str, Enum):
    """健康状态枚举"""
    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    UNRESPONSIVE = 'unresponsive'


class CheckSource(str, Enum):
    """检测来源"""
    HEARTBEAT = 'heartbeat'
    TASK_DETECTOR = 'task_detector'
    WINDOW_RESUME = 'window_resume'


class AlertType(str, Enum):
    """告警类型"""
    HEARTBEAT_TIMEOUT = 'heartbeat_timeout'
    TASK_STALL = 'task_stall'
    SERVICE_UNRESPONSIVE = 'service_unresponsive'
    TASK_RECOVERED = 'task_recovered'
    SERVICE_RECOVERED = 'service_recovered'
    AUTO_RETRY_TRIGGERED = 'auto_retry_triggered'
    AUTO_RETRY_FAILED = 'auto_retry_failed'
    AUTO_RETRY_LIMIT_REACHED = 'auto_retry_limit_reached'


class AlertLevel(str, Enum):
    """告警级别"""
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'


# ============================================================
# Core Dataclasses
# ============================================================

@dataclass
class HeartbeatResult:
    """心跳检测结果"""
    success: bool
    latency: float          # 毫秒
    timestamp: float         # Unix 时间戳
    error: Optional[str] = None  # 异常信息


@dataclass
class TrackedTask:
    """被跟踪的任务"""
    task_id: str
    name: str
    start_time: float
    last_progress_update: float
    last_log_output: Optional[float] = None
    retry_count: int = 0
    auto_retry_disabled: bool = False


@dataclass
class StallCheckResult:
    """卡顿检查结果"""
    task_id: str
    is_stalled: bool
    stall_duration: float    # 毫秒
    is_active: bool          # 是否仍有日志/资源活动


@dataclass
class Alert:
    """告警记录"""
    type: AlertType
    level: AlertLevel
    message: str
    description: str
    suggested_action: str
    related_task_id: Optional[str] = None


@dataclass
class AlertRecord(Alert):
    """带 ID 和时间戳的告警记录"""
    id: str = ''
    timestamp: float = 0.0


@dataclass
class AlertFilter:
    """告警筛选条件"""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    alert_type: Optional[AlertType] = None


@dataclass
class HeartbeatInfo:
    last_check_time: float
    last_latency: float
    consecutive_timeouts: int


@dataclass
class TaskInfo:
    active_count: int
    stalled_tasks: list[StallCheckResult]


@dataclass
class WindowInfo:
    is_active: bool
    active_duration: float
    last_background_time: Optional[float] = None


@dataclass
class AlertSummary:
    recent_alerts: list[AlertRecord]
    total_alerts: int


@dataclass
class HealthReport:
    """健康报告"""
    status: HealthStatus
    timestamp: float
    heartbeat: HeartbeatInfo
    tasks: TaskInfo
    window: WindowInfo
    alert_summary: AlertSummary
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MonitorConfig:
    """监控配置"""
    heartbeat_interval: int = 300   # 秒，默认 5 分钟
    response_timeout: int = 5       # 秒，默认 5
    stall_threshold: int = 60       # 秒，默认 60
    auto_retry: Literal['on', 'off'] = 'off'  # 默认 'off'


@dataclass
class ConfigUpdateResult:
    """配置更新结果"""
    success: bool
    config: MonitorConfig
    errors: Optional[list[str]] = None


@dataclass
class ValidationResult:
    """参数校验结果"""
    valid: bool
    message: Optional[str] = None
    range: Optional[dict[str, int]] = None  # {"min": ..., "max": ...}


# ============================================================
# Constants
# ============================================================

CONFIG_RANGES: dict[str, dict[str, int]] = {
    'heartbeat_interval': {'min': 10, 'max': 300},
    'response_timeout': {'min': 1, 'max': 30},
    'stall_threshold': {'min': 10, 'max': 600},
}


# ============================================================
# Union Type
# ============================================================

CheckResult = HeartbeatResult | StallCheckResult


# ============================================================
# Protocol Classes
# ============================================================

class IHealthMonitorCore(Protocol):
    """核心协调模块接口"""

    def get_health_status(self) -> HealthStatus:
        """获取当前健康状态"""
        ...

    def perform_health_check(self) -> HealthReport:
        """执行一次完整健康检查，返回健康报告"""
        ...

    def perform_deep_health_check(self) -> HealthReport:
        """执行深度健康检查（窗口离开超过10分钟时）"""
        ...

    def update_status(self, source: CheckSource, result: CheckResult) -> None:
        """更新健康状态"""
        ...

    async def start(self) -> None:
        """启动监控"""
        ...

    async def stop(self) -> None:
        """停止监控"""
        ...


class IHeartbeatChecker(Protocol):
    """心跳检测器接口"""

    async def start(self, interval: int) -> None:
        """启动心跳检测定时器"""
        ...

    async def stop(self) -> None:
        """停止心跳检测"""
        ...

    async def ping(self) -> HeartbeatResult:
        """执行一次心跳检测"""
        ...

    def get_consecutive_timeouts(self) -> int:
        """获取连续超时次数"""
        ...

    def reset_timeout_count(self) -> None:
        """重置连续超时计数"""
        ...


class ITaskStatusDetector(Protocol):
    """任务状态检测器接口"""

    def track_task(self, task: TrackedTask) -> None:
        """注册一个正在执行的任务进行监控"""
        ...

    def untrack_task(self, task_id: str) -> None:
        """移除任务监控"""
        ...

    def update_task_progress(self, task_id: str, timestamp: float) -> None:
        """更新任务进度时间戳"""
        ...

    def check_for_stalls(self) -> list[StallCheckResult]:
        """检查所有被跟踪任务的卡顿状态"""
        ...

    def is_task_active(self, task_id: str) -> bool:
        """判断任务是否仍有活动（日志输出或资源变化）"""
        ...


class IWindowResumeDetector(Protocol):
    """窗口恢复检测器接口"""

    def start_listening(self) -> None:
        """开始监听窗口事件"""
        ...

    def stop_listening(self) -> None:
        """停止监听"""
        ...

    def record_background_timestamp(self) -> None:
        """记录窗口进入后台的时间"""
        ...

    def get_background_duration(self) -> Optional[float]:
        """获取窗口离开时长（毫秒）"""
        ...

    def on_resume(self, callback: Callable[[float], None]) -> None:
        """注册窗口恢复回调"""
        ...


class INotificationManager(Protocol):
    """通知管理器接口"""

    def send_alert(self, alert: Alert) -> bool:
        """发送告警通知（内部执行去重）"""
        ...

    def send_recovery_notification(self, message: str) -> None:
        """发送恢复通知"""
        ...

    def get_alert_history(self, filter: Optional[AlertFilter] = None) -> list[AlertRecord]:
        """查询历史告警记录"""
        ...

    def is_duplicate(self, alert_type: str) -> bool:
        """检查告警是否在去重窗口内"""
        ...


class IConfigManager(Protocol):
    """配置管理器接口"""

    def get_config(self) -> MonitorConfig:
        """获取当前配置"""
        ...

    def update_config(self, partial: dict[str, Any]) -> ConfigUpdateResult:
        """更新配置（含参数校验）"""
        ...

    def validate_param(self, key: str, value: Any) -> ValidationResult:
        """校验参数值是否在合理范围内"""
        ...


# ============================================================
# MCP Tool Dataclasses
# ============================================================

@dataclass
class CheckHealthOutput:
    report: HealthReport


@dataclass
class GetStatusOutput:
    status: HealthStatus
    last_heartbeat: str          # ISO 时间戳
    last_heartbeat_latency: float  # 毫秒
    active_task_count: int
    stalled_task_count: int


@dataclass
class ConfigureMonitorInput:
    heartbeat_interval: Optional[int] = None    # 秒，范围 [10, 300]
    response_timeout: Optional[int] = None      # 秒，范围 [1, 30]
    stall_threshold: Optional[int] = None       # 秒，范围 [10, 600]
    auto_retry: Optional[Literal['on', 'off']] = None


@dataclass
class ConfigureMonitorOutput:
    success: bool
    config: MonitorConfig
    errors: Optional[list[str]] = None


@dataclass
class GetAlertHistoryInput:
    start_time: Optional[str] = None   # ISO 时间戳
    end_time: Optional[str] = None     # ISO 时间戳
    alert_type: Optional[AlertType] = None


@dataclass
class GetAlertHistoryOutput:
    alerts: list[AlertRecord]
    total: int
