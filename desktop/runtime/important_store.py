"""Important Store — information the owner marks as relevant for the agents.

When the owner flags a finished task or insight as "importante", it is
persisted here so that any agent can later consume it as curated context
(e.g. strategic facts, decisions, lessons learned). It is a single source
of truth for curated business knowledge inside VANOVA.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from . import config_store
from .logger import get_logger

log = get_logger("maios.important", "important-store")

IMPORTANT_KEY = "importantItems"
MAX_IMPORTANT = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict[str, Any]]:
    data = config_store.load().get(IMPORTANT_KEY) or []
    if not isinstance(data, list):
        return []
    return [i for i in data if isinstance(i, dict)]


def _save(items: list[dict[str, Any]]) -> None:
    config_store.save({IMPORTANT_KEY: items[:MAX_IMPORTANT]})


def mark_important(
    kind: str,
    ref_id: str,
    *,
    title: str,
    body: str = "",
    agent_id: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark an item (task or insight) as important/curated knowledge."""
    kind = str(kind or "item").strip().lower()
    ref_id = str(ref_id or "").strip()
    if not ref_id:
        return {"ok": False, "error": "Falta el identificador del elemento"}

    items = _load()
    # Avoid duplicates: same kind + ref_id gets refreshed instead.
    for existing in items:
        if str(existing.get("kind") or "").lower() == kind and str(existing.get("refId") or "") == ref_id:
            existing["title"] = title or existing.get("title") or ""
            existing["body"] = body or existing.get("body") or ""
            existing["updatedAt"] = _now()
            if meta:
                existing["meta"] = {**(existing.get("meta") or {}), **meta}
            _save(items)
            return {"ok": True, "item": existing, "updated": True}

    item = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "refId": ref_id,
        "title": (title or "Elemento importante").strip(),
        "body": (body or "").strip(),
        "agentId": agent_id or "",
        "createdAt": _now(),
        "updatedAt": _now(),
    }
    if meta:
        item["meta"] = meta
    items.insert(0, item)
    _save(items)
    log.info("Important marked (%s): %s", kind, item["title"][:60])
    return {"ok": True, "item": item, "updated": False}


def unmark(kind: str, ref_id: str) -> dict[str, Any]:
    kind = str(kind or "").strip().lower()
    ref_id = str(ref_id or "").strip()
    items = _load()
    kept = [i for i in items if not (str(i.get("kind") or "").lower() == kind and str(i.get("refId") or "") == ref_id)]
    if len(kept) == len(items):
        return {"ok": False, "error": "El elemento no estaba marcado como importante"}
    _save(kept)
    return {"ok": True}


def is_important(kind: str, ref_id: str) -> bool:
    kind = str(kind or "").strip().lower()
    ref_id = str(ref_id or "").strip()
    return any(
        str(i.get("kind") or "").lower() == kind and str(i.get("refId") or "") == ref_id
        for i in _load()
    )


def list_important(limit: int = 200) -> list[dict[str, Any]]:
    items = _load()
    items.sort(key=lambda i: str(i.get("updatedAt") or i.get("createdAt") or ""), reverse=True)
    return items[:limit]
