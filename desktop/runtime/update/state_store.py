"""Update state persistence — crash-safe transaction log."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..paths import data_dir
from .state_machine import UpdateState


def state_file() -> Path:
    path = data_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path / "update-state.json"


def history_file() -> Path:
    path = data_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path / "update-history.json"


def load_state() -> dict[str, Any]:
    sf = state_file()
    if not sf.exists():
        return _default_state()
    try:
        return {**_default_state(), **json.loads(sf.read_text(encoding="utf-8-sig"))}
    except json.JSONDecodeError:
        return _default_state()


def save_state(data: dict[str, Any]) -> None:
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    state_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _default_state() -> dict[str, Any]:
    return {
        "state": UpdateState.IDLE.value,
        "installedVersion": "",
        "targetVersion": "",
        "progress": 0,
        "downloadedBytes": 0,
        "totalBytes": 0,
        "message": "",
        "error": None,
        "manifest": None,
        "packagePath": "",
        "backupPath": "",
        "lastCheck": None,
        "channel": "stable",
        "postInstallPending": False,
    }


def set_state(state: UpdateState, **kwargs: Any) -> dict[str, Any]:
    current = load_state()
    current["state"] = state.value
    current.update(kwargs)
    save_state(current)
    return current


def append_history(entry: dict[str, Any]) -> None:
    hf = history_file()
    history = []
    if hf.exists():
        try:
            history = json.loads(hf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    history.insert(0, entry)
    hf.write_text(json.dumps(history[:20], indent=2), encoding="utf-8")


def get_history() -> list[dict[str, Any]]:
    hf = history_file()
    if not hf.exists():
        return []
    try:
        return json.loads(hf.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def load_config() -> dict[str, Any]:
    cfg_path = data_dir() / "updates" / "updates-config.json"
    defaults = {
        "channel": "stable",
        "autoCheck": True,
        "autoDownload": False,
        "checkIntervalHours": 4,
        "postponeHours": 24,
        "manifestUrl": "",
        "lastCheck": None,
        "postponedVersion": None,
        "postponedUntil": None,
    }
    if not cfg_path.exists():
        return defaults
    text = cfg_path.read_text(encoding="utf-8-sig")
    return {**defaults, **json.loads(text)}


def save_config(cfg: dict[str, Any]) -> None:
    cfg_path = data_dir() / "updates" / "updates-config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
