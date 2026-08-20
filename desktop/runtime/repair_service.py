"""Repair installation — fixes runtime/deps/cloud without deleting user data."""
from __future__ import annotations

from typing import Any

from . import config_store, process_manager
from .startup_gate import validate_startup
from .startup_log import emit


def run_repair(*, reinstall_deps: bool = True) -> dict[str, Any]:
    """Attempt to repair core services. Never deletes user workspaces or credentials."""
    emit("REPAIR_STARTED", status="running")
    actions: list[str] = []

    try:
        if reinstall_deps:
            process_manager._ensure_venv()
            actions.append("venv_ready")
    except Exception as exc:
        emit("REPAIR_COMPLETE", status="failed", error=str(exc))
        return {
            "ok": False,
            "status": "failed",
            "actions": actions,
            "error": str(exc),
            "error_code": "DEPENDENCY_INSTALL_FAILED",
        }

    try:
        process_manager.stop_all()
        actions.append("services_stopped")
    except Exception:
        pass

    try:
        svc = process_manager.start_all()
        if svc.get("cloud"):
            actions.append("cloud_started")
        if svc.get("connector"):
            actions.append("connector_started")
        actions.extend(f"warning:{w}" for w in svc.get("warnings", []))
    except Exception as exc:
        emit("REPAIR_COMPLETE", status="failed", error=str(exc))
        return {
            "ok": False,
            "status": "failed",
            "actions": actions,
            "error": str(exc),
            "error_code": "CLOUD_START_FAILED",
        }

    # Preserve user config — only ensure files exist
    try:
        config_store.load()
        actions.append("config_ok")
    except Exception as exc:
        actions.append(f"config_warn:{exc}")

    gate = validate_startup(install_deps=False)
    emit("REPAIR_COMPLETE", status=gate["status"])
    return {
        "ok": gate["status"] in ("success", "partial"),
        "status": gate["status"],
        "actions": actions,
        "gate": gate,
    }
