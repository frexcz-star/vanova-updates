"""VANOVA PRODUCT 8 — Memoria de recomendaciones (ciclo observar→recomendar→medir).

Registra cada prioridad/hallazgo que VANOVA surfacea al usuario, permite
marcar la acción como «hecho», y al re-analizar compara la métrica de la
entidad afectada antes/después para decir si la recomendación funcionó.

Reglas de honestidad:
* Nunca afirma que una recomendación «funcionó» sin datos comparables: si no
  hay métrica anterior o el cambio no es medible, estado = PENDIENTE DE MEDICIÓN.
* La métrica se re-lee del modelo canónico en cada chequeo (no se inventa).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from . import config_store
from .logger import get_logger

log = get_logger("maios.recommendations", "recommendation-store")

REC_KEY = "recommendations"
MAX_RECS = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    src = data if data is not None else config_store.load()
    items = src.get(REC_KEY) or []
    return [r for r in items if isinstance(r, dict)]


def _metric_for(finding: dict[str, Any], data: dict[str, Any]) -> dict[str, Any] | None:
    """Métrica canónica de la entidad afectada por el finding, si es medible.
    Devuelve None si no hay forma de medirla (UNKNOWN ≠ 0, no se inventa)."""
    ftype = str(finding.get("type") or finding.get("finding_type") or "")
    entity = str(finding.get("entity") or "")
    sku = str((finding.get("metrics") or {}).get("sku") or "") or entity
    if not sku:
        return None
    try:
        from . import business_model

        sales = data.get("organizedSales") or []
        rev = 0.0
        orders = 0
        for s in sales:
            for li in business_model.normalize_sale_lines(s):
                if str(li.get("sku") or "").strip().lower() == sku.lower():
                    rev += (business_model._as_float(li.get("price")) or 0.0) * (business_model._as_float(li.get("quantity")) or 1.0)
                    orders += 1
        if orders == 0:
            return None
        return {"sku": sku, "revenue": round(rev, 2), "orders": orders}
    except Exception:  # noqa: BLE001
        return None


def record_finding(finding: dict[str, Any], *, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Registra una recomendación desde un finding con prioridad (score > umbral).
    ID estable por firma del finding: re-analizar el mismo finding NO crea otra
    recomendación; solo actualiza la métrica actual."""
    ftype = str(finding.get("type") or finding.get("finding_type") or "")
    if not ftype:
        return None
    sig = str(finding.get("signature") or "")
    if not sig:
        return None
    items = _load(data)
    metric = _metric_for(finding, data or config_store.load())
    existing = next((r for r in items if str(r.get("signature") or "") == sig), None)
    if existing:
        existing["lastSeenAt"] = _now()
        existing["title"] = str(finding.get("title") or existing.get("title") or "")
        if metric:
            existing["metricNow"] = metric
        return existing
    rec = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "vanova:rec:" + sig)),
        "signature": sig,
        "findingType": ftype,
        "findingId": finding.get("id"),
        "title": str(finding.get("title") or ""),
        "recommendedAction": str(finding.get("recommendedAction") or ""),
        "status": "open",  # open → done → measured
        "createdAt": _now(),
        "lastSeenAt": _now(),
        "metricBefore": metric,
        "metricNow": metric,
        "outcome": None,  # None | "improved" | "no_change" | "worsened" | "unmeasurable"
    }
    items.insert(0, rec)
    _save(items, data=data)
    return rec


def _save(items: list[dict[str, Any]], *, data: dict[str, Any] | None = None) -> None:
    if data is not None:
        data[REC_KEY] = items[:MAX_RECS]
        return
    config_store.save({REC_KEY: items[:MAX_RECS]})


def mark_done(rec_id: str, *, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return set_status(rec_id, "done", data=data)


# Estados de ciclo de vida visibles al usuario (producto, no técnico).
VALID_STATUSES = {
    "open": "Nueva",
    "in_progress": "En curso",
    "done": "Realizada",
    "not_done": "No realizada",
    "resolved": "Resuelta",
}


def set_status(rec_id: str, status: str, *, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Cambia el estado de una recomendación. Al marcar como realizada/resuelta
    se re-mide automáticamente el resultado (siempre que haya métrica)."""
    if status not in VALID_STATUSES:
        return None
    items = _load(data)
    for r in items:
        if r.get("id") == rec_id:
            r["status"] = status
            if status == "done":
                r["doneAt"] = _now()
            if status == "resolved":
                r["resolvedAt"] = _now()
            if status in ("not_done", "dismissed"):
                r["dismissedAt"] = _now()
            _save(items, data=data)
            if status == "done":
                try:
                    measure(rec_id, data=data)
                except Exception:  # noqa: BLE001 — medir nunca rompe el estado
                    pass
                # Devolver el estado REAL tras la auto-medición (measure() puede
                # cambiar status a 'measured' y fijar outcome), no el dict
                # anterior a medir.
                after = next(
                    (x for x in _load(data) if x.get("id") == rec_id),
                    None,
                )
                if after is not None:
                    return after
            return r
    return None


def measure(rec_id: str, *, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Re-mide la métrica de la entidad tras la acción y clasifica el resultado
    de forma honesta. Sin métrica anterior comparable → unmeasurable."""
    items = _load(data)
    cfg = data if data is not None else config_store.load()
    for r in items:
        if r.get("id") != rec_id:
            continue
        finding = next(
            (f for f in (cfg.get("businessFindings") or []) if str(f.get("signature") or "") == str(r.get("signature") or "")),
            None,
        )
        metric = _metric_for(finding or {"type": r.get("findingType"), "metrics": {}, "entity": ""}, cfg)
        before = r.get("metricBefore") or {}
        if not metric or not before or not before.get("revenue") or not metric.get("revenue"):
            r["outcome"] = "unmeasurable"
            r["measuredAt"] = _now()
            _save(items, data=data)
            return r
        b_rev = float(before.get("revenue") or 0.0)
        n_rev = float(metric.get("revenue") or 0.0)
        if n_rev <= 0 and b_rev <= 0:
            r["outcome"] = "unmeasurable"
        elif b_rev > 0 and n_rev > b_rev * 1.05:
            r["outcome"] = "improved"
        elif b_rev > 0 and n_rev < b_rev * 0.95:
            r["outcome"] = "worsened"
        else:
            r["outcome"] = "no_change"
        r["status"] = "measured"
        r["metricNow"] = metric
        r["measuredAt"] = _now()
        _save(items, data=data)
        return r
    return None


def list_recommendations(*, data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _load(data)


def sync_resolutions(
    findings: list[dict[str, Any]] | None,
    *,
    active_signatures: set[str] | list[str] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lifecycle honesto: si el finding que originó una recomendación ya NO está
    activo (el problema desapareció de los datos), la recomendación pasa a
    'resolved' sin atribuir causalidad: solo dice que la condición ya no existe.
    Nunca inventa un resultado: el outcome queda sin forzar.

    ``active_signatures`` (opcional): firmas DETECTADAS EN LA ÚLTIMA EJECUCIÓN
    (result.freshSignatures del motor). Si no se pasa, se derivan de los
    findings — pero ojo: run_detection conserva findings históricos con
    lastSeenAt viejo, así que siempre que se pueda hay que pasar las frescas."""
    if active_signatures is not None:
        active_sigs = {str(s) for s in active_signatures}
    else:
        active_sigs = {str(f.get("signature") or "") for f in (findings or []) if isinstance(f, dict) and f.get("signature")}
    items = _load(data)
    changed = 0
    for r in items:
        sig = str(r.get("signature") or "")
        # SOLO las recomendaciones que el usuario aún no ha tocado (open) se
        # auto-resuelven cuando la condición desaparece. Un estado elegido
        # por el usuario (in_progress / done / not_done / resolved / measured)
        # NUNCA se pisa en un re-análisis automático: si el usuario marcó
        # «En curso» o «Realizada», eso es una decisión suya que el motor no
        # puede revertir en silencio (regresión 3.0.3: sync_resolutions
        # convertía «En curso»/«Realizada» en «Resuelta» tras cada análisis).
        if sig and sig not in active_sigs and str(r.get("status") or "") == "open":
            r["status"] = "resolved"
            r["resolvedAt"] = _now()
            r["resolvedReason"] = "la condición detectada ya no está presente en los datos"
            changed += 1
    if changed:
        _save(items, data=data)
    return {"resolved": changed, "total": len(items)}


def measure_all(*, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """PRODUCT LEAP — re-mide las recomendaciones realizadas/resueltas con los
datos canonicos actuales (ciclo recomendar -> actuar -> medir automatico).
UNKNOWN != 0: sin metrica comparable la medicion queda como 'unmeasurable'.
"""
    items = _load(data)
    measured = 0
    for r in items:
        # Solo las marcadas 'done' se re-miden: 'resolved' ya cerró el ciclo
        # (la condición desapareció) y no debe volver a 'measured'.
        if str(r.get("status") or "") in ("done", "measured"):
            # done: primera medición · measured: re-medición para ver evolución.
            # resolved: ciclo cerrado, nunca se re-mide.
            try:
                if measure(r.get("id"), data=data):
                    measured += 1
            except Exception:  # noqa: BLE001 — medir nunca debe romper el ciclo
                pass
    return {"measured": measured, "total": len(items)}
