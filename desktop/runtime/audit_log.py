"""Structured security/operations audit log (Phase 14)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .paths import logs_dir

AUDIT_FILE = logs_dir() / "audit.jsonl"
_SENSITIVE_RE = re.compile(
    r"(token|password|secret|apikey|api_key|authorization|bearer|refresh)",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            if _SENSITIVE_RE.search(str(key)):
                out[key] = "[REDACTED]"
            else:
                out[key] = _redact(val)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def record(actor: str, action: str, detail: str | dict | None = None) -> None:
    entry = {
        "ts": _now(),
        "actor": actor,
        "action": action,
        "detail": _redact(detail) if detail is not None else "",
    }
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent(limit: int = 50) -> list[dict[str, Any]]:
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in reversed(lines[-limit:]):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
