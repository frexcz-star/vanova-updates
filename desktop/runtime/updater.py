"""VANOVA Updater — production update system (refactored from basic check)."""
from __future__ import annotations

import json
from typing import Any

from .paths import app_root, version_file
from .logger import get_logger
from .update.update_manager import UpdateManager
from .update import state_store

log = get_logger("maios.updater", "updater")

_manager: UpdateManager | None = None


def current_version() -> str:
    vf = version_file()
    if vf.exists():
        return json.loads(vf.read_text(encoding="utf-8-sig")).get("version", "0.0.0")
    return "0.0.0"


def get_manager() -> UpdateManager:
    global _manager
    if _manager is None:
        _manager = UpdateManager()
    return _manager


def check_for_updates(force: bool = False) -> dict[str, Any]:
    return get_manager().check_for_updates(force=force)


def get_update_status() -> dict[str, Any]:
    return get_manager().get_status()


def download_update() -> dict[str, Any]:
    return get_manager().download_update()


def install_update() -> dict[str, Any]:
    return get_manager().install_update()


def cancel_update() -> dict[str, Any]:
    return get_manager().cancel()


def startup_recovery() -> dict[str, Any]:
    return get_manager().startup_recovery()


def postpone_update(version: str = "", hours: float | None = None) -> dict[str, Any]:
    return get_manager().postpone_update(version=version, hours=hours)


def export_diagnostics() -> dict[str, Any]:
    """Full diagnostics payload for UI (Phase 28)."""
    try:
        from . import diagnostics_service

        return diagnostics_service.run_diagnostics()
    except Exception as exc:
        log.warning("diagnostics_service failed, using minimal payload: %s", exc)
        from .paths import logs_dir

        try:
            st = get_update_status()
        except Exception:
            st = {}
        return {
            "version": current_version(),
            "overall": "degraded",
            "checks": [],
            "updates": {
                "state": st.get("state", "unknown"),
                "channel": st.get("channel"),
                "lastCheck": st.get("lastCheck"),
            },
            "logsPath": str(logs_dir()),
            "error": str(exc),
        }
