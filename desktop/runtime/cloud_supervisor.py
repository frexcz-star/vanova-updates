"""VANOVA Cloud Supervisor — external watchdog for the cloud service.

BUG-063 (HIGH): the cloud (uvicorn on :8000) died silently and nothing
relaunched it. Root cause: the watchdog lived INSIDE the runtime process
(launcher.py health_watchdog thread -> health_monitor.watchdog_tick). When the
runtime also died, the watchdog died with it, and the Electron app (the only
thing that relaunches the runtime) was not running -> the cloud stayed dead
indefinitely.

Fix: a SEPARATE, DETACHED supervisor process that survives the runtime's death.
It is spawned by the launcher with DETACHED_PROCESS (so it is not killed when
the launcher/runtime exits) and independently watches both the cloud (:8000)
and the runtime (:8765), relaunching whichever is down.

This module is intentionally self-contained: it must NOT import
process_manager (whose in-memory state dies with the runtime) or health_monitor
(whose watchdog thread dies with the runtime). It only uses paths/port_utils
for stable, stateless helpers.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure runtime package is importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from desktop.runtime import port_utils  # noqa: E402
from desktop.runtime.paths import app_root, config_dir, logs_dir, python_executable  # noqa: E402

CLOUD_URL = "http://127.0.0.1:8000"
CLOUD_PORT = 8000
RUNTIME_PORT = port_utils.RUNTIME_PORT  # 8765

# Tuning (seconds).
POLL_INTERVAL = 15
DOWN_GRACE_SEC = 30      # how long a component must be down before we act
COOLDOWN_SEC = 60        # min gap between relaunches of the same component
MAX_RESTARTS = 5         # cap per component to avoid a crash-loop hammering

# Marker file: the supervisor writes its PID here so the launcher can avoid
# spawning a duplicate supervisor on every runtime start.
SUPERVISOR_PID_FILE = "cloud_supervisor.pid"


def _log(msg: str) -> None:
    try:
        with open(logs_dir() / "cloud-supervisor.log", "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            return client.get(url).status_code == 200
    except Exception:
        return False


def _cloud_ok() -> bool:
    return _http_ok(f"{CLOUD_URL}/api/health")


def _runtime_ok() -> bool:
    return _http_ok(f"http://127.0.0.1:{RUNTIME_PORT}/api/health")


def _spawn_cloud() -> bool:
    """Relaunch the cloud (uvicorn cloud.main:app) exactly like process_manager."""
    root = app_root()
    py = str(python_executable())
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    log_file = logs_dir() / "cloud.log"
    cmd = [py, "-m", "uvicorn", "cloud.main:app", "--host", "127.0.0.1", "--port", "8000"]
    try:
        with open(log_file, "a", encoding="utf-8") as err_log:
            subprocess.Popen(
                cmd,
                cwd=str(root),
                env=env,
                stdout=err_log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        _log("Cloud relaunched by supervisor")
        return True
    except Exception as exc:  # pragma: no cover - defensive
        _log(f"Failed to relaunch cloud: {exc}")
        return False


def _spawn_runtime() -> bool:
    """Relaunch the runtime (launcher.py) so its internal watchdog returns."""
    root = app_root()
    py = str(python_executable())
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    launcher = root / "desktop" / "runtime" / "launcher.py"
    log_file = logs_dir() / "runtime-launcher.log"
    cmd = [py, str(launcher)]
    try:
        with open(log_file, "a", encoding="utf-8") as err_log:
            subprocess.Popen(
                cmd,
                cwd=str(root),
                env=env,
                stdout=err_log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        _log("Runtime relaunched by supervisor")
        return True
    except Exception as exc:  # pragma: no cover - defensive
        _log(f"Failed to relaunch runtime: {exc}")
        return False


def _write_pid() -> None:
    try:
        (config_dir() / SUPERVISOR_PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass


def _already_running() -> bool:
    """True if another supervisor is alive (avoid duplicate spawns)."""
    try:
        pid_file = config_dir() / SUPERVISOR_PID_FILE
        if not pid_file.exists():
            return False
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if pid == os.getpid():
            return False
        # On Windows, a process is "alive" if we can open it with 0 access.
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def run() -> None:
    _log("Cloud supervisor started (pid=%d)" % os.getpid())
    _write_pid()

    down_since: dict[str, float] = {}
    last_restart: dict[str, float] = {}
    restart_count: dict[str, int] = {}

    while True:
        try:
            for key, ok in (("cloud", _cloud_ok()), ("runtime", _runtime_ok())):
                if ok:
                    down_since[key] = None
                    restart_count[key] = 0
                    continue
                if down_since.get(key) is None:
                    down_since[key] = time.time()
                    continue
                if time.time() - down_since[key] < DOWN_GRACE_SEC:
                    continue
                if time.time() - last_restart.get(key, 0) < COOLDOWN_SEC:
                    continue
                if restart_count.get(key, 0) >= MAX_RESTARTS:
                    continue
                _log(f"{key} down for {time.time() - down_since[key]:.0f}s — relaunching")
                ok_spawn = _spawn_cloud() if key == "cloud" else _spawn_runtime()
                last_restart[key] = time.time()
                restart_count[key] = restart_count.get(key, 0) + 1
                if ok_spawn:
                    down_since[key] = None
        except Exception as exc:  # pragma: no cover - defensive
            _log(f"Supervisor loop error: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if _already_running():
        _log("Another supervisor is already running — exiting")
        sys.exit(0)
    run()
