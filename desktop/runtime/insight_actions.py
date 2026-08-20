"""Persist user actions on AI insights (approve / reject / dismiss)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import data_dir
from .logger import get_logger

log = get_logger("maios.insight_actions")

ACTIONS_FILE = data_dir() / "insight-actions.json"
VALID_ACTIONS = frozenset({"approved", "rejected", "dismissed"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_all() -> dict[str, str]:
    if not ACTIONS_FILE.exists():
        return {}
    try:
        raw = json.loads(ACTIONS_FILE.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items() if v in VALID_ACTIONS}
    except json.JSONDecodeError:
        log.warning("Corrupt insight-actions file — resetting")
    return {}


def save_all(actions: dict[str, str]) -> None:
    ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ACTIONS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(actions, indent=2), encoding="utf-8")
    tmp.replace(ACTIONS_FILE)


def action_for(insight_id: str) -> str | None:
    """Return the persisted decision for an insight, if one exists."""
    return load_all().get(str(insight_id or "").strip())


def is_actioned(insight_id: str) -> bool:
    """Whether an insight has already been handled by the owner."""
    return action_for(insight_id) in VALID_ACTIONS


def set_action(insight_id: str, action: str) -> dict[str, Any]:
    insight_id = (insight_id or "").strip()
    action = (action or "").strip().lower()
    if not insight_id:
        return {"ok": False, "error": "insight_id required"}
    if action not in VALID_ACTIONS:
        return {"ok": False, "error": f"invalid action: {action}"}

    actions = load_all()
    actions[insight_id] = action
    save_all(actions)
    log.info("Insight action recorded: %s -> %s", insight_id, action)
    return {"ok": True, "insight_id": insight_id, "action": action, "at": _now()}
