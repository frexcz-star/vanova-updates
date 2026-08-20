"""Honest operational state labels — never fake success (Phase 15)."""
from __future__ import annotations

from typing import Any

VALID_MODES = frozenset({"real", "partial", "mock", "empty"})

MODE_META: dict[str, dict[str, str]] = {
    "real": {
        "label": "Conectado",
        "description": "Datos reales sincronizados desde fuentes conectadas",
        "badge": "success",
    },
    "partial": {
        "label": "Parcial",
        "description": "Datos locales escaneados; algunas fuentes aún no conectadas",
        "badge": "warning",
    },
    "mock": {
        "label": "Demo",
        "description": "Datos de demostración — no representan tu negocio",
        "badge": "neutral",
    },
    "empty": {
        "label": "Sin datos",
        "description": "Conecta fuentes o importa archivos para ver datos reales",
        "badge": "neutral",
    },
}


def normalize_mode(mode: str | None, *, has_local_files: bool = False) -> str:
    value = (mode or "empty").strip().lower()
    if value not in VALID_MODES:
        value = "empty"
    if value == "empty" and has_local_files:
        return "partial"
    return value


def describe_mode(mode: str | None) -> dict[str, Any]:
    normalized = normalize_mode(mode)
    meta = MODE_META[normalized]
    return {
        "dataMode": normalized,
        "label": meta["label"],
        "description": meta["description"],
        "badge": meta["badge"],
        "honest": normalized in ("real", "partial", "empty"),
        "isDemo": normalized == "mock",
    }


def task_status_label(status: str) -> dict[str, str]:
    mapping = {
        "queued": {"label": "En cola", "badge": "neutral"},
        "running": {"label": "Ejecutando", "badge": "info"},
        "completed": {"label": "Completada", "badge": "success"},
        "failed": {"label": "Fallida", "badge": "danger"},
        "needs_approval": {"label": "Necesita aprobación", "badge": "warning"},
        "blocked": {"label": "Bloqueada", "badge": "danger"},
    }
    return mapping.get(status, {"label": status, "badge": "neutral"})
