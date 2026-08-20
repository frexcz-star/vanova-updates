"""Post-install health gate — validates core components before declaring success."""
from __future__ import annotations

import os
from typing import Any

from . import config_store, port_utils, process_manager
from .health_monitor import check_all
from .paths import app_root
from .python_runtime import (
    DEPENDENCIES_MISSING,
    DEPENDENCY_INSTALL_FAILED,
    PYTHON_RUNTIME_MISSING,
    PythonRuntimeError,
    resolve_python,
    verify_dependencies,
    verify_python,
)
from .startup_log import emit


def validate_startup(*, install_deps: bool = False) -> dict[str, Any]:
    """Return structured startup status. ``status``: success | partial | failed."""
    checks: list[dict[str, Any]] = []
    critical_failed = False

    emit("STARTING_RUNTIME", status="running")

    try:
        py = resolve_python(required=True)
        verify_python(py)
        emit("PYTHON_RESOLVED", python=str(py))
        version = _python_version(py)
        emit("PYTHON_VERSION", version=version)

        missing = verify_dependencies(py)
        if missing and install_deps:
            try:
                process_manager._ensure_venv()
                py = resolve_python(required=True)
                missing = verify_dependencies(py)
            except Exception as exc:
                emit("DEPENDENCY_INSTALL_FAILED", status="failed", error=str(exc))
                checks.append(
                    {
                        "id": "dependencies",
                        "status": "critical",
                        "error_code": DEPENDENCY_INSTALL_FAILED,
                        "message": str(exc),
                    }
                )
                critical_failed = True
        if missing:
            checks.append(
                {
                    "id": "dependencies",
                    "status": "critical",
                    "error_code": DEPENDENCIES_MISSING,
                    "message": "Missing modules: " + ", ".join(missing),
                }
            )
            critical_failed = True
        else:
            emit("DEPENDENCY_CHECK", status="ok")
            checks.append({"id": "dependencies", "status": "ok"})
    except PythonRuntimeError as exc:
        emit("PYTHON_RESOLVED", status="failed", error_code=exc.code)
        checks.append(
            {
                "id": "python",
                "status": "critical",
                "error_code": exc.code,
                "message": str(exc),
            }
        )
        critical_failed = True
        py = None

    static = app_root() / "web" / "dist" / "index.html"
    if not static.exists():
        static = app_root() / "web" / "index.html"
    if static.exists():
        checks.append({"id": "static_assets", "status": "ok"})
    else:
        checks.append(
            {
                "id": "static_assets",
                "status": "critical",
                "error_code": "STATIC_ASSETS_MISSING",
                "message": "Dashboard static files missing",
            }
        )
        critical_failed = True

    ports = port_utils.check_ports()
    runtime_ok = ports.get("runtime", {}).get("status") == "ok"
    checks.append(
        {
            "id": "runtime_port",
            "status": "ok" if runtime_ok else "critical",
            "message": ports.get("runtime", {}).get("message", ""),
        }
    )
    if not runtime_ok:
        critical_failed = True

    emit("STARTING_CLOUD", status="running")
    svc = process_manager.start_all()
    cloud_ok = bool(svc.get("cloud"))
    emit(
        "CLOUD_HEALTH_CHECK",
        status="ok" if cloud_ok else "failed",
        cloud=cloud_ok,
        connector=bool(svc.get("connector")),
    )
    if cloud_ok:
        emit("CLOUD_READY", port=8000)
        checks.append({"id": "cloud", "status": "ok"})
    else:
        hint = (svc.get("warnings") or ["Cloud failed to start"])[0]
        checks.append(
            {
                "id": "cloud",
                "status": "critical",
                "error_code": "CLOUD_START_FAILED",
                "message": hint,
            }
        )
        critical_failed = True

    if svc.get("connector"):
        emit("CONNECTOR_READY", status="ok")
        checks.append({"id": "connector", "status": "ok"})
    else:
        checks.append(
            {
                "id": "connector",
                "status": "warning",
                "error_code": "CONNECTOR_START_FAILED",
                "message": "Connector optional — may register later",
            }
        )

    try:
        config_store.load()
        checks.append({"id": "database", "status": "ok"})
    except Exception as exc:
        checks.append(
            {
                "id": "database",
                "status": "critical",
                "error_code": "DATABASE_ERROR",
                "message": str(exc),
            }
        )
        critical_failed = True

    health = check_all()
    if critical_failed:
        status = "failed"
        emit("INSTALLATION_INCOMPLETE", status="failed")
    elif any(c.get("status") == "warning" for c in checks):
        status = "partial"
    else:
        status = "success"
        emit("STARTUP_COMPLETE", status="ok")

    return {
        "status": status,
        "ok": status == "success",
        "partial": status == "partial",
        "checks": checks,
        "health": health,
        "ports": ports,
    }


def _python_version(py) -> str:
    import subprocess

    out = subprocess.run(
        [str(py), "-c", "import platform; print(platform.python_version())"],
        capture_output=True,
        text=True,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return out.stdout.strip()
