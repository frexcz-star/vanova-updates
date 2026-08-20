"""Structured logging for VANOVA Desktop — never logs secrets."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .paths import logs_dir
from .observability import get_correlation_id

_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*['\"]?\S+", re.I),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"shpat_[a-zA-Z0-9]+"),
]


def _redact(msg: str) -> str:
    out = msg
    for pat in _SECRET_PATTERNS:
        out = pat.sub("***REDACTED***", out)
    return out


class JsonlHandler(logging.Handler):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
            "component": getattr(record, "component", "desktop"),
            "correlationId": get_correlation_id(),
        }
        # Logging must never make a user operation fail if the disk or log
        # directory is temporarily unavailable.
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            self.handleError(record)


def get_logger(name: str, component: str = "desktop") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log_path = logs_dir() / "maios-desktop.jsonl"
    h = JsonlHandler(log_path)
    h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(h)
    # Console in dev
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s"))
    log.addHandler(ch)

    class ComponentAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            extra = kwargs.setdefault("extra", {})
            extra["component"] = self.extra["component"]
            return msg, kwargs

    return ComponentAdapter(log, {"component": component})  # type: ignore
