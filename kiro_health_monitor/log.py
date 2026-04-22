"""Unified logging for Kiro Health Monitor.

All modules should use `from kiro_health_monitor.log import log` instead of
`logging.getLogger(__name__)`. This ensures clean single-line
output in Kiro's MCP Logs panel without rich formatting noise.
"""

import logging
import sys

_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(message)s"))
_handler.setLevel(logging.DEBUG)

log = logging.getLogger("kiro-health-monitor")
log.addHandler(_handler)
log.setLevel(logging.INFO)
log.propagate = False
