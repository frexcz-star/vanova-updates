"""Portable path resolution for VANOVA Desktop (no hardcoded developer paths)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Installed app root (Electron resources or dev repo root)."""
    env = os.getenv("MAIOS_APP_ROOT")
    if env:
        return Path(env).resolve()
    # Dev: desktop/runtime -> repo root
    here = Path(__file__).resolve().parent
    if (here.parent.parent / "cloud").exists():
        return here.parent.parent
    # Packaged: resources/maios
    resources = os.getenv("MAIOS_RESOURCES")
    if resources:
        return Path(resources).resolve()
    return here.parent.parent


def _migrate_legacy_data_dir(path: Path) -> None:
    """One-time rebrand migration: %LOCALAPPDATA%/MAIOS -> %LOCALAPPDATA%/VANOVA.
    Copies user data (config/maios.json, tasks.db, approvals.db, logs, backups)
    so the rebrand never loses a record. Idempotent + skips heavy transient dirs."""
    import shutil

    try:
        legacy = path.parent / "VANOVA"
        if not legacy.is_dir():
            return
        if (path / "config" / "maios.json").exists():
            return  # already migrated
        if not (legacy / "config" / "maios.json").exists():
            return  # nothing to migrate
        path.mkdir(parents=True, exist_ok=True)
        ignore = shutil.ignore_patterns("venv", "updates", "temp", ".tmp", "__pycache__")
        for item in legacy.iterdir():
            if item.name in ("venv", "updates", "temp", ".tmp"):
                continue
            try:
                if item.is_dir():
                    if not (path / item.name).exists():
                        shutil.copytree(item, path / item.name, ignore=ignore, dirs_exist_ok=True)
                elif not (path / item.name).exists():
                    shutil.copy2(item, path / item.name)
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        pass


def data_dir() -> Path:
    """User data directory (%LOCALAPPDATA%/VANOVA on Windows)."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    path = Path(base) / "VANOVA"
    _migrate_legacy_data_dir(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = data_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def venv_dir() -> Path:
    """User-writable Python environment (not inside Program Files)."""
    path = data_dir() / "venv"
    path.mkdir(parents=True, exist_ok=True)
    return path


def python_executable() -> Path:
    """Python used for Cloud/Connector subprocesses."""
    from . import python_runtime

    return python_runtime.resolve_python(required=True)  # type: ignore[return-value]


def version_file() -> Path:
    return app_root() / "version.json"
