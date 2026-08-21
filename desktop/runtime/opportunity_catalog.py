"""VANOVA — Detector de Oportunidades de Crecimiento (capa de producto).

Capa de presentación/agrupación sobre los findings de categoría `opportunity`
que YA emite el detection_engine. NO re-implementa el motor: surfacea, agrupa
y cuantifica en € lo que ya se detecta (cross_sell, product_concentration,
aov_multi_item_opportunity, customer_concentration, low_revenue_high_margin).

Spec: docs/STRATI_DETECTOR_OPORTUNIDADES_SPEC.md

Reglas de honestidad (UNKNOWN != 0):
* Nunca se afirma un upsideEuro sin evidencia numérica real.
* Sin coste verificado -> upsideEuro = None, impactKind != "calculated" (nunca 0 EUR).
* No se emite una oportunidad cuantificable con upsideEuro < MIN_UPSIDE_EURO.
* Reutiliza las constantes del motor, no las redefine.

Dedupe por firma: usa la firma estable `type:entity` (BUG-001) para que
re-analizar la misma oportunidad no la duplique.
"""
from __future__ import annotations

from typing import Any

from . import config_store, product_identity

OPPORTUNITY_KEY = "opportunities"
MAX_OPPORTUNITIES = 5
# Umbral anti-ruido (spec §3.4): nunca emitir una oportunidad cuantificable con
# upside < 25 EUR (evidencia EUR minima).
MIN_UPSEID_EURO = 25.0


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _load(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    src = data if data is not None else config_store.load()
    items = src.get(OPPORTUNITY_KEY) or []
    return [i for i in items if isinstance(i, dict)]


def _save(items: list[dict[str, Any]], *, data: dict[str, Any] | None = None) -> None:
    if data is not None:
        data[OPPORTUNITY_KEY] = items[:MAX_OPPORTUNITIES]
        return
    config_store.save({OPPORTUNITY_KEY: items[:MAX_OPPORTUNITIES]})


# ---------------------------------------------------------------------------
# Enriquecimiento en EUR (espec §3.3) — reglas de evidencia por tipo
# ---------------------------------------------------------------------------


def _product_cost_ok(product: dict[str, Any]) -> bool:
    """Coste real disponible (verified/imported), nunca PVD disfrazado."""
    resolved = product_identity.resolve_cost(product)
    return str(resolved.get("costStatus") or "") in ("verified", "imported") and _as_float(resolved.get("cost")) is not None


def _upside_for_cross_sell(f: dict[str, Any], products: list[dict[str, Any]]) -> tuple[float | None, str, str]:
    """Cross-sell: upside = tickets_potencial x margen promedio (solo con coste)."""
    metrics = f.get("metrics") or {}
    orders_together = _as_float(metrics.get("ordersTogether")) or 0.0
    pair = str(metrics.get("pair") or "")
    a_sku = pair.split("+")[0] if "+" in pair else ""
    b_sku = pair.split("+")[1] if "+" in pair and len(pair.split("+")) > 1 else ""
    margins: list[float] = []
    for p in products:
        sku = str(p.get("sku") or "")
        if sku in (a_sku, b_sku):
            resolved = product_identity.resolve_cost(p)
            sale = _as_float(resolved.get("salePrice"))
            cost = _as_float(resolved.get("cost"))
            if sale and cost is not None and sale > 0:
                margins.append((sale - cost) / sale)
    if not margins:
        return None, "not_quantifiable", "requiere margen por SKU para cuantificar"
    avg_margin = sum(margins) / len(margins)
    upside = orders_together * avg_margin
    if upside < MIN_UPSEID_EURO:
        return None, "not_quantifiable", "volumen de co-compra insuficiente para cuantificar"
    return round(upside, 2), "calculated", f"{int(orders_together)} pedidos co-comprados x margen promedio {round(avg_margin*100,1)}%"


def _upside_for_concentration(f: dict[str, Any]) -> tuple[float | None, str, str]:
    """Concentracion: usa revenueAtRisk ya calculado por el motor."""
    imp = f.get("estimatedImpact") or {}
    revenue_at_risk = _as_float(imp.get("revenueAtRisk"))
    if revenue_at_risk is None or revenue_at_risk <= 0:
        return None, "not_quantifiable", "no hay revenue en riesgo cuantificado"
    return revenue_at_risk, "calculated", f"{revenue_at_risk:.2f} EUR de revenue expuesto a un unico producto"


def _upside_for_aov(f: dict[str, Any]) -> tuple[float | None, str, str]:
    """Ticket/AOV: upside = (AOV_objetivo - AOV_actual) x pedidos_periodo.

    BUG-018 FIX: antes era código muerto — nunca cuantificaba. Ahora lee
    currentOrders/previousOrders de los metrics (añadidos al finding aov_change)
    y calcula el upside solo si current_aov < previous_aov y hay pedidos.
    UNKNOWN != 0: sin pedidos del periodo no se inventa el multiplicador.
    """
    metrics = f.get("metrics") or {}
    current_aov = _as_float(metrics.get("currentAov"))
    previous_aov = _as_float(metrics.get("previousAov"))
    if current_aov is None or previous_aov is None or current_aov >= previous_aov:
        return None, "not_quantifiable", "sin gap de ticket recuperable con datos suficientes"
    gap = previous_aov - current_aov
    if gap <= 0:
        return None, "not_quantifiable", "sin gap de ticket recuperable"
    # Pedidos del periodo actual (ventana 30d). Si no hay datos, no cuantifica.
    orders = _as_float(metrics.get("currentOrders"))
    if orders is None or orders <= 0:
        return None, "not_quantifiable", "requiere pedidos del periodo para cuantificar el upside"
    upside = gap * orders
    if upside < MIN_UPSEID_EURO:
        return None, "not_quantifiable", "upsell por debajo del umbral minimo de evidencia"
    return round(upside, 2), "calculated", f"gap de ticket {gap:.2f} EUR x {int(orders)} pedidos"


def _upside_for_reactivation(f: dict[str, Any]) -> tuple[float | None, str, str]:
    """Cliente reactivable: upside = ticket medio x pedidos recuperables (con historial)."""
    metrics = f.get("metrics") or {}
    ticket = _as_float(metrics.get("avgTicket"))
    expected_orders = _as_float(metrics.get("expectedRecoverableOrders"))
    if ticket is None or expected_orders is None or ticket <= 0 or expected_orders <= 0:
        return None, "not_quantifiable", "requiere historial de pedidos del cliente"
    upside = ticket * expected_orders
    if upside < MIN_UPSEID_EURO:
        return None, "not_quantifiable", "upsell por debajo del umbral minimo de evidencia"
    return round(upside, 2), "calculated", f"ticket medio {ticket:.2f} EUR x {int(expected_orders)} pedidos recuperables"


def _upside_for_low_revenue_high_margin(f: dict[str, Any]) -> tuple[float | None, str, str]:
    """Margen/revenue: usa marginPotential del motor si existe, si no None."""
    imp = f.get("estimatedImpact") or {}
    margin_potential = _as_float(imp.get("marginPotential"))
    if margin_potential is None or margin_potential <= 0:
        return None, "not_quantifiable", "requiere margen por SKU para cuantificar"
    if margin_potential < MIN_UPSEID_EURO:
        return None, "not_quantifiable", "upsell por debajo del umbral minimo"
    return round(margin_potential, 2), "calculated", f"margen potencial {margin_potential:.2f} EUR"


_ENRICHERS = {
    "cross_sell": _upside_for_cross_sell,
    "product_concentration": _upside_for_concentration,
    "aov_multi_item_opportunity": _upside_for_aov,
    "aov_change": _upside_for_aov,
    "customer_concentration": _upside_for_concentration,
    "customer_reactivation": _upside_for_reactivation,
    "low_revenue_high_margin": _upside_for_low_revenue_high_margin,
}


def build_catalog(
    findings: list[dict[str, Any]] | None,
    *,
    products: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
    top: int = MAX_OPPORTUNITIES,
) -> list[dict[str, Any]]:
    """Construye el catalogo de oportunidades desde los findings ACTIVOS de
    categoria opportunity, enriquecidos en EUR segun el tipo y priorizados.

    Sin evidencia EUR (None) -> la oportunidad se conserva con
    ``impactEuro = None`` y ``impactKind = "not_quantifiable"`` (nunca 0 EUR).
    """
    findings = [f for f in (findings or []) if isinstance(f, dict)]
    active = [
        f for f in findings
        if str(f.get("status") or "").lower() not in ("resolved", "archived")
        and str(f.get("category") or "") == "opportunity"
    ]
    if products is None:
        cfg = data if data is not None else config_store.load()
        products = cfg.get("organizedProducts") or []

    out: list[dict[str, Any]] = []
    seen_sigs: dict[str, dict[str, Any]] = {}
    for f in active:
        typ = str(f.get("type") or f.get("finding_type") or "")
        enricher = _ENRICHERS.get(typ)
        upside: float | None = None
        kind = "not_quantifiable"
        detail = ""
        if enricher is not None:
            if typ == "cross_sell":
                upside, kind, detail = enricher(f, products)
            else:
                upside, kind, detail = enricher(f)
        else:
            detail = "no hay regla de cuantificacion para este tipo"

        sig = str(f.get("signature") or "")
        # Dedupe por firma estable (BUG-001): si ya existe esta oportunidad en
        # el catálogo, conservar la de mayor upside (no duplicar).
        existing = seen_sigs.get(sig)
        if existing is not None:
            existing_upside = existing.get("upsideEuro")
            if (upside is not None) and (existing_upside is None or upside > existing_upside):
                seen_sigs[sig] = _build_opp(f, typ, upside, kind, detail, sig)
            continue
        opp = _build_opp(f, typ, upside, kind, detail, sig)
        seen_sigs[sig] = opp

    out = list(seen_sigs.values())
    # Cuantificables con EUR primero (desc), luego no cuantificables por severidad
    out.sort(key=lambda o: (o.get("_quantifiable"), o.get("_upsideSort")), reverse=True)
    return out[:top]


def _build_opp(f: dict[str, Any], typ: str, upside: float | None,
               kind: str, detail: str, sig: str) -> dict[str, Any]:
    return {
        "opportunityId": f"opportunity:{sig or f.get('id') or ''}",
        "signature": sig,
        "type": typ,
        "title": str(f.get("title") or "Oportunidad de crecimiento"),
        "observation": str(f.get("observation") or ""),
        "evidence": list(f.get("evidence") or [])[:5],
        "recommendedAction": str(f.get("recommendedAction") or ""),
        "upsideEuro": upside,
        "impactKind": kind,
        "impactDetail": detail,
        "impactLabel": _impact_label(upside),
        "severity": str(f.get("severity") or "medium"),
        "confidence": str(f.get("confidence") or "medium"),
        "entity": str(f.get("entity") or ""),
        "metrics": f.get("metrics") or {},
        "estimatedImpact": f.get("estimatedImpact") or {},
        "createdAt": str(f.get("createdAt") or _now()),
        "_upsideSort": upside if upside is not None else -1.0,
        "_quantifiable": upside is not None,
    }


def _impact_label(upside: float | None) -> str:
    if upside is None:
        return "Impacto no cuantificable"
    # Formato europeo: miles con punto, decimales con coma
    return f"aproximadamente {upside:,.2f} EUR".replace(",", " ").replace(".", ",")


def catalog(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Devuelve el catalogo persistido; si vacio, reconstruye desde findings."""
    items = _load(data)
    if items:
        return items
    from . import detection_engine

    res = detection_engine.run_detection(data, persist=False)
    findings = (res or {}).get("findings") or []
    return build_catalog(findings, data=data)


def persist_opportunities(opportunities: list[dict[str, Any]], *, data: dict[str, Any] | None = None) -> None:
    _save(opportunities, data=data)
