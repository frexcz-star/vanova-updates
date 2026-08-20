"""Hermes Service — decoupled Hermes lifecycle management."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from typing import Any

import httpx

from . import config_store, hermes_config
from .logger import get_logger
from .paths import app_root, config_dir

log = get_logger("maios.hermes", "hermes-service")

HERMES_URL = os.getenv("HERMES_URL", "http://127.0.0.1:8642")
PING_INTERVAL_SECONDS = 12
DEFAULT_OLLAMA_LAUNCH_MODEL = "deepseek-v4-flash:cloud"
_process: subprocess.Popen | None = None
_ollama_serve_process: subprocess.Popen | None = None
_ollama_launch_attempted = False
_warm_lock = threading.Lock()
_warm_thread: threading.Thread | None = None
_stop_warm = threading.Event()
_cached_health: dict[str, Any] = {"healthy": False, "checkedAt": 0.0, "latencyMs": None}


def status() -> dict[str, Any]:
    cfg = config_store.load().get("hermes", {})
    hcfg = hermes_config.load_config()
    running = _health_check()
    warmed = bool(_cached_health.get("healthy"))
    ollama = hermes_config.check_ollama() if hcfg.get("ollamaLaunch") else None
    return {
        "installed": cfg.get("installed", False) or _find_hermes() is not None,
        "running": running,
        "path": cfg.get("path", "") or (_find_hermes() or ""),
        "url": HERMES_URL,
        "healthy": running,
        "warmed": warmed,
        "latencyMs": _cached_health.get("latencyMs"),
        "checkedAt": _cached_health.get("checkedAt"),
        "launchMode": "ollama-launch" if hcfg.get("ollamaLaunch") else "standalone",
        "hermesConfigPath": hcfg.get("path") or "",
        "ollamaRunning": ollama.get("running") if ollama else None,
        "activeModel": hcfg.get("model") or "",
        "activeProvider": hcfg.get("providerId") or "",
    }


def install(progress_callback=None, skip_start: bool = False) -> dict[str, Any]:
    """Configure Hermes — detect existing install or guide user path."""
    steps = [
        ("Downloaded", _step_detect),
        ("Installed", _step_configure_path),
        ("Configured", _step_write_env),
    ]
    if not skip_start:
        steps.extend([("Started", _step_start), ("Health check passed", _step_health)])
    else:
        steps.append(("Health check passed", lambda: (True, "Deferred to Settings")))
    results = []
    for label, fn in steps:
        if progress_callback:
            progress_callback(label, "running")
        ok, detail = fn()
        results.append({"step": label, "ok": ok, "detail": detail})
        if progress_callback:
            progress_callback(label, "ok" if ok else "failed")
        if not ok and label != "Health check passed":
            log.warning("Hermes step failed: %s — %s", label, detail)
    all_ok = all(r["ok"] for r in results[:-1]) or results[-1]["ok"]
    config_store.save({"hermes": {"installed": True, "running": all_ok, "path": _find_hermes() or ""}})
    return {"ok": all_ok, "steps": results}


def ensure_ollama_launch(model: str = DEFAULT_OLLAMA_LAUNCH_MODEL) -> dict[str, Any]:
    """Ensure Ollama (11434) and Hermes config exist — auto-starts on VANOVA boot."""
    global _ollama_serve_process, _ollama_launch_attempted

    ollama = hermes_config.check_ollama()
    hcfg = hermes_config.load_config()
    if ollama.get("running") and hcfg.get("found") and _find_hermes():
        return {
            "ok": True,
            "started": False,
            "ollamaRunning": True,
            "message": "Ollama y Hermes ya activos",
        }

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        return {
            "ok": False,
            "started": False,
            "ollamaRunning": ollama.get("running"),
            "message": "Ollama no encontrado en PATH — instala Ollama primero",
        }

    started = False

    if not ollama.get("running"):
        try:
            if _ollama_serve_process is None or _ollama_serve_process.poll() is not None:
                log.info("Starting ollama serve (background)")
                _ollama_serve_process = subprocess.Popen(
                    [ollama_bin, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                started = True
            for _ in range(24):
                time.sleep(0.5)
                ollama = hermes_config.check_ollama()
                if ollama.get("running"):
                    break
        except Exception as exc:
            log.warning("Could not start ollama serve: %s", exc)

    hcfg = hermes_config.load_config()
    if (not hcfg.get("found") or not _find_hermes()) and not _ollama_launch_attempted:
        _ollama_launch_attempted = True
        launch_model = model or DEFAULT_OLLAMA_LAUNCH_MODEL
        # VANOVA NUNCA descarga modelos LOCALES de Ollama por su cuenta:
        # "ollama launch hermes" bajaria el modelo si no existe. Los modelos
        # cloud (:cloud) van por API y no descargan nada local, asi que se
        # permiten. Con un modelo local, solo se lanza si ya esta instalado
        # (check_ollama devuelve la lista de /api/tags).
        is_cloud_model = ":cloud" in launch_model
        if not is_cloud_model and launch_model not in (ollama.get("models") or []):
            log.warning(
                "Modelo local %s no instalado en Ollama — VANOVA no lo descarga automaticamente",
                launch_model,
            )
            return {
                "ok": False,
                "started": started,
                "ollamaRunning": bool(ollama.get("running")),
                "hermesConfigFound": bool(hcfg.get("found")),
                "message": (
                    f"Modelo local {launch_model} no instalado — instala con: "
                    f"ollama pull {launch_model}"
                ),
            }
        try:
            log.info("Running: ollama launch hermes --model %s", launch_model)
            proc = subprocess.run(
                [ollama_bin, "launch", "hermes", "--model", launch_model],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            started = True
            if proc.returncode != 0:
                log.warning(
                    "ollama launch hermes rc=%s stderr=%s",
                    proc.returncode,
                    (proc.stderr or "")[:500],
                )
            else:
                log.info("ollama launch hermes completed")
        except subprocess.TimeoutExpired:
            log.info("ollama launch hermes timed out — may still be starting")
            started = True
        except Exception as exc:
            log.warning("ollama launch hermes failed: %s", exc)

    ollama = hermes_config.check_ollama()
    hcfg = hermes_config.load_config()
    ok = bool(ollama.get("running") and hcfg.get("found") and _find_hermes())
    return {
        "ok": ok,
        "started": started,
        "ollamaRunning": bool(ollama.get("running")),
        "hermesConfigFound": bool(hcfg.get("found")),
        "message": (
            "Hermes listo"
            if ok
            else (
                "Ollama no responde en localhost:11434"
                if not ollama.get("running")
                else "Hermes config.yaml no encontrado"
            )
        ),
    }


def ensure_running() -> bool:
    """Start Hermes if needed — uses cached health when recent."""
    if _cached_health.get("healthy") and (time.time() - float(_cached_health.get("checkedAt") or 0)) < PING_INTERVAL_SECONDS:
        return True
    return start()


def start_warm_pool() -> None:
    """Keep Hermes warm with periodic health pings (call once at app startup)."""
    global _warm_thread
    with _warm_lock:
        if _warm_thread and _warm_thread.is_alive():
            return
        _stop_warm.clear()
        _warm_thread = threading.Thread(target=_warm_loop, name="maios-hermes-warm", daemon=True)
        _warm_thread.start()
        log.info("Hermes warm pool started (ping every %ds)", PING_INTERVAL_SECONDS)


def stop_warm_pool() -> None:
    _stop_warm.set()


def warm_status() -> dict[str, Any]:
    return dict(_cached_health)


def start() -> bool:
    global _process
    hcfg = hermes_config.load_config()
    if hcfg.get("ollamaLaunch") or not hcfg.get("found"):
        launch = ensure_ollama_launch()
        if launch.get("ok"):
            _record_health(True)
            return True
    if _health_check():
        _record_health(True)
        return True
    hermes = _find_hermes()
    if not hermes:
        log.warning("Hermes not found")
        _record_health(False)
        return False

    hcfg = hermes_config.load_config()
    # ollama launch hermes: chat uses CLI + config.yaml; Ollama on 11434 is the backend.
    if hcfg.get("ollamaLaunch"):
        ollama = hermes_config.check_ollama()
        if ollama.get("running"):
            log.info("Hermes ollama-launch mode — Ollama OK, CLI chat ready (no hermes serve spawn)")
            _record_health(True)
            return True
        log.warning("ollama-launch mode but Ollama offline: %s", ollama.get("message"))
        _record_health(False)
        return False

    try:
        _process = subprocess.Popen(
            [hermes, "serve", "--port", "8642"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for _ in range(12):
            if _health_check():
                _record_health(True)
                return True
            time.sleep(0.25)
        ok = _health_check()
        _record_health(ok)
        return ok
    except Exception as e:
        log.error("Failed to start Hermes: %s", e)
        _record_health(False)
        return False


def stop() -> bool:
    global _process
    if _process and _process.poll() is None:
        _process.terminate()
        _process = None
        return True
    return not _health_check()


def restart() -> bool:
    stop()
    time.sleep(1)
    return start()


def _find_hermes() -> str | None:
    cfg_path = config_store.load().get("hermes", {}).get("path")
    if cfg_path and os.path.isfile(cfg_path):
        return cfg_path
    for path in (config_dir() / "connector.env", app_root() / "connector" / ".env"):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("HERMES_CLI="):
                    val = line.split("=", 1)[1].strip()
                    if val and os.path.isfile(val):
                        return val
    return shutil.which("hermes")


def _health_check() -> bool:
    started = time.perf_counter()
    ok = False
    hcfg = hermes_config.load_config()
    try:
        with httpx.Client(timeout=1.5) as client:
            r = client.get(f"{HERMES_URL}/health")
            ok = r.status_code == 200
    except Exception:
        try:
            port = int((hcfg.get("apiServer") or {}).get("port") or 8642)
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.8)
            sock.close()
            ok = True
        except OSError:
            ok = False
    # ollama-launch: CLI + Ollama is enough even if api_server on 8642 is down
    if not ok and hcfg.get("ollamaLaunch") and _find_hermes():
        ollama = hermes_config.check_ollama()
        ok = bool(ollama.get("running"))
    if ok:
        _cached_health["latencyMs"] = round((time.perf_counter() - started) * 1000, 1)
    return ok


def _record_health(healthy: bool) -> None:
    _cached_health.update({"healthy": healthy, "checkedAt": time.time()})


def _warm_loop() -> None:
    time.sleep(0.5)
    while not _stop_warm.is_set():
        try:
            hcfg = hermes_config.load_config()
            if hcfg.get("ollamaLaunch") or not hcfg.get("found"):
                ollama = hermes_config.check_ollama()
                if not ollama.get("running"):
                    ensure_ollama_launch()
            if not _health_check():
                start()
            else:
                _record_health(True)
        except Exception as exc:
            log.debug("Hermes warm ping: %s", exc)
            _record_health(False)
        if _stop_warm.wait(PING_INTERVAL_SECONDS):
            break


def _step_detect() -> tuple[bool, str]:
    path = _find_hermes()
    if path:
        return True, path
    return True, "Will configure during setup"


def _step_configure_path() -> tuple[bool, str]:
    path = _find_hermes()
    if path:
        config_store.save({"hermes": {"path": path, "installed": True}})
        return True, path
    return True, "Hermes path can be set in Settings"


def _step_write_env() -> tuple[bool, str]:
    path = _find_hermes()
    if not path:
        return True, "Skipped — no Hermes binary"
    from .process_manager import _ensure_env_files
    _ensure_env_files()
    env_path = config_dir() / "connector.env"
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "HERMES_CLI=" in content:
        lines = []
        for line in content.splitlines():
            if line.startswith("HERMES_CLI="):
                lines.append(f"HERMES_CLI={path}")
            else:
                lines.append(line)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        env_path.write_text(content + f"\nHERMES_CLI={path}\n", encoding="utf-8")
    return True, "Configured"


def _step_start() -> tuple[bool, str]:
    if not _find_hermes():
        return True, "Skipped — Hermes not installed yet"
    ok = start()
    return ok, "Running" if ok else "Could not start — configure manually in Settings"


def _step_health() -> tuple[bool, str]:
    if not _find_hermes():
        return True, "Pending manual configuration"
    return _health_check(), "Healthy" if _health_check() else "Offline"
