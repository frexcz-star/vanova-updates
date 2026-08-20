"""Lossless pre-update backup and recovery for VANOVA user data.

The updater may replace the application, but it must never replace the user's
normalized catalog, Hermes context, approvals, insights, integrations, or
scheduler state. Backups are kept outside the installation directory so an
installer cannot remove them.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..logger import get_logger
from ..paths import config_dir, data_dir

log = get_logger("maios.update.backup", "updater")

# Keep enough history to recover from a bad release discovered days later.
MAX_BACKUPS = 10


def backup_root() -> Path:
    path = data_dir() / "backup"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_sqlite(path: Path) -> None:
    """Flush WAL content before copying a database, without failing an update."""
    if not path.exists():
        return
    try:
        conn = sqlite3.connect(path, timeout=15)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("WAL checkpoint failed for %s: %s", path.name, exc)


def _copy_file(src: Path, dest: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def _copy_direct_user_files(dest: Path, manifest: dict[str, Any]) -> None:
    """Copy top-level data files, including future JSON stores and DB sidecars."""
    root = data_dir()
    data_dest = dest / "data"
    copied = manifest.setdefault("files", [])

    # Include every top-level JSON/DB store rather than maintaining a fragile
    # list as new Hermes/agent stores are added. Runtime/update folders are
    # directories and are handled separately below.
    candidates = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in {".json", ".db"}
    )
    for src in candidates:
        if src.suffix.lower() == ".db":
            _checkpoint_sqlite(src)
        target = data_dest / src.name
        if _copy_file(src, target):
            copied.append(f"data/{src.name}")

        # A checkpoint normally removes these, but copy any remaining sidecars
        # so a recovery never loses uncheckpointed SQLite pages.
        if src.suffix.lower() == ".db":
            for suffix in ("-wal", "-shm"):
                sidecar = src.with_name(src.name + suffix)
                if _copy_file(sidecar, data_dest / sidecar.name):
                    copied.append(f"data/{sidecar.name}")


def _data_summary() -> dict[str, int]:
    try:
        payload = json.loads((config_dir() / "maios.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        key: len(payload.get(key) or []) if isinstance(payload.get(key), list) else 0
        for key in ("organizedProducts", "organizedSales", "organizedCustomers", "scanFiles", "insights")
    }


def create_backup(installed_version: str) -> Path:
    """Create a complete, timestamped snapshot before replacing the app."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")
    dest = backup_root() / f"{ts}-v{installed_version}"
    dest.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Any] = {
        "version": installed_version,
        "createdAt": _now(),
        "files": [],
        "dataSummary": _data_summary(),
        "backupFormat": 2,
    }

    config_source = config_dir()
    if config_source.exists():
        shutil.copytree(config_source, dest / "config", dirs_exist_ok=True)
        manifest["files"].append("config")

    updates_source = data_dir() / "updates"
    if updates_source.exists():
        shutil.copytree(updates_source, dest / "updates", dirs_exist_ok=True)
        manifest["files"].append("updates")

    _copy_direct_user_files(dest, manifest)

    (dest / "backup-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info(
        "Complete pre-update backup created at %s (summary=%s)",
        dest,
        manifest.get("dataSummary"),
    )
    _prune_old_backups()
    return dest


def _restore_config(src: Path) -> None:
    dest = config_dir()
    # Keep files created after the snapshot (for example a newly generated
    # install secret), unless the backup explicitly contains the same path.
    preserved: list[tuple[Path, bytes]] = []
    if dest.exists():
        for live in dest.rglob("*"):
            if live.is_file():
                rel = live.relative_to(dest)
                if not (src / rel).exists():
                    preserved.append((live, live.read_bytes()))
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest)
    for path, payload in preserved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        log.info("Preserved post-backup config file %s", path.name)


def restore_backup(backup_path: Path) -> bool:
    """Restore a pre-update snapshot without deleting unrelated live data."""
    if not backup_path.exists() or not backup_path.is_dir():
        return False
    try:
        config_source = backup_path / "config"
        if config_source.exists():
            _restore_config(config_source)

        updates_source = backup_path / "updates"
        updates_dest = data_dir() / "updates"
        if updates_source.exists():
            if updates_dest.exists():
                shutil.rmtree(updates_dest, ignore_errors=True)
            shutil.copytree(updates_source, updates_dest)

        data_source = backup_path / "data"
        if data_source.exists():
            data_dest = data_dir()
            for source in data_source.rglob("*"):
                if not source.is_file():
                    continue
                relative = source.relative_to(data_source)
                target = data_dest / relative
                _copy_file(source, target)

            # Do not let a live WAL/SHM from a newer database override the
            # restored main file when the snapshot was checkpointed cleanly.
            for db_name in ("tasks.db", "approvals.db"):
                if (data_source / db_name).exists():
                    for suffix in ("-wal", "-shm"):
                        live_sidecar = data_dest / f"{db_name}{suffix}"
                        if not (data_source / f"{db_name}{suffix}").exists():
                            live_sidecar.unlink(missing_ok=True)

        log.info("Restored pre-update backup from %s", backup_path)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Restore failed: %s", exc)
        return False


def list_backups() -> list[dict[str, Any]]:
    """Return safe metadata for recovery UI/API without exposing file contents."""
    entries: list[dict[str, Any]] = []
    if not backup_root().exists():
        return entries
    for folder in sorted(
        (p for p in backup_root().iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        manifest_path = folder / "backup-manifest.json"
        meta: dict[str, Any] = {}
        try:
            if manifest_path.exists():
                meta = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        summary = meta.get("dataSummary") or {}
        if not summary:
            # Backups created by pre-2.0.15 builds did not write a summary, but
            # their config snapshot is still perfectly recoverable.
            try:
                config_snapshot = folder / "config" / "maios.json"
                payload = json.loads(config_snapshot.read_text(encoding="utf-8-sig"))
                summary = {
                    key: len(payload.get(key) or []) if isinstance(payload.get(key), list) else 0
                    for key in ("organizedProducts", "organizedSales", "organizedCustomers", "scanFiles", "insights")
                }
            except (OSError, json.JSONDecodeError):
                summary = {}
        entries.append({
            "id": folder.name,
            "createdAt": meta.get("createdAt"),
            "version": meta.get("version"),
            "format": meta.get("backupFormat", 1),
            "dataSummary": summary,
            "files": meta.get("files") or [],
        })
        if len(entries) >= MAX_BACKUPS:
            break
    return entries


def _prune_old_backups() -> None:
    backups = sorted(
        (p for p in backup_root().iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[MAX_BACKUPS:]:
        shutil.rmtree(old, ignore_errors=True)
