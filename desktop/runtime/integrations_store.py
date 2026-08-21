"""Local persistence for integration configs (Shopify, ERP, etc.)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .paths import data_dir
from .logger import get_logger
from . import credential_vault

log = get_logger("maios.integrations")

CONFIG_FILE = data_dir() / "integrations.json"
VALID_IDS = frozenset({"shopify", "erp", "mcp", "email", "instagram", "gmail", "drive", "facturascript"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        log.warning("Corrupt integrations file — resetting")
        return {}


def _save_store(data: dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


def _decrypt_entry(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    for key in ("token", "pass", "api_key", "access_token"):
        if out.get(key):
            out[key] = credential_vault.decrypt_value(str(out[key]))
    return out


def _encrypt_sensitive_fields(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for key in ("token", "pass", "api_key", "access_token"):
        if out.get(key):
            out[key] = credential_vault.encrypt_if_needed(str(out[key]))
    return out


def _validate_id(integration_id: str) -> str | None:
    integration_id = (integration_id or "").strip().lower()
    if not integration_id or integration_id not in VALID_IDS:
        return None
    return integration_id


def get_config(integration_id: str) -> dict[str, Any]:
    iid = _validate_id(integration_id)
    if not iid:
        return {"connected": False, "error": "invalid integration"}
    entry = _load_store().get(iid)
    if not entry or not entry.get("connected"):
        return {"connected": False}
    public = {"connected": True}
    if entry.get("url"):
        public["url"] = entry["url"]
    if entry.get("user"):
        public["user"] = entry["user"]
    # Never expose secrets in GET responses
    if entry.get("token"):
        public["tokenSet"] = True
    if entry.get("pass"):
        public["passwordSet"] = True
    if entry.get("access_token"):
        public["tokenSet"] = True
    if entry.get("api_key"):
        public["passwordSet"] = True
    return public


def _normalize_shop_url(url: str) -> str:
    u = (url or "").strip().lower().rstrip("/")
    if u.startswith("https://"):
        u = u[8:]
    elif u.startswith("http://"):
        u = u[7:]
    return u


def get_shopify_credentials() -> dict[str, str]:
    """Return Shopify URL/token for background sync (runtime only)."""
    entry = _load_store().get("shopify") or {}
    if not entry.get("connected"):
        return {}
    entry = _decrypt_entry(entry)
    return {
        "url": (entry.get("url") or "").rstrip("/"),
        "token": entry.get("token") or "",
    }


def get_gmail_credentials() -> dict[str, str]:
    """Return decrypted Gmail credentials for the skill bridge (runtime only).

    Never logs or returns raw secrets to callers outside the runtime. Mirrors
    get_shopify_credentials so the Gmail skill bridge has a single public
    accessor instead of reaching into the private store.
    """
    entry = _load_store().get("gmail") or {}
    if not entry.get("connected"):
        return {"connected": False}
    entry = _decrypt_entry(entry)
    return {
        "connected": True,
        "user": str(entry.get("user") or "").strip(),
        "pass": str(entry.get("pass") or entry.get("password") or ""),
    }


def get_shopify_entry() -> dict[str, Any]:
    """Full decrypted Shopify entry (includes metadata like source)."""
    entry = _load_store().get("shopify") or {}
    if not entry:
        return {}
    return _decrypt_entry(entry)


def clear_stale_shopify_sync_errors() -> None:
    """Drop cached permission errors after credentials validate successfully.

    BUG-022 FIX: antes hacía config_store.save({"shopifySync": {...}}) que
    REEMPLAZABA todo el objeto shopifySync con solo 6 campos, perdiendo
    lastSync/counts/status/message/guardAlerts/guard/backfill/startedAt de la
    última sync válida. Ahora hace un UPDATE (merge) de los 6 campos de error
    sobre el dict existente, preservando los metadatos de la última sync.
    """
    from . import config_store

    def _mutate(cfg: dict[str, object]) -> dict[str, object]:
        st = cfg.get("shopifySync") or {}
        if not isinstance(st, dict):
            st = {}
        if not (st.get("missingScopes") or st.get("errorCategory") == "permission_denied"):
            return cfg
        # Merge: solo actualiza los campos de error, conserva el resto.
        st["missingScopes"] = []
        st["scopeErrors"] = []
        st["errorCategory"] = None
        st["lastError"] = None
        st["userMessage"] = None
        st["partial"] = False
        cfg["shopifySync"] = st
        return cfg

    config_store.update(_mutate)


def sync_shopify_from_hermes_if_needed() -> dict[str, Any] | None:
    """Refresh an ALREADY-CONFIGURED Shopify integration from Hermes .env.

    Isolation guarantee (B-01): a fresh VANOVA installation NEVER inherits
    credentials from a machine-global Hermes `.env`. External connections
    must be authorized explicitly for THIS installation: the guided setup
    flow (hermes_shopify_setup) is the only path that imports Hermes
    credentials, and it shows the shop + data to sync and asks for consent
    first. Without an explicit `connected` config here, this function is a
    no-op — no credential is read, no sync is triggered.

    Only when the installation already owns a Shopify config for the SAME
    shop may the token be refreshed from Hermes `.env` (token rotation on an
    existing, explicitly-connected integration — never a shop switch).
    """
    from . import hermes_config, shopify_sync

    entry = get_shopify_entry()
    if not entry.get("connected"):
        # No explicit Shopify config in THIS installation → never auto-import.
        return {"imported": False, "source": "maios", "ok": False, "reason": "not_configured"}

    hermes = hermes_config.load_hermes_shopify_credentials()
    if not hermes.get("url") or not hermes.get("token"):
        return None

    current = get_shopify_credentials()
    same_shop = (
        not current.get("url")
        or _normalize_shop_url(current["url"]) == _normalize_shop_url(hermes["url"])
    )

    if current.get("url") and not same_shop:
        log.warning(
            "Hermes Shopify shop differs from VANOVA (%s vs %s) — not auto-importing",
            _normalize_shop_url(current["url"]),
            _normalize_shop_url(hermes["url"]),
        )
        return {"imported": False, "source": "maios", "ok": False, "reason": "shop_mismatch"}

    hermes_check = shopify_sync.check_credentials(hermes["url"], hermes["token"])
    hermes_granted = list(hermes_check.get("grantedScopes") or [])
    if hermes_check.get("error") and not hermes_granted:
        log.debug("Hermes Shopify token rejected: %s", hermes_check.get("error"))
        return {
            "imported": False,
            "source": "hermes",
            "ok": False,
            "missingScopes": hermes_check.get("missingScopes") or [],
            "userMessage": hermes_check.get("userMessage") or hermes_check.get("error"),
        }

    token_aligned = current.get("token") == hermes["token"]
    if token_aligned:
        if hermes_check.get("ok"):
            clear_stale_shopify_sync_errors()
        return {
            "imported": False,
            "source": entry.get("source") or "maios",
            "ok": bool(hermes_check.get("ok")),
            "alreadyAligned": True,
            "missingScopes": hermes_check.get("missingScopes") or [],
        }

    # Hermes .env is the source of truth for Shopify when the shop matches.
    store = _load_store()
    prev = store.get("shopify") or {}
    payload: dict[str, Any] = {
        "connected": True,
        "updatedAt": _now(),
        "url": hermes["url"],
        "token": hermes["token"],
        "source": "hermes-env",
    }
    if prev.get("url") and not payload.get("url"):
        payload["url"] = prev["url"]
    store["shopify"] = _encrypt_sensitive_fields(payload)
    _save_store(store)
    log.info("Synced VANOVA Shopify credentials from Hermes .env (%s)", _normalize_shop_url(hermes["url"]))
    if hermes_check.get("ok"):
        clear_stale_shopify_sync_errors()
    _trigger_shopify_sync()
    return {
        "imported": True,
        "source": "hermes-env",
        "ok": bool(hermes_check.get("ok")),
        "url": hermes["url"],
        "grantedScopes": hermes_granted,
        "missingScopes": hermes_check.get("missingScopes") or [],
    }


def save_config(integration_id: str, body: dict[str, Any]) -> dict[str, Any]:
    iid = _validate_id(integration_id)
    if not iid:
        return {"ok": False, "error": "invalid integration"}

    url = (body.get("url") or body.get("shopUrl") or body.get("storeUrl") or "").strip()
    token = (body.get("token") or "").strip()
    user = (body.get("user") or "").strip()
    password = (body.get("password") or body.get("pass") or body.get("app_password") or "").strip()

    if iid == "shopify":
        if url and not url.lower().startswith(("http://", "https://")):
            url = "https://" + url.lstrip("/")
        if not url or not token:
            return {"ok": False, "error": "URL y token de Shopify son obligatorios"}

    store = _load_store()
    prev = store.get(iid, {})
    payload: dict[str, Any] = {
        "connected": True,
        "updatedAt": _now(),
    }
    if url:
        payload["url"] = url
    elif prev.get("url"):
        payload["url"] = prev["url"]
    if token:
        payload["token"] = token
    elif prev.get("token"):
        payload["token"] = prev["token"]
    if user:
        payload["user"] = user
    elif prev.get("user"):
        payload["user"] = prev["user"]
    if password:
        payload["pass"] = password
    elif prev.get("pass"):
        payload["pass"] = prev["pass"]
    if body.get("access_token"):
        payload["access_token"] = str(body["access_token"]).strip()
    if body.get("base_url"):
        payload["base_url"] = str(body["base_url"]).strip().rstrip("/")
    if body.get("api_key"):
        payload["api_key"] = str(body["api_key"]).strip()
    if body.get("db_path"):
        payload["db_path"] = str(body["db_path"]).strip()
    if body.get("mode"):
        payload["mode"] = str(body["mode"]).strip()

    store[iid] = _encrypt_sensitive_fields(payload)
    _save_store(store)
    log.info("Integration config saved: %s", iid)
    if iid == "gmail":
        # Provision the Hermes email skill so the agent can actually USE the
        # mailbox (this is the missing inverse bridge; see gmail_skill_bridge).
        _trigger_gmail_skill_sync()
    if iid == "shopify":
        scope_result = _validate_shopify(
            payload.get("url", ""),
            credential_vault.decrypt_value(str(payload.get("token", ""))),
        )
        _trigger_shopify_sync()
        response: dict[str, Any] = {
            "ok": True,
            "connected": True,
            "url": payload.get("url", ""),
        }
        if scope_result.get("missingScopes"):
            response["scopeWarning"] = True
            response["missingScopes"] = scope_result.get("missingScopes")
            response["userMessage"] = scope_result.get("userMessage")
        if scope_result.get("error") and not scope_result.get("ok"):
            response["scopeWarning"] = True
            response["userMessage"] = scope_result.get("userMessage") or scope_result.get("error")
        return response
    return {"ok": True, "connected": True, "url": payload.get("url", "")}


def disconnect(integration_id: str) -> dict[str, Any]:
    """Mark integration disconnected without deleting stored URL metadata."""
    iid = _validate_id(integration_id)
    if not iid:
        return {"ok": False, "error": "invalid integration"}
    store = _load_store()
    prev = store.get(iid, {})
    store[iid] = {
        "connected": False,
        "disconnectedAt": _now(),
        "url": prev.get("url", ""),
    }
    _save_store(store)
    log.info("Integration disconnected: %s", iid)
    if iid == "shopify":
        from . import config_store

        config_store.save(
            {
                "shopifySync": {
                    "status": "idle",
                    "lastError": None,
                    "userMessage": None,
                    "missingScopes": [],
                }
            }
        )
    return {"ok": True, "connected": False, "integration": iid}


def _validate_shopify(url: str, token: str) -> dict[str, Any]:
    try:
        from . import shopify_sync

        return shopify_sync.check_credentials(url, token)
    except Exception as exc:
        log.warning("Shopify scope validation failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _trigger_shopify_sync() -> None:
    try:
        import threading
        from . import shopify_sync

        threading.Thread(target=shopify_sync.sync_now, daemon=True).start()
    except Exception as exc:
        log.warning("Could not start Shopify sync: %s", exc)


def _trigger_gmail_skill_sync() -> None:
    """Provision the Hermes email skill from the freshly saved Gmail config.

    Runs in a background thread so the save response is never blocked by a
    filesystem write. Idempotent: writing the same himalaya config twice is a
    no-op rename.
    """
    try:
        import threading
        from . import gmail_skill_bridge

        threading.Thread(target=gmail_skill_bridge.sync_from_integrations_store, daemon=True).start()
    except Exception as exc:
        log.warning("Could not start Gmail skill sync: %s", exc)
