"""Process Manager — starts/stops VANOVA Cloud and Connector."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from .logger import get_logger
from .paths import app_root, config_dir, logs_dir, python_executable, venv_dir
from . import install_secrets, port_utils

log = get_logger("maios.process", "process-manager")

_cloud_proc: subprocess.Popen | None = None
_connector_proc: subprocess.Popen | None = None
_last_register_attempt: float = 0.0
REGISTER_COOLDOWN_SEC = 120.0

CLOUD_URL = "http://127.0.0.1:8000"
CLOUD_START_WAIT_SEC = 45
CLOUD_START_RETRIES = 3


def start_all() -> dict[str, Any]:
    global _cloud_proc, _connector_proc
    results = {"cloud": False, "connector": False, "warnings": []}
    _ensure_venv()
    py = str(python_executable())
    root = app_root()
    env = _service_env()

    if not _is_cloud_running():
        port_recovery = port_utils.ensure_cloud_port(8000)
        if not port_recovery.get("ok"):
            results["warnings"].append(port_recovery.get("message", "Cloud port 8000 is blocked"))
            log.warning("Cloud port blocked: %s", port_recovery.get("message"))
        elif port_recovery.get("action") == "recovered":
            results["warnings"].append("Recovered stale VANOVA Cloud on port 8000")

        for attempt in range(1, CLOUD_START_RETRIES + 1):
            if _cloud_proc and _cloud_proc.poll() is None:
                _cloud_proc.terminate()
                try:
                    _cloud_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    _cloud_proc.kill()
                _cloud_proc = None

            log_file = logs_dir() / "cloud.log"
            cloud_cmd = [py, "-m", "uvicorn", "cloud.main:app", "--host", "127.0.0.1", "--port", "8000"]
            from .startup_log import emit

            emit("CLOUD_COMMAND", command="uvicorn cloud.main:app")
            with open(log_file, "a", encoding="utf-8") as err_log:
                _cloud_proc = subprocess.Popen(
                    cloud_cmd,
                    cwd=str(root),
                    env=env,
                    stdout=err_log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            deadline = time.time() + CLOUD_START_WAIT_SEC
            while time.time() < deadline:
                if _is_cloud_running():
                    results["cloud"] = True
                    emit("CLOUD_PID", pid=_cloud_proc.pid if _cloud_proc else None)
                    emit("CLOUD_PORT", port=8000)
                    break
                if _cloud_proc.poll() is not None:
                    results["warnings"].append(
                        f"Cloud process exited early (code {_cloud_proc.returncode}) — see cloud.log"
                    )
                    break
                time.sleep(0.5)

            if results["cloud"]:
                break
            if attempt < CLOUD_START_RETRIES:
                log.info("Cloud start attempt %d failed — retrying", attempt)
                port_utils.ensure_cloud_port(8000)
                time.sleep(1.0)

        if not results["cloud"]:
            hint = _cloud_failure_hint(logs_dir() / "cloud.log")
            results["warnings"].append(hint or "Cloud did not respond in time — will retry later")
    else:
        results["cloud"] = True

    if results["cloud"]:
        if _is_connector_running():
            results["connector"] = True
            if not _connector_heartbeat_ok():
                reg = _ensure_device_registered()
                if reg:
                    log.info("Connector re-registered with Cloud")
                elif _connector_proc is None or _connector_proc.poll() is not None:
                    restart = restart_connector()
                    results["connector"] = restart.get("connector", False)
                    if not results["connector"]:
                        results["warnings"].append(restart.get("message", "Connector restart failed"))
        else:
            conn_log = logs_dir() / "connector.log"
            with open(conn_log, "a", encoding="utf-8") as err_log:
                _connector_proc = subprocess.Popen(
                    [py, str(root / "connector" / "connector.py")],
                    cwd=str(root),
                    env=env,
                    stdout=err_log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            time.sleep(1.5)
            results["connector"] = _connector_proc.poll() is None
            if results["connector"]:
                _ensure_device_registered()
            if not results["connector"]:
                results["warnings"].append("Connector stopped — see connector.log")
    elif _connector_proc and _connector_proc.poll() is None:
        results["connector"] = True

    if results["cloud"]:
        if not _ensure_owner_auth_sync():
            results["warnings"].append("Owner login credentials could not be verified — use Recuperar acceso in login")

    log.info("Services started — cloud=%s connector=%s", results["cloud"], results["connector"])
    return results


def stop_all() -> None:
    global _cloud_proc, _connector_proc
    for proc, name in [(_connector_proc, "connector"), (_cloud_proc, "cloud")]:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.info("Stopped %s", name)
    _connector_proc = None
    _cloud_proc = None


def ensure_services() -> dict[str, Any]:
    """Start cloud/connector when missing — safe to call on every runtime boot."""
    return start_all()


def restart_connector() -> dict[str, Any]:
    """Restart only the connector (keeps Cloud running)."""
    global _connector_proc
    if not _is_cloud_running():
        started = start_all()
        if not started.get("cloud"):
            return {"recovered": False, "message": "Cloud offline — cannot start connector"}
    _ensure_device_registered()
    if not _connector_heartbeat_ok() and _refresh_owner_token():
        _ensure_device_registered()
    if not _connector_heartbeat_ok():
        log.info("Connector auth still failing — force-restarting Cloud to sync credentials")
        if not _force_restart_cloud():
            return {"recovered": False, "message": "Cloud restart failed"}
        _refresh_owner_token()
        _ensure_device_registered()
    if _connector_proc and _connector_proc.poll() is None:
        _connector_proc.terminate()
        try:
            _connector_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _connector_proc.kill()
        _connector_proc = None
    py = str(python_executable())
    root = app_root()
    env = _service_env()
    conn_log = logs_dir() / "connector.log"
    with open(conn_log, "a", encoding="utf-8") as err_log:
        _connector_proc = subprocess.Popen(
            [py, str(root / "connector" / "connector.py")],
            cwd=str(root),
            env=env,
            stdout=err_log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    time.sleep(1.5)
    ok = _connector_proc.poll() is None
    auth = False
    if ok:
        auth = _ensure_device_registered()
    log.info("Connector restart — running=%s authenticated=%s", ok, auth)
    return {
        "recovered": ok and auth,
        "connector": ok,
        "authenticated": auth,
        "message": "Connector reiniciado" if ok and auth else "Connector reiniciado pero sin autenticar",
    }


def status() -> dict[str, Any]:
    _ensure_env_files()
    env = _connector_env()
    auth_meta = {
        "hasDeviceKey": bool(env.get("MAIOS_DEVICE_KEY")),
        "hasOwnerToken": bool(env.get("MAIOS_OWNER_TOKEN")),
    }
    cloud_available = _is_cloud_running()
    conn_running = _is_connector_running()
    conn_auth = _connector_heartbeat_ok() if conn_running and cloud_available else False
    if conn_running and cloud_available and not conn_auth:
        global _last_register_attempt
        now = time.time()
        if now - _last_register_attempt >= REGISTER_COOLDOWN_SEC:
            _last_register_attempt = now
            if _ensure_device_registered():
                conn_auth = True
    return {
        "cloud": {"running": cloud_available, "url": CLOUD_URL},
        "connector": {
            "running": conn_running,
            "authenticated": conn_auth,
            "registered": conn_auth,
            "cloudAvailable": cloud_available,
            "managed": _connector_proc is not None and _connector_proc.poll() is None,
            **auth_meta,
        },
    }


def _is_cloud_running() -> bool:
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{CLOUD_URL}/api/health")
            return r.status_code == 200
    except Exception:
        return False


def _is_connector_running() -> bool:
    global _connector_proc
    if _connector_proc is not None and _connector_proc.poll() is None:
        return True
    return _connector_recent_log()


def _connector_recent_log(max_age_sec: float = 90.0) -> bool:
    log_file = logs_dir() / "connector.log"
    if not log_file.exists():
        return False
    try:
        return (time.time() - log_file.stat().st_mtime) < max_age_sec
    except OSError:
        return False


def _connector_env() -> dict[str, str]:
    return _load_env_file(config_dir() / "connector.env")


def _connector_heartbeat_ok() -> bool:
    if not _is_cloud_running():
        return False
    env = _connector_env()
    device_key = env.get("MAIOS_DEVICE_KEY", "")
    if not device_key:
        return False
    cloud_url = env.get("MAIOS_CLOUD_URL", CLOUD_URL).rstrip("/")
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.post(
                f"{cloud_url}/api/connector/heartbeat",
                headers={"Authorization": f"Device {device_key}"},
            )
            return r.status_code == 200
    except Exception:
        return False


def _ensure_device_registered() -> bool:
    """Re-register device when Cloud DB was reset or connector.env lost keys."""
    _ensure_env_files()
    if _connector_heartbeat_ok():
        return True
    if _register_device_with_owner_token():
        return True
    if _refresh_owner_token() and _register_device_with_owner_token():
        log.info("Owner token refreshed and device re-registered")
        return True
    return False


def _app_version() -> str:
    try:
        from . import updater

        return updater.current_version()
    except Exception:
        try:
            from shared.version_info import current_version

            return current_version()
        except Exception:
            return "0.0.0"


def _register_device_with_owner_token() -> bool:
    env = _connector_env()
    device_key = env.get("MAIOS_DEVICE_KEY", "")
    cloud_url = env.get("MAIOS_CLOUD_URL", CLOUD_URL).rstrip("/")
    if not device_key:
        return False
    if _register_device_local(device_key, cloud_url):
        return _connector_heartbeat_ok()
    owner_token = env.get("MAIOS_OWNER_TOKEN", "")
    if not owner_token:
        return False
    try:
        import socket

        with httpx.Client(timeout=10.0) as client:
            reg = client.post(
                f"{cloud_url}/api/devices/register",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={
                    "deviceKey": device_key,
                    "name": socket.gethostname(),
                    "os": "windows",
                    "version": _app_version(),
                },
            )
            if reg.status_code not in (200, 201):
                log.warning("Device re-registration failed: HTTP %s", reg.status_code)
                return False
            return _connector_heartbeat_ok()
    except Exception as exc:
        log.warning("Device re-registration error: %s", exc)
        return False


def _register_device_local(device_key: str, cloud_url: str) -> bool:
    try:
        import socket

        with httpx.Client(timeout=10.0) as client:
            reg = client.post(
                f"{cloud_url}/api/devices/register-local",
                json={
                    "deviceKey": device_key,
                    "name": socket.gethostname(),
                    "os": "windows",
                    "version": _app_version(),
                },
            )
            if reg.status_code not in (200, 201):
                log.warning("Local device registration failed: HTTP %s", reg.status_code)
                return False
            log.info("Device registered via localhost recovery endpoint")
            return True
    except Exception as exc:
        log.warning("Local device registration error: %s", exc)
        return False


def _force_restart_cloud() -> bool:
    """Kill stale Cloud on 8000 and start a fresh instance (picks up cloud.env + bootstrap)."""
    global _cloud_proc
    from . import port_utils

    if _cloud_proc and _cloud_proc.poll() is None:
        _cloud_proc.terminate()
        try:
            _cloud_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _cloud_proc.kill()
    _cloud_proc = None
    for pid in port_utils.find_pids_on_port(8000):
        port_utils.kill_pid(pid)
    time.sleep(1.0)
    port_utils.ensure_cloud_port(8000)
    _ensure_venv()
    py = str(python_executable())
    root = app_root()
    env = _service_env()
    log_file = logs_dir() / "cloud.log"
    with open(log_file, "a", encoding="utf-8") as err_log:
        _cloud_proc = subprocess.Popen(
            [py, "-m", "uvicorn", "cloud.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(root),
            env=env,
            stdout=err_log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    deadline = time.time() + CLOUD_START_WAIT_SEC
    while time.time() < deadline:
        if _is_cloud_running():
            return True
        if _cloud_proc.poll() is not None:
            break
        time.sleep(0.5)
    return False


def _sync_owner_password_in_db() -> bool:
    """Align Cloud SQLite owner password with cloud.env (fixes post-update drift)."""
    import bcrypt
    import sqlite3

    cloud_env = _load_env_file(config_dir() / "cloud.env")
    username = cloud_env.get("MAIOS_DEMO_USER", "ceo")
    password = cloud_env.get("MAIOS_DEMO_PASSWORD", "")
    if not password:
        return False
    db_path = Path(cloud_env.get("MAIOS_DB") or str(config_dir() / "maios_cloud.db"))
    if not db_path.exists():
        return False
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            log.warning("Owner user %r not found in cloud DB", username)
            return False
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed, row[0]))
        conn.commit()
        log.info("Synced owner password for %r in cloud DB", username)
        return True
    finally:
        conn.close()


def _ensure_owner_auth_sync() -> bool:
    """Ensure cloud.env owner credentials authenticate against the running Cloud."""
    _sync_owner_password_in_db()
    if _refresh_owner_token():
        return True
    log.warning("Owner auth sync failed — restarting Cloud to apply cloud.env credentials")
    if not _force_restart_cloud():
        return False
    _sync_owner_password_in_db()
    return _refresh_owner_token()


def local_owner_session() -> dict[str, Any]:
    """Issue a Cloud JWT using local cloud.env credentials (localhost recovery)."""
    from . import config_store

    if not config_store.is_setup_complete():
        return {"ok": False, "error": "setup_incomplete"}
    if not _is_cloud_running():
        started = start_all()
        if not started.get("cloud"):
            return {"ok": False, "error": "cloud_unavailable"}
    if not _ensure_owner_auth_sync():
        return {"ok": False, "error": "auth_sync_failed"}
    cloud_env = _load_env_file(config_dir() / "cloud.env")
    username = cloud_env.get("MAIOS_DEMO_USER", "ceo")
    password = cloud_env.get("MAIOS_DEMO_PASSWORD", "")
    if not password:
        return {"ok": False, "error": "missing_owner_password"}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{CLOUD_URL}/api/auth/login",
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code != 200:
                return {"ok": False, "error": "auth_failed", "status": r.status_code}
            data = r.json() or {}
            token = data.get("access_token", "")
            if not token:
                return {"ok": False, "error": "no_token"}
            existing = _connector_env()
            existing["MAIOS_OWNER_TOKEN"] = token
            _write_connector_env(existing)
            return {
                "ok": True,
                "username": username,
                "access_token": token,
                "refresh_token": data.get("refresh_token", ""),
                "role": data.get("role", "owner"),
            }
    except Exception as exc:
        log.warning("Local owner session failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _refresh_owner_token() -> bool:
    """Obtain a fresh JWT when connector.env owner token is stale after Cloud reset."""
    cloud_env = _load_env_file(config_dir() / "cloud.env")
    username = cloud_env.get("MAIOS_DEMO_USER", "ceo")
    password = cloud_env.get("MAIOS_DEMO_PASSWORD", "")
    if not password:
        return False
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{CLOUD_URL}/api/auth/login",
                data={"username": username, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code != 200:
                log.warning("Owner token refresh login failed: HTTP %s", r.status_code)
                return False
            token = (r.json() or {}).get("access_token", "")
            if not token:
                return False
        existing = _connector_env()
        existing["MAIOS_OWNER_TOKEN"] = token
        _write_connector_env(existing)
        log.info("Refreshed MAIOS_OWNER_TOKEN in connector.env")
        return True
    except Exception as exc:
        log.warning("Owner token refresh error: %s", exc)
        return False


def _ensure_venv() -> None:
    """Ensure Python venv exists in user-writable data dir."""
    from . import python_runtime
    from .startup_log import emit

    venv_py = venv_dir() / "Scripts" / "python.exe"
    if venv_py.exists():
        missing = python_runtime.verify_dependencies(venv_py)
        if not missing:
            _ensure_env_files()
            return

    base_py = python_runtime.resolve_python(required=True)
    python_runtime.verify_python(base_py)
    emit("PYTHON_RESOLVED", python=str(base_py))

    # Packaged installs ship a complete interpreter (python-bundle) with every
    # required module already installed, and resolve_python() prefers it for all
    # subprocesses. Creating a venv + pip-installing over the internet here is
    # slow on first run (minutes) and the result is never used, so skip it.
    if python_runtime.is_production() and not python_runtime.verify_dependencies(base_py):
        emit("VENV_SKIPPED", reason="bundled interpreter has all dependencies")
        _ensure_env_files()
        return

    log.info("Creating Python environment at %s", venv_dir())
    try:
        subprocess.run(
            [str(base_py), "-m", "venv", str(venv_dir())],
            check=True,
            cwd=str(app_root()),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.CalledProcessError as exc:
        emit("DEPENDENCY_INSTALL_FAILED", status="failed", error_code=python_runtime.DEPENDENCY_INSTALL_FAILED)
        raise RuntimeError(f"Failed to create Python venv: {exc}") from exc

    py = str(venv_py)
    root = app_root()
    for req, label in (
        (root / "cloud" / "requirements.txt", "cloud"),
        (root / "connector" / "requirements.txt", "connector"),
        (root / "desktop" / "runtime" / "requirements.txt", "runtime"),
    ):
        try:
            subprocess.run(
                [py, "-m", "pip", "install", "-q", "--upgrade", "pip"],
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            subprocess.run(
                [py, "-m", "pip", "install", "-q", "-r", str(req)],
                check=True,
                cwd=str(root),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.CalledProcessError as exc:
            emit("DEPENDENCY_INSTALL_FAILED", status="failed", package=label)
            raise RuntimeError(f"DEPENDENCY_INSTALL_FAILED: {label}") from exc

    missing = python_runtime.verify_dependencies(venv_py)
    if missing:
        raise RuntimeError(f"DEPENDENCIES_MISSING: {', '.join(missing)}")

    _ensure_env_files()


def _ensure_env_files() -> None:
    import secrets

    cfg = config_dir()
    root = app_root()
    static = root / "web" / "dist"
    cloud_env = cfg / "cloud.env"
    desired_paths = {
        "MAIOS_STATIC_DIR": str(static),
        "MAIOS_DB": str(cfg / "maios_cloud.db"),
        "MAIOS_AUDIT_LOG": str(logs_dir() / "audit.jsonl"),
        "MAIOS_ENV": "production" if os.getenv("MAIOS_APP_EXE") else os.getenv("MAIOS_ENV", "development"),
        "MAIOS_ALLOWED_ORIGINS": "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:8765,http://localhost:8765",
    }

    if not cloud_env.exists():
        cloud_env.write_text(
            f"MAIOS_CLOUD_SECRET_KEY={secrets.token_urlsafe(48)}\n"
            f"MAIOS_DEMO_USER=ceo\n"
            f"MAIOS_DEMO_PASSWORD={secrets.token_urlsafe(16)}\n"
            f"MAIOS_ENV=production\n"
            f"MAIOS_ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:8765,http://localhost:8765\n"
            f"MAIOS_STATIC_DIR={desired_paths['MAIOS_STATIC_DIR']}\n"
            f"MAIOS_DB={desired_paths['MAIOS_DB']}\n"
            f"MAIOS_AUDIT_LOG={desired_paths['MAIOS_AUDIT_LOG']}\n",
            encoding="utf-8",
        )
    else:
        existing = _load_env_file(cloud_env)
        updated = False
        for key, value in desired_paths.items():
            current = existing.get(key, "")
            if current != value and (not current or not Path(current).exists() or key != "MAIOS_AUDIT_LOG"):
                existing[key] = value
                updated = True
        if updated:
            lines = [f"{k}={v}" for k, v in existing.items()]
            cloud_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log.info("Updated cloud.env paths for current install")

    conn_env = cfg / "connector.env"
    existing = _load_env_file(conn_env) if conn_env.exists() else {}
    updated = False
    for key, value in {
        "MAIOS_CLOUD_URL": "http://127.0.0.1:8000",
        "MAIOS_HEARTBEAT_SECONDS": "30",
    }.items():
        if not existing.get(key):
            existing[key] = value
            updated = True
    if not existing.get("MAIOS_DEVICE_KEY"):
        existing["MAIOS_DEVICE_KEY"] = secrets.token_urlsafe(32)
        updated = True
        log.info("Generated missing MAIOS_DEVICE_KEY in connector.env")
    if updated or not conn_env.exists():
        _write_connector_env(existing)


def _write_connector_env(values: dict[str, str]) -> None:
    conn_path = config_dir() / "connector.env"
    conn_path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")


def _cloud_failure_hint(log_file: Path) -> str | None:
    if _cloud_proc and _cloud_proc.poll() is not None:
        return f"Cloud process exited (code {_cloud_proc.returncode}) — see {log_file.name}"
    if not log_file.exists():
        return "Cloud did not respond — no log output yet"
    try:
        tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
        if tail:
            return "Cloud did not respond — " + " | ".join(line.strip() for line in tail if line.strip())
    except Exception:
        pass
    return "Cloud did not respond in time — see cloud.log"


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _service_env() -> dict[str, str]:
    root = app_root()
    cfg = config_dir()
    _ensure_env_files()
    secrets_data = install_secrets.ensure_install_secrets()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env.update(_load_env_file(cfg / "cloud.env"))
    env.update(_load_env_file(cfg / "connector.env"))
    env["MAIOS_RUNTIME_TOKEN"] = str(secrets_data.get("runtimeToken") or "")
    env["MAIOS_INSTALLATION_ID"] = str(secrets_data.get("installationId") or "")
    env["MAIOS_DEVICE_IDENTITY"] = str(secrets_data.get("deviceIdentity") or "")
    env["MAIOS_ENCRYPTION_KEY_FOUNDATION"] = str(secrets_data.get("encryptionKeyFoundation") or "")
    env.setdefault("MAIOS_DB", str(cfg / "maios_cloud.db"))
    env.setdefault("MAIOS_AUDIT_LOG", str(logs_dir() / "audit.jsonl"))
    env.setdefault("MAIOS_STATIC_DIR", str(root / "web" / "dist"))
    return env
