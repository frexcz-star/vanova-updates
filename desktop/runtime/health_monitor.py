"""Health Monitor — component health with auto-recovery."""
from __future__ import annotations

import copy
import time
from typing import Any

from . import ai_providers, config_store, hermes_service, process_manager
from .logger import get_logger

log = get_logger("maios.health", "health-monitor")

_WATCHDOG_STATE: dict[str, Any] = {
    "cloud_down_since": None,
    "connector_down_since": None,
    "last_recovery": {},
}
WATCHDOG_DOWN_SEC = 30
WATCHDOG_COOLDOWN_SEC = 60


# P6 (latencia): el estado de salud se consulta en cada build del contexto de
# Hermes (una vez por pregunta). Las sondas HTTP tienen timeouts de hasta ~1.5s
# por componente — un TTL corto elimina las llamadas redundantes sin perder
# frescura (2s es mucho menos que el tiempo de una respuesta del modelo).
_status_cache: dict[str, Any] | None = None
_status_cache_ts: float = 0.0
STATUS_CACHE_TTL_SECONDS = 2.0


def check_all() -> dict[str, Any]:
    global _status_cache, _status_cache_ts
    now = time.monotonic()
    if _status_cache is not None and (now - _status_cache_ts) < STATUS_CACHE_TTL_SECONDS:
        return copy.deepcopy(_status_cache)
    started = time.monotonic()
    components = {
        "maios": _check_maios(),
        "runtime": _check_runtime(),
        "hermes": _check_hermes(),
        "aiProvider": _check_ai(),
        "cloud": _check_cloud(),
        "connector": _check_connector(),
        "network": {"status": "ok", "label": "Network"},
    }
    overall = _overall_from_components(components)
    result = {"overall": overall, "components": components}
    # Solo se cachea un chequeo caro (sondas reales con timeout); un chequeo
    # rápido (mocks en tests o servicios respondiendo) no necesita caché.
    if (time.monotonic() - started) >= 0.15:
        _status_cache = result
        _status_cache_ts = time.monotonic()
    return copy.deepcopy(result)


def _overall_from_components(components: dict[str, Any]) -> str:
    """Core services (runtime, cloud) drive overall status; connector auth alone does not."""
    core = ("runtime", "cloud")
    overall = "healthy"
    optional_warnings = 0

    for key in core:
        comp = components.get(key, {})
        st = comp.get("status")
        if comp.get("stale"):
            return "degraded"
        if st == "critical":
            return "degraded"
        if st != "ok":
            overall = "degraded"

    for key, comp in components.items():
        if key in core or key == "network":
            continue
        st = comp.get("status")
        if st in ("ok", "unknown"):
            continue
        # Connector running but awaiting re-register is non-blocking for the whole system.
        if key == "connector" and st == "warning":
            continue
        if st == "warning":
            optional_warnings += 1
        elif st == "critical":
            optional_warnings += 2

    if overall == "healthy" and optional_warnings >= 2:
        return "degraded"
    return overall


def attempt_recovery(component: str) -> dict[str, Any]:
    log.info("Attempting recovery for %s", component)
    if component == "hermes":
        ok = hermes_service.restart()
        return {"recovered": ok, "message": "Hermes restarted" if ok else "Could not restart Hermes"}
    if component == "connector":
        result = process_manager.restart_connector()
        if result.get("recovered"):
            return result
        process_manager.stop_all()
        result = process_manager.start_all()
        ok = result.get("connector", False)
        return {"recovered": ok, "message": "Connector reiniciado" if ok else "Recovery failed"}
    if component in ("cloud", "maios", "runtime"):
        process_manager.stop_all()
        result = process_manager.start_all()
        ok = result.get("cloud", False)
        return {"recovered": ok, "message": "Services restarted" if ok else "Recovery failed"}
    return {"recovered": False, "message": f"No recovery action for {component}"}


def watchdog_tick() -> dict[str, Any]:
    """Background watchdog — auto-recover cloud/connector after sustained failure."""
    health = check_all()
    components = health.get("components", {})
    now = time.time()
    actions: list[str] = []

    for key in ("cloud", "connector"):
        comp = components.get(key, {})
        st = comp.get("status")
        down_key = f"{key}_down_since"
        if st == "ok":
            _WATCHDOG_STATE[down_key] = None
            continue
        # Connector process up but unauthenticated needs registration, not restart loops.
        if key == "connector" and comp.get("running") and not comp.get("authenticated"):
            _WATCHDOG_STATE[down_key] = None
            continue
        if _WATCHDOG_STATE[down_key] is None:
            _WATCHDOG_STATE[down_key] = now
            continue
        if now - _WATCHDOG_STATE[down_key] < WATCHDOG_DOWN_SEC:
            continue
        last = _WATCHDOG_STATE["last_recovery"].get(key, 0)
        if now - last < WATCHDOG_COOLDOWN_SEC:
            continue
        attempts = int(_WATCHDOG_STATE["last_recovery"].get(f"{key}_count", 0))
        if attempts >= 3:
            continue
        log.info("Watchdog: %s unhealthy for %.0fs — attempting recovery", key, now - _WATCHDOG_STATE[down_key])
        result = attempt_recovery(key)
        _WATCHDOG_STATE["last_recovery"][key] = now
        _WATCHDOG_STATE["last_recovery"][f"{key}_count"] = attempts + 1
        if result.get("recovered"):
            _WATCHDOG_STATE[down_key] = None
            _WATCHDOG_STATE["last_recovery"][f"{key}_count"] = 0
        actions.append(f"{key}:{result.get('message', 'recovery')}")

    return {"actions": actions, "health": health}


def _check_maios() -> dict:
    from . import updater

    cfg = config_store.load()
    versions = {}
    try:
        from shared.version_info import version_bundle

        versions = version_bundle()
    except Exception:
        versions = {"maios": updater.current_version()}
    installed = updater.current_version()
    return {
        "status": "ok" if cfg.get("setupComplete") else "warning",
        "label": "VANOVA",
        "version": installed,
        "versions": versions,
        "setupComplete": bool(cfg.get("setupComplete")),
    }


def _check_runtime() -> dict:
    from . import port_utils

    if port_utils.probe_runtime():
        return {"status": "ok", "label": "Runtime", "running": True, "message": "Online"}
    # Responds on /api/health but lacks files or configPath — stale process on 8765.
    if port_utils._probe_health(
        f"http://127.0.0.1:{port_utils.RUNTIME_PORT}/api/health",
        check=lambda data: data.get("service") == "vanova-desktop-runtime",
    ):
        return {
            "status": "warning",
            "label": "Runtime",
            "running": True,
            "message": "Runtime desactualizado — reiniciar",
            "action": "restart",
            "stale": True,
        }
    return {
        "status": "critical",
        "label": "Runtime",
        "running": False,
        "message": "Runtime no disponible — puerto 8765",
        "action": "restart",
    }


def _check_hermes() -> dict:
    from . import hermes_chat

    ready = hermes_chat.chat_ready(force=True)
    if ready.get("ready"):
        msg = f"Online — {ready.get('aiProvider') or ready.get('model') or 'IA configurada'}"
        return {"status": "ok", "label": "Hermes", "running": True, "message": msg, "chatReady": True}
    reason = ready.get("reason") or "offline"
    hints = {
        "ollama_offline": "Ollama no responde en localhost:11434",
        "model_unreachable": "Modelo no disponible en Ollama",
        "ai_not_configured": "IA no configurada — ejecuta ollama launch hermes",
        "hermes_cli_missing": "Hermes CLI no encontrado",
    }
    msg = hints.get(reason, "Hermes no listo para chat")
    installed = ready.get("hermesInstalled")
    return {
        "status": "warning" if installed else "warning",
        "label": "Hermes",
        "running": False,
        "chatReady": False,
        "action": "restart" if installed else None,
        "message": msg,
    }


def _check_ai() -> dict:
    s = ai_providers.get_provider_status()
    return {"status": "ok" if s["configured"] else "warning", "label": "AI Provider", **s}


def _check_cloud() -> dict:
    from . import port_utils
    from shared.version_info import CLOUD_API_VERSION, current_version

    s = process_manager.status()["cloud"]
    row = {
        "status": "ok" if s["running"] else "critical",
        "label": "Cloud",
        "version": CLOUD_API_VERSION,
        "maiosVersion": current_version(),
        **s,
    }
    if not s["running"]:
        ports = port_utils.check_ports()
        cloud_port = ports.get("cloud", {})
        if cloud_port.get("status") == "blocked":
            row["message"] = cloud_port.get("message", "Puerto 8000 ocupado")
            row["hint"] = cloud_port.get("hint")
        else:
            row["message"] = "Cloud no disponible — puerto 8000"
    return row


def _connector_label(running: bool, authenticated: bool, *, recovering: bool = False) -> str:
    if recovering:
        return "↻ Reconectando..."
    if running and authenticated:
        return "● Connector conectado"
    if running and not authenticated:
        return "⚠ Connector requiere autenticación"
    if not running:
        return "○ Connector desconectado"
    return "✕ Connector no disponible"


def _check_connector() -> dict:
    s = process_manager.status()["connector"]
    running = s.get("running", False)
    authenticated = s.get("authenticated", False)
    cloud_available = s.get("cloudAvailable", False)
    row: dict[str, Any] = {
        "status": "ok" if running and authenticated else "warning",
        "label": "Connector",
        **s,
    }
    if not cloud_available and running:
        row["message"] = "✕ Connector no disponible — Cloud offline"
        row["action"] = "restart"
    elif not running:
        row["message"] = _connector_label(False, False)
        row["action"] = "restart"
    elif not authenticated:
        row["message"] = _connector_label(True, False)
        if not s.get("hasDeviceKey"):
            row["hint"] = "Falta la clave del dispositivo — se generará al registrar este PC."
        else:
            row["hint"] = "Registra este PC como dispositivo para conectar con Cloud."
        row["action"] = "register"
        row["authRequired"] = True
    else:
        row["message"] = _connector_label(True, True)
    return row
