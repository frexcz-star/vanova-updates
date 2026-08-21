"""Persistent configuration store for VANOVA Desktop."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .paths import config_dir, data_dir
from .logger import get_logger

log = get_logger("maios.config")

_config_lock = threading.Lock()
_config_corrupt = False
# BUG-024: lock dedicado para serializar el RMW de credentials.json (archivo
# de API keys). Se usa un lock separado de _config_lock porque este protege
# maios.json y credentials.json es un archivo distinto.
_credentials_lock = threading.Lock()
CONFIG_FILE = config_dir() / "maios.json"
# Legacy flag — no longer used as source of truth (kept for cleanup only).
SETUP_FLAG = data_dir() / ".setup_complete"


def load() -> dict[str, Any]:
    with _config_lock:
        _migrate_legacy_setup_flag_unlocked()
        return _read_config_body()


def save(data: dict[str, Any]) -> None:
    with _config_lock:
        # FASE 9 hardening: un config corrupto NUNCA se sobrescribe en silencio.
        # Antes de guardar se resguarda el archivo dañado; si el resguardo no
        # puede hacerse, se aborta el guardado para no perder los datos.
        if _config_corrupt and CONFIG_FILE.exists():
            try:
                backup = CONFIG_FILE.with_name(f"maios.corrupt-{int(time.time())}.json")
                CONFIG_FILE.replace(backup)
                log.warning("Config corrupto resguardado en %s antes de guardar", backup)
            except OSError as exc:
                log.error("No se pudo resguardar el config corrupto (%s) — se aborta el guardado", exc)
                return
        current = _read_config_body()
        current.update(data)
        _write_atomic_unlocked(current)


def update(mutator: Any) -> dict[str, Any]:
    """BUG-006 FIX: read-modify-write ATÓMICO bajo un solo lock.

    El API server usa ThreadingHTTPServer — cada request corre en su propio
    hilo. El patrón `load()` → modificar → `save()` NO está serializado: aunque
    load() y save() toman _config_lock individualmente, el RMW completo no, así
    que dos requests concurrentes pueden hacer lost-update (el que guarda
    primero se pierde si el otro leyó antes).

    ``mutator`` recibe el config actual (dict) y devuelve el dict a persistir
    (o None para no escribir). Todo el ciclo load→modify→save ocurre bajo un
    único _config_lock, garantizando atomicidad entre hilos.

    Devuelve el config persistido (el resultado de mutator).
    """
    with _config_lock:
        current = _read_config_body()
        result = mutator(current)
        if result is not None:
            _write_atomic_unlocked(result)
            return result
        return current


def _read_config_body() -> dict[str, Any]:
    global _config_corrupt
    if not CONFIG_FILE.exists():
        _config_corrupt = False
        return _defaults()
    for attempt in range(5):
        try:
            parsed = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
            _config_corrupt = False
            return {**_defaults(), **parsed}
        except json.JSONDecodeError:
            _config_corrupt = True
            log.warning("Config corrupto (%s) — se usa defaults y se resguarda antes del próximo guardado", CONFIG_FILE)
            return _defaults()
        except OSError as exc:
            if attempt < 4:
                time.sleep(0.02 * (attempt + 1))
                continue
            log.warning("Config read failed (%s) — using defaults", exc)
            return _defaults()
    return _defaults()


def remove_keys(keys) -> dict[str, Any]:
    """Remove top-level keys from the persisted config (full-file rewrite).

    Unlike save() — which MERGES into the existing config, so popping keys from
    a loaded dict does not remove them from disk — this writes the whole file
    without those keys. Used for "clean and re-import" and factory reset so
    derived state (findings, insights, recommendations, memory) truly
    disappears instead of surviving silently.
    """
    to_remove = [str(k) for k in (keys or [])]
    with _config_lock:
        current = _read_config_body()
        removed: list[str] = []
        for k in to_remove:
            if k in current:
                current.pop(k, None)
                removed.append(k)
        if removed:
            _write_atomic_unlocked(current)
            log.info("Config keys removed: %s", ", ".join(removed))
        return current


def reset_to_defaults() -> dict[str, Any]:
    """Factory reset: overwrite the ENTIRE config with pristine defaults.

    Replaces the whole file instead of merging, so every user-generated key
    disappears: business data, findings, insights, recommendations, memory,
    history, notifications, integrations. The installation secret (runtime
    token) lives outside maios.json (install_secrets) and is preserved.
    """
    with _config_lock:
        fresh = _defaults()
        _write_atomic_unlocked(fresh)
        log.info("Config reset to pristine defaults (factory reset)")
        return fresh


def is_setup_complete() -> bool:
    return bool(load().get("setupComplete", False))


def mark_setup_complete() -> None:
    save({"setupComplete": True, "setupCompletedAt": _now()})
    _remove_legacy_setup_flag()


def reset_setup() -> None:
    """Reset onboarding/setup state — single source of truth in maios.json."""
    save({"setupComplete": False, "setupCompletedAt": None})
    _remove_legacy_setup_flag()
    log.info("Setup state reset")


def is_architecture_dismissed() -> bool:
    return bool(load().get("architectureDismissed", False))


def get_ui_prefs() -> dict[str, Any]:
    """Return user interface preferences from the local source of truth."""
    data = load()
    prefs = data.get("uiPrefs") or {}
    return dict(prefs) if isinstance(prefs, dict) else {}


def save_ui_prefs(prefs: dict[str, Any] | None) -> dict[str, Any]:
    """Persist validated UI preferences without touching business data."""
    incoming = prefs if isinstance(prefs, dict) else {}
    current = get_ui_prefs()
    merged = dict(current)
    if "homeCards" in incoming and isinstance(incoming.get("homeCards"), list):
        merged["homeCards"] = [str(x)[:40] for x in incoming["homeCards"][:4]]
    if "fontFamily" in incoming:
        merged["fontFamily"] = str(incoming.get("fontFamily") or "inter")[:40]
    save({"uiPrefs": merged})
    return merged


def dismiss_architecture() -> None:
    save({"architectureDismissed": True, "architectureDismissedAt": _now()})
    log.info("Hermes architecture onboarding dismissed")


def _write_atomic(data: dict[str, Any]) -> None:
    with _config_lock:
        _write_atomic_unlocked(data)


def _write_atomic_unlocked(data: dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    if CONFIG_FILE.exists():
        try:
            existing = CONFIG_FILE.read_text(encoding="utf-8-sig")
            if existing == serialized:
                return
        except OSError:
            pass
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    for attempt in range(5):
        try:
            tmp.write_text(serialized, encoding="utf-8")
            os.replace(tmp, CONFIG_FILE)
            log.info("Configuration saved to %s", CONFIG_FILE)
            return
        except OSError as exc:
            if attempt < 4:
                time.sleep(0.02 * (attempt + 1))
                continue
            raise exc


def _migrate_legacy_setup_flag() -> None:
    with _config_lock:
        _migrate_legacy_setup_flag_unlocked()


def _migrate_legacy_setup_flag_unlocked() -> None:
    """One-time migration: legacy .setup_complete flag -> maios.json, then remove flag."""
    if not SETUP_FLAG.exists():
        return
    try:
        current: dict[str, Any] = {}
        if CONFIG_FILE.exists():
            current = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        if current.get("setupComplete") is False:
            _remove_legacy_setup_flag()
            return
        if not current.get("setupComplete"):
            current["setupComplete"] = True
            if not current.get("setupCompletedAt"):
                current["setupCompletedAt"] = _now()
            _write_atomic_unlocked({**_defaults(), **current})
            log.info("Migrated legacy .setup_complete flag into maios.json")
    except Exception as exc:
        log.warning("Legacy setup flag migration failed: %s", exc)
    finally:
        _remove_legacy_setup_flag()


def _remove_legacy_setup_flag() -> None:
    try:
        if SETUP_FLAG.exists():
            SETUP_FLAG.unlink()
    except OSError as exc:
        log.warning("Could not remove legacy setup flag: %s", exc)


def _defaults() -> dict[str, Any]:
    from .paths import app_root
    import json as _json

    version = "0.9.0"
    vf = app_root() / "version.json"
    if vf.exists():
        version = _json.loads(vf.read_text(encoding="utf-8-sig")).get("version", version)
    return {
        "version": version,
        "setupComplete": False,
        "setupCompletedAt": None,
        "companyProfile": {},
        "aiProviders": {},
        "agents": [],
        "hermes": {"installed": False, "running": False, "path": ""},
        "installationPlan": {},
        "lastScan": None,
        "dashboardSnapshot": None,
        "scanFiles": [],
        "scanExclusions": [],
        "organizedProducts": [],
        "organizedSales": [],
        "organizedCustomers": [],
        "organizedSuppliers": [],
        "organizedInvoices": [],
        "organizedInvoiceLines": [],
        "organizedFinance": [],
        "facturascriptSync": None,
        "financialReconciliation": None,
        "dataNormalizationVersion": 0,
        # FASE 14 — gobernanza de datos: versión de esquema, última migración y
        # última validación de integridad. Una actualización NUNCA asume que los
        # datos heredados son correctos sin evidencia.
        "dataGovernance": {
            "dataSchemaVersion": 0,
            "dataMigrationVersion": "",
            "dataCreatedByVersion": "",
            "lastMigrationAt": None,
            "lastIntegrityCheck": None,
            "lastDataValidation": None,
            "lastIntegrityStatus": "never_run",
            "migrationStatus": "never_run",
            "lastIntegritySummary": None,
            "lastMigrationReport": None,
        },
        "fileOrganization": None,
        "shopifySync": None,
        "architectureDismissed": False,
        "architectureDismissedAt": None,
        "uiPrefs": {},
        "hermesActivity": None,
        "autonomyLevel": "approval_required",
        "onboardingProfile": {},
    }


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def secure_store_credentials(provider_id: str, api_key: str) -> None:
    """Store API key encrypted in a separate credentials file with restricted permissions.

    BUG-024 FIX: antes hacía read→modify→write SIN lock sobre credentials.json,
    perdiendo API keys de providers configurados concurrentemente
    (ThreadingHTTPServer). Ahora el RMW completo corre bajo _credentials_lock.
    """
    from . import credential_vault

    cred_path = config_dir() / "credentials.json"
    with _credentials_lock:
        creds: dict = {}
        if cred_path.exists():
            try:
                creds = json.loads(cred_path.read_text(encoding="utf-8"))
            except Exception:
                creds = {}
            if not isinstance(creds, dict):
                creds = {}
        creds[provider_id] = {"apiKey": credential_vault.encrypt_if_needed(api_key)}
        cred_path.write_text(json.dumps(creds, ensure_ascii=False), encoding="utf-8")
    if os.name == "nt":
        try:
            import subprocess
            subprocess.run(
                ["icacls", str(cred_path), "/inheritance:r", "/grant:r", f"{os.getenv('USERNAME')}:F"],
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception:
            pass


def get_credential(provider_id: str) -> str | None:
    from . import credential_vault

    cred_path = config_dir() / "credentials.json"
    if not cred_path.exists():
        return None
    creds = json.loads(cred_path.read_text(encoding="utf-8"))
    stored = creds.get(provider_id, {}).get("apiKey")
    if not stored:
        return None
    return credential_vault.decrypt_value(str(stored))


def ensure_install_secrets() -> dict[str, Any]:
    """Ensure per-installation secrets exist (delegates to install_secrets)."""
    from .install_secrets import ensure_install_secrets as _ensure

    return _ensure()


def rotateRuntimeCredentials(**kwargs: Any) -> dict[str, Any]:
    """Rotate local runtime credentials without breaking install identity."""
    from .install_secrets import rotateRuntimeCredentials as _rotate

    return _rotate(**kwargs)
