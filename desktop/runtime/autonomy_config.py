"""Autonomy level configuration (Phase 24)."""
from __future__ import annotations

from typing import Any

from . import config_store

VALID_LEVELS = frozenset({"manual", "approval_required", "supervised", "autonomous"})

LEVEL_META: dict[str, dict[str, str]] = {
    "manual": {
        "label": "Manual",
        "description": "Ninguna acción se ejecuta sin tu confirmación explícita.",
    },
    "approval_required": {
        "label": "Aprobación requerida",
        "description": "Las acciones sensibles requieren aprobación humana.",
    },
    "supervised": {
        "label": "Supervisado",
        "description": "Acciones de bajo riesgo automáticas; el resto requiere revisión.",
    },
    "autonomous": {
        "label": "Autónomo",
        "description": "Ejecución automática con políticas y guardrails activos.",
    },
}


def get_level() -> str:
    level = str(config_store.load().get("autonomyLevel") or "approval_required").strip().lower()
    return level if level in VALID_LEVELS else "approval_required"


def set_level(level: str) -> dict[str, Any]:
    normalized = (level or "").strip().lower()
    if normalized not in VALID_LEVELS:
        return {"ok": False, "error": "Nivel de autonomía no válido"}
    config_store.save({"autonomyLevel": normalized})
    return {"ok": True, "level": normalized, **describe(normalized)}


def describe(level: str | None = None) -> dict[str, Any]:
    key = (level or get_level()).strip().lower()
    meta = LEVEL_META.get(key, LEVEL_META["approval_required"])
    return {"level": key, "label": meta["label"], "description": meta["description"]}


def list_levels() -> list[dict[str, Any]]:
    current = get_level()
    out = []
    for key in ("manual", "approval_required", "supervised", "autonomous"):
        row = describe(key)
        row["active"] = key == current
        out.append(row)
    return out
