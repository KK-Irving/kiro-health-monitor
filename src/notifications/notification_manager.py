"""NotificationManager - Alert notification management with deduplication."""

import logging
import time
import uuid
from typing import Optional

from src.types import (
    Alert,
    AlertFilter,
    AlertLevel,
    AlertRecord,
    AlertType,
    HealthStatus,
)

logger = logging.getLogger(__name__)

# Deduplication window in seconds
_DEDUP_WINDOW_SECONDS = 300  # 5 minutes

# Maximum alert history size (FIFO)
_MAX_HISTORY_SIZE = 1000


def get_alert_level_for_status(status: HealthStatus) -> AlertLevel:
    """Map HealthStatus to AlertLevel.

    healthy → info, degraded → warning, unresponsive → critical.
    """
    mapping = {
        HealthStatus.HEALTHY: AlertLevel.INFO,
        HealthStatus.DEGRADED: AlertLevel.WARNING,
        HealthStatus.UNRESPONSIVE: AlertLevel.CRITICAL,
    }
    return mapping[status]


class NotificationManager:
    """Manages alert notifications with deduplication and history tracking."""

    def __init__(self) -> None:
        self._history: list[AlertRecord] = []
        self._last_sent: dict[str, float] = {}

    # ------------------------------------------------------------------
    # INotificationManager protocol methods
    # ------------------------------------------------------------------

    def send_alert(self, alert: Alert) -> bool:
        """Send an alert with deduplication.

        Returns True if the alert was sent, False if suppressed as duplicate.
        """
        if self.is_duplicate(alert.type.value):
            logger.debug("Alert suppressed (duplicate): %s", alert.type.value)
            return False

        record = AlertRecord(
            type=alert.type,
            level=alert.level,
            message=alert.message,
            description=alert.description,
            suggested_action=alert.suggested_action,
            related_task_id=alert.related_task_id,
            id=str(uuid.uuid4()),
            timestamp=time.time(),
        )

        self._store_record(record)
        self._last_sent[alert.type.value] = record.timestamp

        logger.info(
            "Alert sent [%s] %s: %s",
            record.level.value,
            record.type.value,
            record.message,
        )
        return True

    def send_recovery_notification(self, message: str) -> None:
        """Send a recovery notification (bypasses dedup)."""
        alert = Alert(
            type=AlertType.SERVICE_RECOVERED,
            level=AlertLevel.INFO,
            message=message,
            description=message,
            suggested_action="No action required.",
        )

        record = AlertRecord(
            type=alert.type,
            level=alert.level,
            message=alert.message,
            description=alert.description,
            suggested_action=alert.suggested_action,
            related_task_id=alert.related_task_id,
            id=str(uuid.uuid4()),
            timestamp=time.time(),
        )

        self._store_record(record)

        logger.info("Recovery notification sent: %s", message)

    def get_alert_history(
        self, filter: Optional[AlertFilter] = None
    ) -> list[AlertRecord]:
        """Return alert history, optionally filtered."""
        if filter is None:
            return list(self._history)

        result: list[AlertRecord] = []
        for record in self._history:
            if filter.start_time is not None and record.timestamp < filter.start_time:
                continue
            if filter.end_time is not None and record.timestamp > filter.end_time:
                continue
            if filter.alert_type is not None and record.type != filter.alert_type:
                continue
            result.append(record)
        return result

    def is_duplicate(self, alert_type: str) -> bool:
        """Check if an alert of the given type was sent within the dedup window."""
        last_time = self._last_sent.get(alert_type)
        if last_time is None:
            return False
        return (time.time() - last_time) < _DEDUP_WINDOW_SECONDS

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _store_record(self, record: AlertRecord) -> None:
        """Append a record to history, enforcing FIFO max size."""
        self._history.append(record)
        if len(self._history) > _MAX_HISTORY_SIZE:
            self._history = self._history[-_MAX_HISTORY_SIZE:]
