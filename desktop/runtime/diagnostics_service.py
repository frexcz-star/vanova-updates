"""Real diagnostics checks for the UI (Phase 28)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import backup_service, config_store, health_monitor, integrations_lifecycle, port_utils, task_queue
from .logger import get_logger
from .observability import get_correlation_id
from .paths import data_dir, logs_dir
from . import updater

log = get_logger("maios.diagnostics", "diagnostics")

# Only these checks can mark the whole system as critical.
_CORE_CRITICAL_IDS = frozenset({"runtime_port", "health_runtime", "health_cloud"})


def run_diagnostics() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # Runtime / ports
    ports = port_utils.check_ports()
    runtime_port = ports.get("runtime", {})
    checks.append(
        {
            "id": "runtime_port",
            "category": "connectivity",
            "status": "ok" if runtime_port.get("status") == "ok" else "critical",
            "label": "Runtime local",
            "message": runtime_port.get("message") or "Puerto 8765",
        }
    )

    health = health_monitor.check_all()
    for key in ("runtime", "cloud", "connector", "hermes", "aiProvider"):
        comp = health.get("components", {}).get(key, {})
        st = comp.get("status", "unknown")
        if st == "ok":
            diag_st = "ok"
        elif st == "warning":
            diag_st = "warning"
        elif key == "connector":
            diag_st = "warning"
        else:
            diag_st = "warning" if key not in ("runtime", "cloud") else "critical"
        checks.append(
            {
                "id": f"health_{key}",
                "category": "services",
                "status": diag_st,
                "label": comp.get("label", key),
                "message": comp.get("message") or st,
            }
        )

    # Databases + backups
    for row in backup_service.database_health():
        checks.append({**row, "category": "data"})

    backup_st = backup_service.status()
    latest = backup_st.get("latest")
    checks.append(
        {
            "id": "backups",
            "category": "data",
            "status": "ok" if latest else "warning",
            "label": "Copias de seguridad",
            "message": f"Última: {latest.get('createdAt', 'ninguna')[:19]}" if latest else "Sin copias aún",
            "count": backup_st.get("count", 0),
        }
    )

    # Shopify lifecycle
    shop = integrations_lifecycle.shopify_lifecycle()
    shop_status = _shopify_diag_status(shop["state"])
    shop_msg = shop.get("label") or "Shopify"
    if shop.get("userMessage"):
        shop_msg += f" — {shop['userMessage']}"
    elif shop["state"] == "reauth_required" and shop.get("missingScopes"):
        shop_msg += " — faltan permisos: " + ", ".join(shop["missingScopes"])
    checks.append(
        {
            "id": "shopify",
            "category": "integrations",
            "status": shop_status,
            "label": "Shopify",
            "message": shop_msg,
            "state": shop["state"],
        }
    )

    # Task queue
    queue = task_queue.get_queue_status()
    checks.append(
        {
            "id": "task_queue",
            "category": "automation",
            "status": "ok",
            "label": "Cola de tareas",
            "message": f"{queue.get('running', 0)} en ejecución · {queue.get('queued', 0)} en cola",
        }
    )

    setup_ok = config_store.is_setup_complete()
    checks.append(
        {
            "id": "setup",
            "category": "config",
            "status": "ok" if setup_ok else "warning",
            "label": "Setup completado",
            "message": "Sí" if setup_ok else "Pendiente — ejecuta el asistente inicial",
        }
    )

    try:
        upd = updater.get_update_status()
    except Exception as exc:
        log.warning("Update status in diagnostics failed: %s", exc)
        upd = {}

    overall = _overall_from_checks(checks)
    versions = {}
    try:
        from shared.version_info import version_bundle

        versions = version_bundle()
    except Exception:
        versions = {"maios": updater.current_version()}
    return {
        "version": updater.current_version(),
        "versions": versions,
        "correlationId": get_correlation_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "checks": checks,
        "health": health,
        "ports": ports,
        "updates": {
            "state": upd.get("state", "unknown"),
            "channel": upd.get("channel"),
            "lastCheck": upd.get("lastCheck"),
            "targetVersion": upd.get("targetVersion"),
            "installedVersion": upd.get("installedVersion"),
            "history": upd.get("history", [])[:5],
        },
        "backups": backup_st,
        "integrations": integrations_lifecycle.list_lifecycles(),
        "logsPath": str(logs_dir()),
        "dataPath": str(data_dir()),
    }


def _shopify_diag_status(state: str) -> str:
    if state == "connected":
        return "ok"
    if state in ("disconnected", "partial", "syncing", "reauth_required", "error"):
        return "warning"
    return "warning"


def _overall_from_checks(checks: list[dict[str, Any]]) -> str:
    """Align with health_monitor: only core outages are critical; integrations are warnings."""
    has_warning = False
    for check in checks:
        st = check.get("status")
        cid = str(check.get("id") or "")
        if st == "critical" and cid in _CORE_CRITICAL_IDS:
            return "critical"
        if st in ("warning", "critical"):
            has_warning = True
    if has_warning:
        return "degraded"
    return "healthy"
