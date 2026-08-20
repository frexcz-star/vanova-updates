"""Production Python runtime resolution — fail-closed outside development."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .paths import app_root, venv_dir

# Structured error codes for UI / logs (no secrets).
PYTHON_RUNTIME_MISSING = "PYTHON_RUNTIME_MISSING"
PYTHON_RUNTIME_INVALID = "PYTHON_RUNTIME_INVALID"
DEPENDENCIES_MISSING = "DEPENDENCIES_MISSING"
DEPENDENCY_INSTALL_FAILED = "DEPENDENCY_INSTALL_FAILED"


class PythonRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def is_production() -> bool:
    if os.getenv("MAIOS_DEV", "").lower() in ("1", "true", "yes"):
        return False
    if os.getenv("MAIOS_PACKAGED", "").lower() in ("1", "true", "yes"):
        return True
    if os.getenv("MAIOS_APP_EXE"):
        return True
    # Electron sets MAIOS_APP_ROOT when packaged
    root = app_root()
    resources = os.getenv("MAIOS_RESOURCES", "")
    if resources and Path(resources).resolve() == root.resolve():
        return True
    # Packaged layout: resources/maios without dev repo cloud sibling
    if (root / "cloud").exists() and not (root.parent.parent / "desktop" / "main.js").exists():
        if os.getenv("MAIOS_APP_EXE") or "resources" in str(root).lower():
            return True
    return False


def _bundled_candidates() -> list[Path]:
    root = app_root()
    return [
        root / "python" / "python.exe",
        root / "python-bundle" / "python.exe",
        root / "python-bundle" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
    ]


def _user_venv_python() -> Path:
    return venv_dir() / "Scripts" / "python.exe"


def resolve_python(*, required: bool = True) -> Path | None:
    """Return Python executable. In production, never fall back to bare ``python`` on PATH."""
    for candidate in _bundled_candidates():
        if candidate.exists():
            return candidate
    user_py = _user_venv_python()
    if user_py.exists():
        return user_py
    if not is_production():
        return Path(sys.executable)
    if required:
        raise PythonRuntimeError(
            PYTHON_RUNTIME_MISSING,
            "Python runtime unavailable — bundled interpreter not found in installation",
            details={"searched": [str(p) for p in _bundled_candidates()]},
        )
    return None


def verify_python(python: Path) -> None:
    import subprocess

    try:
        out = subprocess.run(
            [str(python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        version = out.stdout.strip()
        major, minor = version.split(".")[:2]
        if int(major) < 3 or (int(major) == 3 and int(minor) < 11):
            raise PythonRuntimeError(
                PYTHON_RUNTIME_INVALID,
                f"Python {version} is too old — VANOVA requires 3.11+",
            )
    except PythonRuntimeError:
        raise
    except Exception as exc:
        raise PythonRuntimeError(
            PYTHON_RUNTIME_INVALID,
            f"Python runtime invalid: {exc}",
        ) from exc


def check_dependency(python: Path, module: str) -> bool:
    import subprocess

    try:
        subprocess.run(
            [str(python), "-c", f"import {module}"],
            capture_output=True,
            timeout=20,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return True
    except Exception:
        return False


def required_modules() -> list[str]:
    return ["fastapi", "uvicorn", "httpx", "bcrypt", "jose"]


def verify_dependencies(python: Path) -> list[str]:
    modules = required_modules()
    probe = ";".join(f"import {m}" for m in modules)
    try:
        subprocess.run(
            [str(python), "-c", probe],
            capture_output=True,
            timeout=30,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return []
    except Exception:
        return [m for m in modules if not check_dependency(python, m)]
