"""Hermes activity log — visible steps for organize/sync/chat operations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import config_store

MAX_LOG = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_step(message: str, *, step: str = "info", source: str = "hermes") -> dict[str, Any]:
    entry = {"step": step, "message": message, "source": source, "at": _now()}
    # BUG-011 FIX: RMW atómico bajo un solo lock. Antes hacía load() → modificar
    # → save() sin serializar; el API server (ThreadingHTTPServer) y el scheduler
    # pueden invocar log_step concurrentemente y perder un step. update() cubre
    # todo el ciclo load→modify→save bajo _config_lock.
    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        activity = dict(cfg.get("hermesActivity") or {})
        log = list(activity.get("log") or [])
        log.append(entry)
        activity["current"] = message
        activity["step"] = step
        activity["source"] = source
        activity["updatedAt"] = _now()
        activity["log"] = log[-MAX_LOG:]
        cfg["hermesActivity"] = activity
        return cfg

    config_store.update(_mutate)
    return entry


def current() -> dict[str, Any]:
    data = config_store.load()
    activity = data.get("hermesActivity") or {}
    org = data.get("fileOrganization") or {}
    shop = data.get("shopifySync") or {}
    return {
        "current": activity.get("current") or org.get("message") or shop.get("status", ""),
        "step": activity.get("step") or org.get("status") or shop.get("status") or "idle",
        "log": activity.get("log") or [],
        "organize": {
            "status": org.get("status", "idle"),
            "message": org.get("message", ""),
        },
        "shopify": {
            "status": shop.get("status", "idle"),
            "lastSync": shop.get("lastSync"),
            "counts": shop.get("counts") or {},
            "lastError": shop.get("lastError"),
        },
    }


def clear() -> None:
    config_store.save({"hermesActivity": {"current": "", "step": "idle", "log": []}})


def wants_organize(message: str) -> bool:
    """True only for explicit organize/sync requests — not generic data questions."""
    m = (message or "").lower().strip()
    if not m:
        return False
    explicit = (
        "organiza mis",
        "organizar mis",
        "organiza los archivos",
        "organizar archivos",
        "organiza archivos",
        "reorganiza",
        "clasifica mis archivos",
        "clasificar archivos",
        "sincroniza shopify",
        "sync shopify",
        "sincronizar shopify",
        "importa mis archivos",
        "importar archivos",
        "organiza el catálogo",
        "organizar catálogo",
        "organiza el catalogo",
    )
    return any(p in m for p in explicit)


def run_organize_pipeline() -> dict[str, Any]:
    """Sync Shopify + organize local files; log each step for the UI."""
    from . import file_organizer, integrations_store, shopify_sync

    results: dict[str, Any] = {"steps": []}

    cfg = integrations_store.get_config("shopify")
    if cfg.get("connected"):
        if shopify_sync.needs_reauth():
            log_step(
                "Shopify conectado pero faltan permisos (read_products/read_orders) — "
                "los productos locales/Excel siguen disponibles; reconfigura en Integraciones.",
                step="shopify_skip",
                source="shopify",
            )
            results["shopify"] = {"ok": False, "skipped": True, "errorCategory": "permission_denied"}
        else:
            log_step("Conectando con Shopify…", step="shopify_start", source="shopify")
            sync = shopify_sync.sync_now()
            results["shopify"] = sync
            if sync.get("ok"):
                counts = sync.get("counts") or {}
                log_step(
                    f"Shopify: {counts.get('products', 0)} productos, {counts.get('orders', 0)} pedidos sincronizados.",
                    step="shopify_done",
                    source="shopify",
                )
            else:
                log_step(
                    f"Shopify: {sync.get('userMessage') or sync.get('error', 'error de sincronización')}",
                    step="shopify_error",
                    source="shopify",
                )
            results["steps"].append("shopify")
    else:
        log_step("Shopify no conectado — omitiendo sync.", step="shopify_skip", source="shopify")

    log_step("Clasificando archivos locales (productos / ventas)…", step="organize_start", source="organizer")
    org = file_organizer.organize_files(trigger_hermes=False)
    results["organize"] = org
    org_msg = (org.get("organization") or {}).get("message") or "Organización completada."
    log_step(org_msg, step="organize_done", source="organizer")
    results["steps"].append("organize")

    log_step("Actualizando Command Center y pestañas Productos/Ventas…", step="dashboard", source="organizer")
    results["steps"].append("dashboard")
    return results
