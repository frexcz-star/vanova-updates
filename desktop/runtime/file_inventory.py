"""Local file inventory — persisted in config_store.scanFiles (no heavy deps)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from . import config_store, file_relevance
from .runtime_security import sanitize_import_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_imported_files() -> dict[str, Any]:
    data = config_store.load()
    files = data.get("scanFiles") or []
    if not isinstance(files, list):
        files = []
    files = [f for f in files if isinstance(f, dict) and not file_relevance.legacy_app_artifact(f)]
    exclusions = data.get("scanExclusions") or []
    if not isinstance(exclusions, list):
        exclusions = []
    return {"files": files, "count": len(files), "excludedCount": len(exclusions)}


def add_imported_file(entry: dict[str, Any]) -> dict[str, Any]:
    name = (entry.get("name") or "archivo").strip()
    ext = (entry.get("ext") or (name.rsplit(".", 1)[-1] if "." in name else "xlsx")).lower().lstrip(".")
    raw_path = (entry.get("path") or name).strip()
    path, path_err = sanitize_import_path(raw_path)
    if path_err:
        return {"ok": False, "error": path_err}
    legacy_reason = file_relevance.legacy_app_artifact({"name": name, "path": path, "source": "import"})
    if legacy_reason:
        return {"ok": False, "error": f"No se puede importar {name}: {legacy_reason}. Selecciona el archivo original de la empresa."}
    record = {
        "name": name,
        "ext": ext,
        "size": int(entry.get("size") or 0),
        "path": path,
        "modified": entry.get("modified") or _now(),
        "source": "import",
    }
    preview = entry.get("contentPreview")
    if isinstance(preview, str) and preview.strip():
        record["contentPreview"] = preview[:65536]
    # BUG-017 FIX: RMW atómico bajo un solo lock. Antes hacía load() → añadir →
    # save() sin serializar; con ThreadingHTTPServer dos imports concurrentes
    # podían hacer lost-update (el archivo añadido primero se perdía).
    files: list[dict[str, Any]] = []

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal files
        files = [f for f in (cfg.get("scanFiles") or []) if f.get("path") != path]
        files.append(record)
        cfg["scanFiles"] = files
        return cfg

    config_store.update(_mutate)
    _organize_after_import(files)
    return {"ok": True, "count": len(files), "file": record}


def _organize_after_import(files: list[dict[str, Any]]) -> None:
    try:
        from . import file_organizer

        file_organizer.organize_files(files)
    except Exception:
        pass


def remove_imported_file(path: str) -> dict[str, Any]:
    safe_path, path_err = sanitize_import_path(path)
    if path_err:
        return {"ok": False, "error": path_err}
    path = safe_path or ""
    # BUG-017 FIX: RMW atómico bajo un solo lock (mismo patrón que add_imported_file).
    files: list[dict[str, Any]] = []
    exclusions: list[str] = []

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal files, exclusions
        files = [f for f in (cfg.get("scanFiles") or []) if f.get("path") != path]
        cfg["scanFiles"] = files
        # BUG-028 FIX: registrar la exclusión para que un scan futuro NO
        # reintroduzca el archivo eliminado (el archivo sigue en disco; sin
        # exclusiones el siguiente scan lo volvería a añadir).
        exclusions = list(cfg.get("scanExclusions") or [])
        if not isinstance(exclusions, list):
            exclusions = []
        if path not in exclusions:
            exclusions.append(path)
        cfg["scanExclusions"] = exclusions
        return cfg

    config_store.update(_mutate)
    _organize_after_import(files)
    return {"ok": True, "count": len(files), "excludedCount": len(exclusions)}


def list_candidates() -> dict[str, Any]:
    """Files the scanner found but is not sure about — pending human approval."""
    items = config_store.load().get("fileCandidates") or []
    if not isinstance(items, list):
        items = []
    pending = [i for i in items if isinstance(i, dict) and i.get("status") == "pending"]
    return {"files": pending, "count": len(pending)}


def decide_candidate(path: str, approve: bool) -> dict[str, Any]:
    """Human decision on a scanned candidate file (approve -> import, reject -> drop)."""
    safe_path, path_err = sanitize_import_path(path)
    if path_err:
        return {"ok": False, "error": path_err}
    path = safe_path or ""
    data = config_store.load()
    candidates = data.get("fileCandidates") or []
    if not isinstance(candidates, list):
        candidates = []
    record = next((c for c in candidates if isinstance(c, dict) and c.get("path") == path), None)
    if not record:
        return {"ok": False, "error": "Candidato no encontrado"}
    legacy_reason = file_relevance.legacy_app_artifact(record)
    if legacy_reason:
        return {"ok": False, "error": f"Archivo excluido: {legacy_reason}."}
    decision = "approved" if approve else "rejected"
    # BUG-017 FIX: RMW atómico bajo un solo lock sobre fileCandidates.
    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        updated: list[dict[str, Any]] = []
        for c in (cfg.get("fileCandidates") or []):
            if isinstance(c, dict) and c.get("path") == path:
                c["status"] = decision
                c["decision"] = decision
                c["decidedAt"] = _now()
            updated.append(c)
        cfg["fileCandidates"] = updated
        return cfg

    config_store.update(_mutate)
    if approve:
        files: list[dict[str, Any]] = []

        def _mutate_scan(cfg: dict[str, Any]) -> dict[str, Any]:
            nonlocal files
            files = [f for f in (cfg.get("scanFiles") or []) if isinstance(f, dict) and f.get("path") != path]
            approved = dict(record)
            approved["status"] = "approved"
            approved["source"] = "approved"
            approved["category"] = None
            files.append(approved)
            cfg["scanFiles"] = files
            return cfg

        config_store.update(_mutate_scan)
        threading.Thread(
            target=_organize_after_import,
            args=(files,),
            daemon=True,
        ).start()
    return {"ok": True, "approved": approve, "path": path}
