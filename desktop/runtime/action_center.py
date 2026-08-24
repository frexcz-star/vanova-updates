"""VANOVA PRODUCT LEAP — Action Center (acciones PREPARADAS, nunca ejecutadas).

Convierte una recomendación en un entregable concreto SIN tocar sistemas
externos: prepara el CSV/plan que el dueño puede revisar, confirmar y usar
(cargar costes, segmento de reactivación). Todo es solo lectura + audit trail.

Reglas:
* NUNCA escribe fuera de VANOVA (no cambia precios, no envía emails).
* Toda acción queda registrada en el audit log (qué, cuándo, quién, cuántos).
* Determinista: mismos datos -> mismo entregable.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from . import config_store
from .logger import get_logger

log = get_logger("maios.actions", "action-center")

ACTION_TYPES = ("cost_template", "reactivation_segment")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(kind: str, payload: dict[str, Any]) -> None:
    try:
        from . import audit_log

        audit_log.record("runtime", f"action_prepared:{kind}", payload)
    except Exception:  # noqa: BLE001 — el audit nunca debe romper la acción
        log.warning("audit record failed for action %s", kind)


def _csv_bytes(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k) for k in fieldnames})
    return buf.getvalue()


def prepare_cost_template(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plantilla CSV para cargar costes de los productos sin coste verificable.

    Solo lectura: no importa nada. El usuario rellena la columna cost y la
    importa por el flujo normal (cost_importer)."""
    if data is None:
        data = config_store.load()
    products = [p for p in (data.get("organizedProducts") or []) if isinstance(p, dict)]
    try:
        from . import product_identity

        missing = [p for p in products if product_identity.resolve_cost(p).get("costStatus") == "missing"]
    except Exception:  # noqa: BLE001
        missing = [p for p in products if not (p.get("cost") or p.get("unitCost") or p.get("costPrice"))]
    # BUG real (Nico, audit.jsonl): la plantilla incluía productos SIN SKU (sku="").
    # Un producto sin SKU no tiene identidad para vincular el coste al importar la
    # plantilla -> fila inútil/rota. Se excluyen de la plantilla de costes por SKU.
    missing = [p for p in missing if str(p.get("sku") or "").strip()]
    rows = [
        {
            "sku": str(p.get("sku") or ""),
            "name": str(p.get("name") or "")[:80],
            "current_price": p.get("price") if p.get("price") is not None else "",
            "cost": "",
        }
        for p in missing
    ]
    csv_text = _csv_bytes(rows, ["sku", "name", "current_price", "cost"])
    payload = {"count": len(rows), "skus": [r["sku"] for r in rows[:5]]}
    _audit("cost_template", payload)
    return {
        "ok": True,
        "kind": "cost_template",
        "title": "Plantilla de costes — productos sin coste verificable",
        "description": (
            f"{len(rows)} productos no tienen coste verificable. Rellena la columna "
            "'cost' y carga el archivo por el flujo normal de importación de costes. "
            "Nada se modifica hasta que tú lo confirmes."
        ),
        "count": len(rows),
        "filename": "vanova-costes-pendientes.csv",
        "csv": csv_text,
        "rows": rows[:5],
        "preparedAt": _now(),
    }


def prepare_reactivation_segment(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Segmento de clientes inactivos con valor histórico, para una campaña de
    reactivación. Solo lectura: no envía nada."""
    if data is None:
        data = config_store.load()
    try:
        from . import business_signals, detection_engine

        ref = detection_engine._reference_date(data.get("organizedSales") or [])  # noqa: SLF001 — misma señal canónica
        signals = business_signals.compute_signals(data)
        cust = signals.get("customers") or []
    except Exception:  # noqa: BLE001
        cust = []
        ref = None
    rows = [
        {
            "customer": str(c.get("name") or ""),
            "orders": c.get("orders") or 0,
            "historical_revenue": round(c.get("revenue") or 0.0, 2),
            "last_order": str(c.get("lastOrder") or "")[:10],
            "days_inactive": c.get("daysSinceLastOrder") if c.get("daysSinceLastOrder") is not None else "",
        }
        for c in cust
        if (c.get("orders") or 0) >= detection_engine.REACTIVATION_MIN_ORDERS
        and (c.get("revenue") or 0.0) >= detection_engine.REACTIVATION_MIN_REVENUE
        and (c.get("daysSinceLastOrder") or 0) >= detection_engine.REACTIVATION_LAST_ORDER_DAYS
    ]
    rows.sort(key=lambda r: r["historical_revenue"], reverse=True)
    csv_text = _csv_bytes(rows, ["customer", "orders", "historical_revenue", "last_order", "days_inactive"])
    combined = round(sum(r["historical_revenue"] for r in rows), 2)
    _audit("reactivation_segment", {"count": len(rows), "combinedRevenue": combined})
    return {
        "ok": True,
        "kind": "reactivation_segment",
        "title": "Segmento de clientes inactivos para reactivar",
        "description": (
            f"{len(rows)} clientes recurrentes llevan {detection_engine.REACTIVATION_LAST_ORDER_DAYS}+ días "
            f"sin comprar (valor histórico conjunto {combined:.2f}€). Exporta la lista y "
            "usa el segmento para una campaña de reactivación. VANOVA no envía nada por ti."
        ),
        "count": len(rows),
        "combinedRevenue": combined,
        "filename": "vanova-clientes-inactivos.csv",
        "csv": csv_text,
        "rows": rows[:5],
        "preparedAt": _now(),
    }


def prepare(kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    if kind not in ACTION_TYPES:
        return {"ok": False, "error": f"Acción desconocida: {kind}"}
    fn = prepare_cost_template if kind == "cost_template" else prepare_reactivation_segment
    return fn(data)
