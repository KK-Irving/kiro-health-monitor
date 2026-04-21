"""ConfigManager - manages monitor configuration with validation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.types import (
    CONFIG_RANGES,
    ConfigUpdateResult,
    MonitorConfig,
    ValidationResult,
)


class ConfigManager:
    """Manages monitoring parameters configuration.

    Satisfies the IConfigManager Protocol.
    """

    def __init__(self) -> None:
        self._config = MonitorConfig()

    def get_config(self) -> MonitorConfig:
        """Return the current monitor configuration."""
        return self._config

    def update_config(self, partial: dict[str, Any]) -> ConfigUpdateResult:
        """Update configuration with validation.

        Unknown keys are silently ignored. If any known key has an invalid
        value the entire update is rejected and errors are returned.
        """
        errors: list[str] = []
        updates: dict[str, Any] = {}

        known_keys = set(CONFIG_RANGES.keys()) | {"auto_retry"}

        for key, value in partial.items():
            if key not in known_keys:
                continue
            result = self.validate_param(key, value)
            if result.valid:
                updates[key] = value
            else:
                errors.append(result.message or f"Invalid value for {key}")

        if errors:
            return ConfigUpdateResult(
                success=False,
                config=self._config,
                errors=errors,
            )

        if updates:
            self._config = replace(self._config, **updates)

        return ConfigUpdateResult(success=True, config=self._config)

    def validate_param(self, key: str, value: Any) -> ValidationResult:
        """Validate a single configuration parameter."""
        if key in CONFIG_RANGES:
            param_range = CONFIG_RANGES[key]
            if not isinstance(value, int):
                return ValidationResult(
                    valid=False,
                    message=f"{key} must be an integer",
                    range=param_range,
                )
            if value < param_range["min"] or value > param_range["max"]:
                return ValidationResult(
                    valid=False,
                    message=f"{key} must be between {param_range['min']} and {param_range['max']}",
                    range=param_range,
                )
            return ValidationResult(valid=True, range=param_range)

        if key == "auto_retry":
            if value not in ("on", "off"):
                return ValidationResult(
                    valid=False,
                    message="auto_retry must be 'on' or 'off'",
                )
            return ValidationResult(valid=True)

        return ValidationResult(
            valid=False,
            message=f"Unknown configuration parameter: {key}",
        )
