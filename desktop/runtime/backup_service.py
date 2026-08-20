"""SQLite-WAL-safe backups for all local VANOVA user data."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logger import get_logger
from .paths import config_dir, data_dir

log = get_logger("maios.backup", "backup")

BACKUP_ROOT = data_dir() / "backups"
MAX_BACKUPS = 7
_SAFE_BACKUP_ID = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _checkpoint_sqlite(path: Path) -> None:
    if not path.exists():
        return
    conn = None
    try:
        conn = sqlite3.connect(path, timeout=15)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("WAL checkpoint failed for %s: %s", path.name, exc)
    finally:
        # Cerrar SIEMPRE la conexión: si no, el handle queda abierto y en
        # Windows impide borrar el archivo (bloquea el factory reset).
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _data_summary() -> dict[str, int]:
    try:
        from . import config_store

        payload = json.loads(config_store.CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        key: len(payload.get(key) or []) if isinstance(payload.get(key), list) else 0
        for key in ("organizedProducts", "organizedSales", "organizedCustomers", "scanFiles", "insights")
    }


def run_backup(*, reason: str = "manual") -> dict[str, Any]:
    """Create a timestamped backup of config, stores, databases, and sidecars."""
    from . import config_store

    stamp = _stamp()
    dest = BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=False)

    copied: list[str] = []
    data_root = data_dir()
    config_root = config_dir()
    for label, source in (("config", config_root),):
        if source.exists():
            shutil.copytree(source, dest / label, dirs_exist_ok=True)
            copied.append(label)

    # Flush all known SQLite databases before copying them, then retain any
    # remaining WAL/SHM sidecars as an additional safety net.
    for source in sorted(
        p for p in data_root.iterdir() if p.is_file() and p.suffix.lower() in {".json", ".db"}
    ):
        if source.suffix.lower() == ".db":
            _checkpoint_sqlite(source)
        if _copy_if_exists(source, dest / "data" / source.name):
            copied.append(f"data/{source.name}")
        if source.suffix.lower() == ".db":
            for suffix in ("-wal", "-shm"):
                sidecar = source.with_name(source.name + suffix)
                if _copy_if_exists(sidecar, dest / "data" / sidecar.name):
                    copied.append(f"data/{sidecar.name}")

    meta = {
        "createdAt": _now(),
        "reason": reason,
        "files": copied,
        "dataSummary": _data_summary(),
        "backupFormat": 2,
        "path": str(dest),
    }
    (dest / "backup.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _prune_old_backups()
    log.info("Backup created at %s (%d files, summary=%s)", dest, len(copied), meta["dataSummary"])
    return {"ok": True, **meta}


def _read_meta(folder: Path) -> dict[str, Any]:
    for name in ("backup.json", "backup-manifest.json"):
        path = folder / name
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def status() -> dict[str, Any]:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for folder in sorted(BACKUP_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        meta = _read_meta(folder)
        entries.append(
            {
                "id": folder.name,
                "path": str(folder),
                "createdAt": meta.get("createdAt"),
                "files": meta.get("files") or [],
                "dataSummary": meta.get("dataSummary") or {},
            }
        )
        if len(entries) >= MAX_BACKUPS:
            break

    # The updater's pre-update snapshots are separate from daily backups. They
    # must be visible so a failed release can be recovered without file hunting.
    try:
        from .update import backup as update_backup

        pre_update = update_backup.list_backups()
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not list pre-update backups: %s", exc)
        pre_update = []

    return {
        "backupDir": str(BACKUP_ROOT),
        "maxBackups": MAX_BACKUPS,
        "count": len(entries),
        "latest": entries[0] if entries else None,
        "backups": entries,
        "preUpdateBackups": pre_update,
    }


def restore_pre_update(backup_id: str) -> dict[str, Any]:
    """Restore one updater snapshot by ID; reject arbitrary filesystem paths."""
    backup_id = str(backup_id or "").strip()
    if not _SAFE_BACKUP_ID.fullmatch(backup_id):
        return {"ok": False, "error": "Identificador de backup no válido"}
    from .update import backup as update_backup

    root = update_backup.backup_root().resolve()
    candidate = (root / backup_id).resolve()
    if candidate.parent != root or not candidate.is_dir():
        return {"ok": False, "error": "Backup no encontrado"}
    if not (candidate / "backup-manifest.json").exists():
        return {"ok": False, "error": "La copia no tiene un manifiesto válido"}
    ok = update_backup.restore_backup(candidate)
    return {
        "ok": ok,
        "id": backup_id,
        "message": "Copia restaurada. Reinicia VANOVA para recargar todos los datos." if ok else "No se pudo restaurar la copia.",
    }


def database_health() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, path in (
        ("tasks_db", data_dir() / "tasks.db"),
        ("approvals_db", data_dir() / "approvals.db"),
    ):
        if not path.exists():
            checks.append({"id": label, "status": "warning", "message": "Base de datos aún no creada"})
            continue
        try:
            conn = sqlite3.connect(path, timeout=5)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            conn.close()
            checks.append({"id": label, "status": "ok", "message": f"WAL mode: {mode}", "path": str(path)})
        except Exception as exc:
            checks.append({"id": label, "status": "critical", "message": str(exc), "path": str(path)})
    config_path = config_dir() / "maios.json"
    if config_path.exists():
        checks.append({"id": "config", "status": "ok", "message": "maios.json presente", "path": str(config_path)})
    else:
        checks.append({"id": "config", "status": "warning", "message": "Config por defecto"})
    return checks


def _prune_old_backups() -> None:
    if not BACKUP_ROOT.exists():
        return
    folders = sorted(
        [p for p in BACKUP_ROOT.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in folders[MAX_BACKUPS:]:
        try:
            shutil.rmtree(old)
            log.info("Pruned old backup %s", old.name)
        except OSError as exc:
            log.warning("Could not prune backup %s: %s", old.name, exc)


def maybe_startup_backup() -> None:
    """One complete backup per day on runtime start."""
    st = status()
    latest = st.get("latest") or {}
    created = str(latest.get("createdAt") or "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if created.startswith(today):
        return
    try:
        run_backup(reason="startup")
    except Exception as exc:
        log.warning("Startup backup skipped: %s", exc)
