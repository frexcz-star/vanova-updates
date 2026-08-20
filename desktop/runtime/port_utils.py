"""Port availability and stale VANOVA process recovery."""
from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Any, Callable

from .logger import get_logger

log = get_logger("maios.ports", "port-utils")

RUNTIME_PORT = 8765
CLOUD_PORT = 8000


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return False
        except OSError:
            return True


def find_pids_on_port(port: int) -> list[int]:
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        pids: list[int] = []
        needle = f":{port}"
        for line in out.stdout.splitlines():
            if needle not in line or "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pids.append(int(parts[-1]))
            except ValueError:
                continue
        return sorted(set(pids))
    except Exception as exc:
        log.warning("Could not inspect port %s: %s", port, exc)
        return []


def process_name(pid: int) -> str:
    """Executable name for a PID (Windows tasklist / POSIX ps). Empty on error."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in out.stdout.splitlines():
                if f'"{pid}"' in line:
                    parts = line.split(",")
                    if len(parts) > 1:
                        return parts[0].strip('"').lower()
            return ""
        out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True, timeout=5)
        return (out.stdout or "").strip().lower()
    except Exception as exc:
        log.warning("Could not read process name for PID %s: %s", pid, exc)
        return ""


def _looks_like_our_runtime(pid: int) -> bool:
    """True when the PID could be a VANOVA runtime process (python/hermes/
    vanova/launcher). VANOVA JAMÁS mata un proceso que no pueda identificar
    como suyo: un puerto ocupado por una app ajena se reporta como error claro,
    no se cierra la app del usuario."""
    name = process_name(pid)
    if not name:
        return False
    base = name.split(".")[0] if "." in name else name
    return any(tok in base for tok in ("python", "hermes", "vanova", "maios", "launcher", "runtime", "py"))


def kill_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return result.returncode == 0
        os.kill(pid, 15)
        return True
    except Exception as exc:
        log.warning("Failed to terminate PID %s: %s", pid, exc)
        return False


def _probe_health(url: str, *, check: Callable[[dict[str, Any]], bool]) -> bool:
    try:
        import json
        from urllib.request import urlopen

        with urlopen(url, timeout=1.5) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))
            return check(data)
    except Exception:
        return False


_probe_cache: dict[tuple[int, int], tuple[float, bool]] = {}
_PROBE_CACHE_TTL_SECONDS = 2.0


def probe_runtime(port: int = RUNTIME_PORT) -> bool:
    """P6: las sondas HTTP tienen timeouts de ~1.5s y se ejecutan en cada build
    del contexto de Hermes — TTL corto para eliminar llamadas redundantes."""
    key = (port, int(time.monotonic() // _PROBE_CACHE_TTL_SECONDS))
    hit = _probe_cache.get(key)
    if hit is not None:
        return hit
    if not _probe_health(
        f"http://127.0.0.1:{port}/api/health",
        check=lambda data: data.get("service") == "vanova-desktop-runtime",
    ):
        _probe_cache[key] = False
        return False
    # Legacy runtimes answered /api/health but lacked file inventory — treat as stale.
    try:
        import json
        from urllib.request import urlopen

        with urlopen(f"http://127.0.0.1:{port}/api/setup/status", timeout=1.5) as resp:
            if resp.status != 200:
                return False
            setup = json.loads(resp.read().decode("utf-8"))
            if "configPath" not in setup:
                return False
        # P2-1: /api/files ahora requiere token. Un 401 prueba que el servidor
        # está vivo y es nuestro runtime protegido — sigue contando como sano.
        # urlopen LANZA HTTPError para 401 (no lo devuelve como respuesta), así
        # que el 401 debe capturarse explícitamente — de lo contrario cualquier
        # runtime protegido se marcaría como "desactualizado" (regresión 3.0).
        try:
            from urllib.error import HTTPError as _HTTPError

            with urlopen(f"http://127.0.0.1:{port}/api/files", timeout=1.5) as resp:
                ok = resp.status in (200, 401)
        except _HTTPError as exc:
            ok = exc.code in (200, 401)
        except Exception:
            ok = False
        _probe_cache[key] = ok
        return ok
    except Exception:
        _probe_cache[key] = False
        return False


def runtime_config_path(port: int = RUNTIME_PORT) -> str | None:
    """configPath reportado por el runtime que escucha en `port`, o None.

    P2-2 (auditoría comercial): sirve para comprobar que un runtime ya activo
    pertenece a ESTA instalación/perfil antes de adjuntarse. Nunca se adjunta a
    un runtime de otra instalación (mezclaría datos de dos empresas)."""
    try:
        import json
        from urllib.request import urlopen

        with urlopen(f"http://127.0.0.1:{port}/api/setup/status", timeout=1.5) as resp:
            if resp.status != 200:
                return None
            setup = json.loads(resp.read().decode("utf-8"))
        cp = setup.get("configPath")
        return str(cp) if cp else None
    except Exception:
        return None


def runtime_matches_install(port: int = RUNTIME_PORT, expected_config: str | None = None) -> bool:
    """True cuando el runtime en `port` usa el MISMO config (misma instalación).

    Normaliza rutas (case + separadores) para comparar de forma fiable en
    Windows. Si el runtime activo no reporta configPath, se rechaza el attach
    (nunca asumir que es nuestra instalación)."""
    if expected_config is None:
        from . import config_store

        expected_config = str(config_store.CONFIG_FILE)
    actual = runtime_config_path(port)
    if not actual or not expected_config:
        return False
    norm = lambda p: os.path.normcase(os.path.abspath(str(p)))  # noqa: E731
    return norm(actual) == norm(expected_config)


def probe_cloud(port: int = CLOUD_PORT) -> bool:
    """True when port serves OUR cloud (right product + version).

    A legacy MAIOS cloud (old product) that survives an install/update answers /api/health
    with status ok but serves the OLD dashboard — treating it as healthy would
    leave the user inside the renamed app looking at the old branding forever.
    """

    def check(data: dict[str, Any]) -> bool:
        if data.get("status") != "ok":
            return False
        app = str(data.get("app") or "")
        if app and "vanova" not in app.lower():
            log.info("Port %s cloud belongs to another product (%r) — stale, will replace", port, app)
            return False
        try:
            from shared.version_info import current_version

            expected = current_version()
        except Exception:  # noqa: BLE001 — never let a version read break the probe
            return True
        got = str(data.get("maiosVersion") or data.get("version") or "")
        if expected and expected != "0.0.0" and got and got != expected:
            log.info("Port %s cloud version %s != %s — stale, will replace", port, got, expected)
            return False
        return True

    return _probe_health(f"http://127.0.0.1:{port}/api/health", check=check)


def ensure_port_available(
    port: int,
    *,
    label: str,
    probe: Callable[[], bool],
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Free `port` when occupied by a stale process; reuse when VANOVA is already healthy."""
    if not is_port_in_use(port):
        return {"ok": True, "port": port, "action": "free"}

    if probe():
        log.info("Port %s already serving healthy %s", port, label)
        return {"ok": True, "port": port, "action": "already_running"}

    log.info("Port %s occupied but %s not responding — attempting recovery", port, label)
    for attempt in range(max_attempts):
        # Seguridad VANOVA 3.0: solo se cierran procesos identificables como
        # runtime propio (python/hermes/vanova). Un puerto ocupado por una app
        # ajena NUNCA se mata: se reporta recovery_failed con mensaje claro.
        foreign = [pid for pid in find_pids_on_port(port) if not _looks_like_our_runtime(pid)]
        if foreign:
            return {
                "ok": False,
                "port": port,
                "action": "recovery_failed",
                "pids": foreign,
                "message": (
                    f"El puerto {port} está ocupado por un proceso que no es de VANOVA "
                    f"(PID {', '.join(map(str, foreign))}). No se cierra para no "
                    "interrumpir otra aplicación: cierra el proceso o cambia de puerto."
                ),
            }
        for pid in find_pids_on_port(port):
            kill_pid(pid)
        time.sleep(0.6)
        if not is_port_in_use(port):
            log.info("Recovered port %s for %s (attempt %d)", port, label, attempt + 1)
            return {"ok": True, "port": port, "action": "recovered"}
        if probe():
            return {"ok": True, "port": port, "action": "already_running"}

    pids = find_pids_on_port(port)
    return {
        "ok": False,
        "port": port,
        "action": "recovery_failed",
        "pids": pids,
        "message": (
            f"Port {port} is still in use after recovery attempts"
            + (f" (PID {', '.join(map(str, pids))})" if pids else "")
        ),
    }


def ensure_runtime_port(port: int = RUNTIME_PORT) -> dict[str, Any]:
    return ensure_port_available(port, label="VANOVA runtime", probe=lambda: probe_runtime(port))


def ensure_cloud_port(port: int = CLOUD_PORT) -> dict[str, Any]:
    return ensure_port_available(port, label="VANOVA Cloud", probe=lambda: probe_cloud(port))


def _port_row(port: int, *, label: str, probe: Callable[[], bool]) -> dict[str, Any]:
    """Report port occupancy and whether VANOVA is listening on it."""
    in_use = is_port_in_use(port)
    alive = probe()
    if alive:
        return {
            "port": port,
            "label": label,
            "status": "ok",
            "inUse": True,
            "occupied": True,
            "message": f"{label} activo en puerto {port}",
        }
    if in_use:
        pids = find_pids_on_port(port)
        pid_txt = f" (PID {', '.join(map(str, pids))})" if pids else ""
        return {
            "port": port,
            "label": label,
            "status": "blocked",
            "inUse": True,
            "occupied": True,
            "pids": pids,
            "message": f"Puerto {port} ocupado{pid_txt}",
            "hint": "Cierra el proceso que usa el puerto o reinicia VANOVA desde Ajustes → Diagnóstico.",
        }
    return {
        "port": port,
        "label": label,
        "status": "offline",
        "inUse": False,
        "occupied": False,
        "message": f"{label} no responde en puerto {port}",
        "hint": "Comprueba que VANOVA Desktop esté en ejecución.",
    }


def check_ports() -> dict[str, Any]:
    """UI-facing port status for runtime (8765) and Cloud (8000)."""
    runtime = _port_row(RUNTIME_PORT, label="Runtime", probe=probe_runtime)
    cloud = _port_row(CLOUD_PORT, label="Cloud", probe=probe_cloud)
    overall = "ok"
    if runtime["status"] != "ok" or cloud["status"] != "ok":
        overall = "degraded" if runtime["status"] == "ok" or cloud["status"] == "ok" else "critical"
    return {"overall": overall, "runtime": runtime, "cloud": cloud}
