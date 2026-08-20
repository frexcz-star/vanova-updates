"""Integration lifecycle states for commercial UX (Phase 26)."""
from __future__ import annotations

from typing import Any

from . import config_store, facturascripts_sync, integrations_store, shopify_sync

LIFECYCLE_STATES = frozenset(
    {"disconnected", "connecting", "connected", "syncing", "partial", "error", "reauth_required"}
)


def shopify_lifecycle() -> dict[str, Any]:
    cfg = integrations_store.get_config("shopify")
    sync = shopify_sync.sync_status()
    connected = bool(cfg.get("connected"))
    state = "disconnected"
    user_message = sync.get("userMessage") or ""
    missing = list(sync.get("missingScopes") or [])

    entry = integrations_store.get_shopify_entry()
    credential_source = str(entry.get("source") or "")

    if not connected:
        bridge = integrations_store.sync_shopify_from_hermes_if_needed()
        if bridge and bridge.get("imported"):
            cfg = integrations_store.get_config("shopify")
            connected = bool(cfg.get("connected"))
            sync = shopify_sync.sync_status()
            missing = list(sync.get("missingScopes") or [])
            user_message = sync.get("userMessage") or ""
            entry = integrations_store.get_shopify_entry()
            credential_source = str(entry.get("source") or "")

    if connected:
        status = str(sync.get("status") or "idle")
        if status == "syncing":
            state = "syncing"
        elif missing or sync.get("scopeErrors"):
            bridge = integrations_store.sync_shopify_from_hermes_if_needed()
            if bridge and bridge.get("imported"):
                sync = shopify_sync.sync_status()
                missing = list(sync.get("missingScopes") or [])
                user_message = sync.get("userMessage") or ""
                entry = integrations_store.get_shopify_entry()
                credential_source = str(entry.get("source") or "")
                status = str(sync.get("status") or "idle")
            if missing or sync.get("scopeErrors"):
                state = "reauth_required"
                if not user_message and missing:
                    user_message = "Faltan permisos de Shopify: " + ", ".join(missing)
            elif status == "error":
                state = "error"
            elif sync.get("partial"):
                state = "partial"
            else:
                state = "connected"
        elif status == "error":
            state = "error"
        elif sync.get("partial"):
            state = "partial"
        else:
            state = "connected"

    actions: list[str] = []
    if connected:
        actions = ["sync_now", "reconfigure", "disconnect"]
    else:
        actions = ["connect"]

    label = _state_label(state)
    if credential_source == "hermes-env":
        if state == "connected":
            label = "Conectado vía Hermes"
        elif state == "reauth_required":
            label = "Conectado vía Hermes — permisos insuficientes"

    return {
        "integration": "shopify",
        "state": state,
        "connected": connected,
        "url": cfg.get("url", ""),
        "lastSync": sync.get("lastSync"),
        "status": sync.get("status", "idle"),
        "userMessage": user_message or None,
        "missingScopes": missing,
        "counts": sync.get("counts") or {},
        "intervalSeconds": sync.get("intervalSeconds"),
        "actions": actions,
        "label": label,
        "credentialSource": credential_source or None,
    }


def facturascript_lifecycle() -> dict[str, Any]:
    cfg = integrations_store.get_config("facturascript")
    sync = facturascripts_sync.sync_status()
    connected = bool(cfg.get("base_url") and cfg.get("api_key"))
    state = "disconnected"
    if connected:
        status = str(sync.get("status") or "idle")
        if status == "syncing":
            state = "syncing"
        elif status == "error":
            state = "error"
        elif status == "partial":
            state = "partial"
        elif sync.get("ok") and sync.get("lastSync"):
            state = "connected"
        else:
            state = "connected"  # configured but not synced yet
    return {
        "integration": "facturascript",
        "state": state,
        "connected": connected,
        "url": cfg.get("base_url", ""),
        "lastSync": sync.get("lastSync"),
        "status": sync.get("status", "idle"),
        "userMessage": sync.get("userMessage") or None,
        "counts": sync.get("counts") or {},
        "intervalSeconds": sync.get("intervalSeconds"),
        "actions": ["sync_now", "reconfigure", "disconnect"] if connected else ["connect"],
        "label": _state_label(state),
        "credentialSource": None,
    }


def list_lifecycles() -> list[dict[str, Any]]:
    return [shopify_lifecycle(), facturascript_lifecycle()]


def _state_label(state: str) -> str:
    labels = {
        "disconnected": "Desconectado",
        "connecting": "Conectando…",
        "connected": "Conectado",
        "syncing": "Sincronizando…",
        "partial": "Sync parcial",
        "error": "Error",
        "reauth_required": "Permisos insuficientes",
    }
    return labels.get(state, state)
