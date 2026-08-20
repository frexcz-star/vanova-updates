"""Structured startup event logging for production diagnostics."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .logger import get_logger
from .observability import get_correlation_id

log = get_logger("maios.startup", "startup")

EVENTS = (
    "STARTING_RUNTIME",
    "PYTHON_RESOLVED",
    "PYTHON_VERSION",
    "DEPENDENCY_CHECK",
    "DEPENDENCY_INSTALL_FAILED",
    "STARTING_CLOUD",
    "CLOUD_COMMAND",
    "CLOUD_PID",
    "CLOUD_PORT",
    "CLOUD_HEALTH_CHECK",
    "CLOUD_READY",
    "CLOUD_START_FAILED",
    "STARTING_CONNECTOR",
    "CONNECTOR_READY",
    "STARTING_HERMES",
    "DASHBOARD_LOAD",
    "STARTUP_COMPLETE",
    "INSTALLATION_INCOMPLETE",
    "REPAIR_STARTED",
    "REPAIR_COMPLETE",
)


def emit(event: str, *, status: str = "ok", error_code: str = "", **fields: Any) -> None:
    if event not in EVENTS:
        event = event  # allow forward-compatible custom events
    payload = {
        "component": "startup",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "status": status,
        "correlationId": get_correlation_id(),
    }
    if error_code:
        payload["error_code"] = error_code
    for key, value in fields.items():
        if key.lower() in ("password", "token", "secret", "api_key", "authorization"):
            continue
        payload[key] = value
    line = json.dumps(payload, ensure_ascii=False)
    log.info(line)
