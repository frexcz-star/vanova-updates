"""VANOVA Business Detection Engine — FASE 8.

Motor de detección empresarial DETERMINISTA basado en evidencia. Detecta hechos
y oportunidades a partir de reglas y métricas reales del modelo canónico;
Hermes actúa solo como capa de interpretación/conversación sobre estos
hallazgos. El motor NUNCA inventa: sin datos suficientes no genera finding.

Cadena: DATOS CANÓNICOS → MÉTRICAS → MOTOR → HALLAZGOS → EVIDENCIA → IMPACTO
→ HERMES → RECOMENDACIÓN EXPLICADA.  Nunca: LLM → OPINIÓN → DATO INVENTADO.

Cada hallazgo:
  id, signature (dedupe), type, severity, category (problem|opportunity|positive),
  title, observation, evidence[], metrics, period, source[], confidence,
  estimatedImpact {kind: calculated|estimated, ...}, recommendedAction,
  createdAt/updatedAt/lastSeenAt/timesSeen, status (new|active|acknowledged|
  resolved|archived).

Reglas de evidencia (umbrales en constantes): un finding solo se emite cuando
la muestra es suficiente y los datos no están desactualizados. El impacto se
etiqueta SIEMPRE: calculated (aritmética sobre datos reales) vs estimated.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from . import business_model, config_store

# ---------------------------------------------------------------------------
# Umbrales (documentados — reglas de evidencia)
# ---------------------------------------------------------------------------
MIN_ORDERS_TOTAL = 20            # pedidos mínimos para analítica de producto
MIN_ORDERS_WITH_A = 10           # pedidos mínimos que contienen A para cross-sell
MIN_CO_OCCUR_FREQ = 0.15         # frecuencia mínima de co-aparición (15%)
MIN_ORDERS_PER_PERIOD = 10       # pedidos mínimos por período para AOV/evolución
MIN_PERIOD_UNITS = 5             # unidades mínimas en período base (evita muestras diminutas)
CHANGE_PCT = 0.30                # variación mínima para caída/crecimiento de producto
AOV_CHANGE_PCT = 0.10            # variación mínima para ticket medio
EXPENSE_GROWTH_PCT = 0.25        # crecimiento mínimo de gastos
HIGH_REV_SHARE = 0.15            # share de revenue para "mucho revenue"
MARGIN_GAP_POINTS = 10.0         # puntos de margen por debajo del promedio
LOW_MARGIN_PCT = 0.15            # margen absoluto bajo
HIGH_MARKUP_PCT = 1.0            # markup alto (100%)
COST_COVERAGE_MIN = 0.6          # fracción mínima de SKUs con coste
STALE_DAYS = 7                   # datos más viejos que esto = desactualizados
RECON_CRITICAL_MAX = 0           # discrepancias high de reconciliación toleradas

# Capa de vitalidad de producto (SPEC vitalidad). Ventana de vida: un producto
# es VIVO si tiene ≥1 venta real en los últimos VITALITY_WINDOW_DAYS días,
# medido contra la fecha de referencia del dataset (no "hoy"). 90 días = 1 trimestre.
VITALITY_WINDOW_DAYS = 90
DECLINE_WINDOW_DAYS = 180        # ventana amplia para detectar "producto en declive"

FINDING_STATUSES = ("new", "active", "acknowledged", "resolved", "archived")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days_ago(n: int, ref: datetime | None = None) -> str:
    base = ref or datetime.now(timezone.utc)
    return (base - timedelta(days=n)).isoformat()


def _period_bounds(days: int, ref: datetime | None = None) -> tuple[str, str]:
    # MEGA UPDATE (A2/A4): las ventanas se calculan desde la fecha de
    # referencia de los DATOS (no "hoy"), igual que business_signals. Antes la
    # firma usaba _now() → el mismo finding se duplicaba al cambiar de día
    # aunque los datos fueran los mismos.
    base = ref or datetime.now(timezone.utc)
    return (base - timedelta(days=days)).isoformat(), base.isoformat()


def _as_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _reference_date(rows: list[dict[str, Any]]) -> datetime | None:
    """Fecha de referencia = última fecha real del dataset (no 'hoy')."""
    best: datetime | None = None
    for r in rows:
        d = _as_date(r.get("date"))
        if d is not None and (best is None or d > best):
            best = d
    return best


def product_vitality(sku: str, sales: list[dict[str, Any]], *, ref: datetime | None = None) -> dict[str, Any]:
    """Capa de vitalidad de producto (SPEC vitalidad, P1).

    Un producto es VIVO si tiene ≥1 venta real en los últimos
    VITALITY_WINDOW_DAYS días, medido contra la fecha de referencia del dataset
    (no "hoy" inventado). Regla de honestidad: la ventana se mide contra
    `_reference_date(sales)`; si no hay datos de ventas con fecha, se degrada
    (no se inventa una vida).

    Devuelve: {es_vivo, ultima_venta_dias, ventas_en_ventana, window_days,
               decline (ventas en ventana amplia pero no en la corta), calculable}
    """
    key = str(sku or "").strip().lower()
    if not key:
        return {"es_vivo": False, "ultima_venta_dias": None, "ventas_en_ventana": 0,
                "window_days": VITALITY_WINDOW_DAYS, "calculable": False}
    # Fecha de referencia = la más reciente del dataset (no "hoy" inventado).
    ref_date = ref or _reference_date(sales)
    if ref_date is None:
        # Sin datos de ventas con fecha: no se puede calcular vitalidad.
        return {"es_vivo": False, "ultima_venta_dias": None, "ventas_en_ventana": 0,
                "window_days": VITALITY_WINDOW_DAYS, "calculable": False}
    window_start = ref_date - timedelta(days=VITALITY_WINDOW_DAYS)
    decline_start = ref_date - timedelta(days=DECLINE_WINDOW_DAYS)
    ventas_sku: list[datetime] = []
    ventas_decline: list[datetime] = []
    for s in sales:
        sk = str((s or {}).get("sku") or "").strip().lower()
        d = _as_date(s.get("date"))
        if sk != key or d is None:
            continue
        if d >= window_start:
            ventas_sku.append(d)
        if d >= decline_start:
            ventas_decline.append(d)
    ventas_sku.sort()
    ventas_decline.sort()
    ultima = ventas_sku[-1] if ventas_sku else None
    es_vivo = len(ventas_sku) > 0
    # Declive: tuvo ventas en 180d pero 0 en 90d (se está muriendo).
    en_declive = (not es_vivo) and len(ventas_decline) > 0
    return {
        "es_vivo": es_vivo,
        "en_declive": en_declive,
        "ultima_venta_dias": (ref_date - ultima).days if ultima else None,
        "ventas_en_ventana": len(ventas_sku),
        "window_days": VITALITY_WINDOW_DAYS,
        "calculable": True,
    }


# ---------------------------------------------------------------------------
# Calidad de datos — puerta de entrada del motor
# ---------------------------------------------------------------------------


def data_quality(data: dict[str, Any]) -> dict[str, Any]:
    """Comprueba antes de generar hallazgos: muestra, costes, frescura,
    reconciliación. Si no se cumple, el motor degrada o no genera."""
    sales = data.get("organizedSales") or []
    products = data.get("organizedProducts") or []
    invoices = data.get("organizedInvoices") or []
    if not isinstance(sales, list):
        sales = []
    if not isinstance(products, list):
        products = []
    if not isinstance(invoices, list):
        invoices = []

    # FASE 11: el coste solo cuenta si es VERIFICADO/importado con evidencia
    # (coste == PVD sin fuente NO es coste real) y la línea tiene identidad
    # canónica (SKU/barcode/variant-ID/mapping manual).
    from . import product_identity

    with_cost = sum(1 for p in products if isinstance(p, dict) and product_identity.cost_available(p))
    coverage = with_cost / len(products) if products else 0.0
    cc = product_identity.cost_coverage(sales, products)
    ic = product_identity.identity_coverage(sales, products)
    identity_cov = ic.get("coveragePct") or 0.0

    # Frescura: última sync de Shopify/FS o fecha del snapshot
    snapshot = data.get("dashboardSnapshot") or {}
    fetched_at = (snapshot.get("fetchedAt") or "") if isinstance(snapshot, dict) else ""
    fs_state = data.get("facturascriptSync") or {}
    last_sync = str(fs_state.get("lastSync") or fetched_at or "")
    stale = False
    if last_sync:
        dt = _as_date(last_sync)
        if dt is not None and (datetime.now(timezone.utc) - dt).days > STALE_DAYS:
            stale = True

    recon = data.get("financialReconciliation") or {}
    recon_high = 0
    if isinstance(recon, dict):
        recon_high = sum(1 for i in (recon.get("items") or []) if i.get("severity") == "high")

    sales_dated = [s for s in sales if _as_date(s.get("date")) is not None]
    notes: list[str] = []
    if products and coverage < COST_COVERAGE_MIN:
        notes.append(
            f"Bloqueado por falta de coste real: solo {with_cost} de {len(products)} productos tienen "
            "coste verificado/importado (coste == PVD sin evidencia no cuenta)."
        )
    if sales and identity_cov < 60.0:
        # identity_cov es el % con correspondencia FIABLE; lo que no tiene es 100 − cov
        _no_match = round(100 - identity_cov, 1)
        _matched = round(identity_cov, 1)
        notes.append(
            f"Bloqueado por identidad de producto: el {_no_match}% del revenue no tiene "
            f"correspondencia fiable con el catálogo (solo el {_matched}% tiene match)."
        )
    if sales_dated and len(sales_dated) < MIN_ORDERS_TOTAL:
        notes.append(
            f"Muestra insuficiente: {len(sales_dated)} pedidos con fecha (se requieren {MIN_ORDERS_TOTAL} "
            "para analítica de producto)."
        )
    # FASE 12 (P9): aunque la muestra total sea suficiente, los hallazgos de
    # período (caída/crecimiento, AOV, margen por producto) comparan ventanas
    # de 30 días. Si casi no hay pedidos recientes, no hay comparación fiable
    # y el motor debe EXPLICARLO en vez de devolver 0 en silencio.
    ref_dt = _reference_date(sales_dated)
    recent_from = ((ref_dt or datetime.now(timezone.utc)) - timedelta(days=60)).date()
    recent = [s for s in sales_dated if _as_date(s.get("date")) is not None and _as_date(s.get("date")).date() >= recent_from]
    if sales and len(recent) < MIN_ORDERS_PER_PERIOD:
        notes.append(
            f"Muestra reciente insuficiente: solo {len(recent)} pedidos en los últimos 60 días "
            f"(se requieren {MIN_ORDERS_PER_PERIOD} para comparar períodos de 30 días). "
            "Los hallazgos de caída/crecimiento, ticket medio y margen por producto "
            "no son fiables con tan poca actividad reciente; no se emiten para no inventar."
        )
    return {
        "ordersTotal": len(sales),
        "ordersDated": len(sales_dated),
        "productsTotal": len(products),
        "costCoverage": round(coverage, 3),
        "costCoverageOk": coverage >= COST_COVERAGE_MIN,
        "identityCoveragePct": round(identity_cov, 1),
        "identityCoverageOk": identity_cov >= 60.0,
        "revenueWithVerifiedCost": cc.get("revenueWithVerifiedCost"),
        "revenueTotal": round((cc.get("revenueWithVerifiedCost") or 0.0) + (cc.get("revenueWithMissingCost") or 0.0), 2),
        "stale": stale,
        "lastSync": last_sync or None,
        "reconciliationHighIssues": recon_high,
        "reconciliationOk": recon_high <= RECON_CRITICAL_MAX,
        "canAnalyzeProducts": len(sales_dated) >= MIN_ORDERS_TOTAL and coverage >= COST_COVERAGE_MIN and identity_cov >= 60.0 and not stale,
        "canAnalyzeMargin": coverage >= COST_COVERAGE_MIN and identity_cov >= 60.0,
        "canAnalyzeTreasury": bool(data.get("organizedFinance")) and bool(invoices),
        "canAnalyzeExpenses": len(invoices) >= 2,
        "notes": notes,
    }# ---------------------------------------------------------------------------
# Métricas derivadas (del modelo canónico)
# ---------------------------------------------------------------------------
# MEGA UPDATE (A9): `_product_metrics` se eliminó — calculaba revenue/margen
# por SKU por un camino duplicado de `business_signals.product_signals` (la
# única fuente de verdad que consume detect_products). Sin llamadores quedaba
# como código muerto con cálculo duplicado de coste/ventanas.


def _cross_sell_pairs(sales: list[dict[str, Any]], products: list[dict[str, Any]]) -> list[dict[str, Any]]: 
    """Pares de productos co-comprados con frecuencia y margen combinado.
    FASE 11: el coste solo se resuelve con verificación (nunca netPrice a ciegas);
    el finding de cross-sell se basa en la frecuencia REAL de co-compra, no en
    márgenes estimados."""
    from . import product_identity

    cost_by_sku: dict[str, float] = {}
    for p in products:
        if not isinstance(p, dict):
            continue
        rc = product_identity.resolve_cost(p)
        sku = str(p.get("sku") or "").strip().lower()
        if sku and rc.get("costStatus") in ("verified", "imported") and rc.get("cost") is not None:
            cost_by_sku[sku] = rc["cost"]

    per_order: list[set[str]] = []
    for s in sales:
        # FASE 13 (P8): normaliza filas planas de CSV igual que líneas de tienda.
        lines = business_model.normalize_sale_lines(s)
        if len(lines) < 2:
            continue
        skus = {str(li.get("sku") or "").strip().lower() for li in lines if str(li.get("sku") or "").strip()}
        if len(skus) >= 2:
            per_order.append(skus)

    from collections import Counter

    counts_a: Counter[str] = Counter()
    co: Counter[tuple[str, str]] = Counter()
    for skus in per_order:
        for sku in skus:
            counts_a[sku] += 1
        ordered = sorted(skus)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                co[(ordered[i], ordered[j])] += 1

    pairs: list[dict[str, Any]] = []
    for (a, b), n in co.items():
        n_a = counts_a[a]
        freq = n / n_a if n_a else 0.0
        if n_a < MIN_ORDERS_WITH_A or freq < MIN_CO_OCCUR_FREQ:
            continue
        pairs.append({
            "pair": [a, b],
            "ordersTogether": n,
            "ordersWithA": n_a,
            "frequency": round(freq, 4),
            "marginA": None,
            "marginB": None,
            "combinedMarginPct": None,
        })
    pairs.sort(key=lambda r: (r["frequency"], r["ordersTogether"]), reverse=True)
    return pairs[:8]


def _multi_item_share(sales: list[dict[str, Any]], lo: datetime.date, hi: datetime.date) -> float | None:
    """Fracción de pedidos con >=2 SKUs distintos en la ventana [lo, hi].
    None si no hay pedidos con líneas suficientes para medirlo."""
    n = 0
    multi = 0
    for s in sales:
        d = _as_date(s.get("date"))
        if d is None or d.date() < lo or d.date() > hi:
            continue
        lines = s.get("line_items")
        if not isinstance(lines, list) or not lines:
            continue
        skus = {str(li.get("sku") or "").strip().lower() for li in lines if isinstance(li, dict) and str(li.get("sku") or "").strip()}
        if not skus:
            continue
        n += 1
        if len(skus) >= 2:
            multi += 1
    return round(multi / n * 100, 1) if n else None


def _aov_metrics(sales: list[dict[str, Any]]) -> dict[str, Any]:
    ref = _reference_date(sales)
    now = (ref or datetime.now(timezone.utc)).date()
    cur_from = now - timedelta(days=30)
    prev_to = cur_from - timedelta(days=1)
    prev_from = cur_from - timedelta(days=30)

    def _bucket(lo: datetime.date, hi: datetime.date) -> tuple[float, int]:
        rev = 0.0
        n = 0
        for s in sales:
            d = _as_date(s.get("date"))
            if d is None or d.date() < lo or d.date() > hi:
                continue
            t = business_model._as_float(s.get("total"))
            if t is not None:
                rev += t
                n += 1
        return rev, n

    cur_rev, cur_n = _bucket(cur_from, now)
    prev_rev, prev_n = _bucket(prev_from, prev_to)
    cur_aov = cur_rev / cur_n if cur_n else None
    prev_aov = prev_rev / prev_n if prev_n else None
    change = None
    if cur_aov and prev_aov:
        change = round((cur_aov - prev_aov) / prev_aov * 100, 1)
    return {"currentAov": cur_aov, "previousAov": prev_aov, "changePct": change, "currentOrders": cur_n, "previousOrders": prev_n}


def _expense_metrics(invoices: list[dict[str, Any]]) -> dict[str, Any]:
    """Gastos mensuales desde facturas recibidas (por mes del último año)."""
    by_month: dict[str, float] = {}
    for inv in invoices:
        if not isinstance(inv, dict) or inv.get("type") != "received":
            continue
        total = business_model._as_float(inv.get("total"))
        month = str(inv.get("date") or "")[:7]
        if total is None or len(month) != 7:
            continue
        by_month[month] = by_month.get(month, 0.0) + total
    months = sorted(by_month)
    cur_month = months[-1] if months else None
    prev_month = months[-2] if len(months) >= 2 else None
    growth = None
    if cur_month and prev_month and by_month[prev_month] > 0:
        growth = round((by_month[cur_month] - by_month[prev_month]) / by_month[prev_month] * 100, 1)
    return {"byMonth": by_month, "currentMonth": cur_month, "previousMonth": prev_month, "currentTotal": by_month.get(cur_month) if cur_month else None, "previousTotal": by_month.get(prev_month) if prev_month else None, "growthPct": growth}


def _treasury_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Métricas de tesorería desde cobros/pagos/facturas. NUNCA deriva saldo
    bancario: lo que no existe se declara no disponible."""
    invoices = data.get("organizedInvoices") or []
    finance = data.get("organizedFinance") or []
    collections = [f for f in finance if isinstance(f, dict) and f.get("type") == "collection"]
    payments = [f for f in finance if isinstance(f, dict) and f.get("type") == "payment"]
    col_total = round(sum(c.get("amount", 0) for c in collections if isinstance(c.get("amount"), (int, float))), 2)
    received = [i for i in invoices if isinstance(i, dict) and i.get("type") == "received"]
    pending_pay = [i for i in received if not i.get("paid")]
    pending_pay_total = round(sum(i.get("total", 0) for i in pending_pay if isinstance(i.get("total"), (int, float))), 2)
    due_soon = [i for i in pending_pay if i.get("dueDate") and _due_within(i.get("dueDate"), 30)]
    due_soon_total = round(sum(i.get("total", 0) for i in due_soon if isinstance(i.get("total"), (int, float))), 2)
    ratio = round(due_soon_total / col_total * 100, 1) if col_total else None
    return {
        "collectionsTotal": col_total,
        "collectionsCount": len(collections),
        "pendingPaymentsTotal": pending_pay_total,
        "pendingPaymentsCount": len(pending_pay),
        "upcomingDuePaymentsTotal": due_soon_total,
        "upcomingDuePaymentsCount": len(due_soon),
        "upcomingVsCollectionsPct": ratio,
        "bankBalance": {"category": "not_available", "reason": "VANOVA no tiene integración bancaria"},
    }


def _due_within(due_date: str, days: int) -> bool:
    d = _as_date(due_date)
    if d is None:
        return False
    today = datetime.now(timezone.utc).date()
    return today <= d.date() <= today + timedelta(days=days)


# ---------------------------------------------------------------------------
# Fábrica de hallazgos
# ---------------------------------------------------------------------------


def make_finding(
    *,
    finding_type: str,
    severity: str,
    category: str,
    title: str,
    observation: str,
    evidence: list[str],
    metrics: dict[str, Any],
    period: dict[str, Any],
    source: list[str],
    confidence: str,
    estimated_impact: dict[str, Any],
    recommended_action: str,
) -> dict[str, Any]:
    # MEGA UPDATE (A4): la entidad de la firma debe ser ESPECÍFICA para que el
    # dedupe no colapse findings distintos bajo el mismo scope (p. ej. dos
    # clientes en churn con scope='customer'). Orden: sku → pair → customer /
    # supplier / orderId → scope.
    entity = (
        metrics.get("sku")
        or metrics.get("pair")
        or metrics.get("customer")
        or metrics.get("supplier")
        or metrics.get("orderId")
        or metrics.get("category")
        or metrics.get("scope")
        or "global"
    )
    # MEGA UPDATE (A2/A4): la firma debe ser ESTABLE con los datos (no con
    # "hoy"). Se deriva del inicio de la ventana del periodo, que ahora es
    # relativo a la fecha de referencia de los datos; sin ventana, se usa la
    # fecha del periodo textual si existe (p. ej. 'YYYY-MM') o el día actual
    # como último recurso.
    # BUG-001 FIX: la firma debe ser ESTABLE con la identidad del finding, NO
    # con la ventana temporal. Antes incluía window_start (derivado de la fecha
    # de referencia de los datos); cuando llegaban datos nuevos, ref se
    # desplazaba → todas las firmas cambiaban → los findings viejos ya no
    # coincidían por firma y se recreaban como nuevos (duplicación 6→12).
    # La ventana temporal es metadata (period), no identidad: un finding del
    # mismo tipo sobre la misma entidad es el MISMO finding siempre, aunque la
    # magnitud cambie. La firma = type:entity.
    signature = f"{finding_type}:{entity}"
    return {
        "id": f"find_{uuid.uuid4().hex[:10]}",
        "signature": signature,
        "type": finding_type,
        "severity": severity,
        "category": category,
        "title": title,
        "observation": observation,
        "evidence": evidence,
        "metrics": metrics,
        "period": period,
        "source": source,
        "confidence": confidence,
        "estimatedImpact": estimated_impact,
        "recommendedAction": recommended_action,
        "createdAt": _now(),
        "updatedAt": _now(),
        "lastSeenAt": _now(),
        "timesSeen": 1,
        "status": "new",
    }


# ---------------------------------------------------------------------------
# Detectores
# ---------------------------------------------------------------------------


def detect_products(prod: list[dict[str, Any]], quality: dict[str, Any], period: dict[str, Any], sales: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """FASE B — detectores de producto sobre las SEÑALES canónicas (una sola
    fuente de verdad, coherente con business_signals): margen de catálogo
    (full history), share de revenue (full history) y tendencia 30d relativa
    a los datos. Caída/crecimiento no dependen del coste."""
    findings: list[dict[str, Any]] = []
    if not quality["canAnalyzeProducts"] or not prod:
        return findings
    avg_margin_items = [i for i in prod if i["hasCost"] and i["marginPct"] is not None and i["revenue"] > 0]
    avg_margin: float | None = None
    if quality.get("canAnalyzeMargin") and len(avg_margin_items) >= 5:
        total_rev = sum(i["revenue"] for i in avg_margin_items) or 1.0
        avg_margin = sum(i["marginPct"] * i["revenue"] for i in avg_margin_items) / total_rev

    for i in prod:
        if i["revenue"] <= 0 and i["unitsPrev30d"] <= 0:
            continue
        if avg_margin is not None and i["hasCost"] and i["revenue"] > 0 and i["marginPct"] is not None:
            _emit_margin_findings(findings, i, avg_margin, period)
        # FASE C (B7): tendencia de ventana LARGA (60d previos vs 30d actuales)
        # para capturar caídas que ocurrieron antes de la ventana 30d más
        # reciente (declive sostenido de varios meses), sin exigir coste.
        if i["revenuePrev60d"] >= 50 and i["revenue30d"] < i["revenuePrev60d"] * 0.7 and i["unitsPrev60d"] >= MIN_PERIOD_UNITS:
            long_change = (i["revenue30d"] - i["revenuePrev60d"]) / i["revenuePrev60d"]
            if long_change <= -CHANGE_PCT:
                findings.append(make_finding(
                    finding_type="product_declining",
                    severity="high" if long_change <= -0.5 else "medium",
                    category="problem",
                    title=f"{i['sku']} en caída de ingresos",
                    observation=(
                        f"{i['sku']} cae un {round(long_change*100,1)}% en revenue comparando los "
                        f"últimos 30 días ({i['revenue30d']:.2f}€) contra los 60 días anteriores "
                        f"({i['revenuePrev60d']:.2f}€) — declive sostenido."
                    ),
                    evidence=[
                        f"Revenue 30d actuales {i['revenue30d']:.2f}€ vs 60d previos {i['revenuePrev60d']:.2f}€",
                        f"Unidades {i['unitsPrev60d']} (60d previos) → {i['units30d']} (30d actuales)",
                    ],
                    metrics={"sku": i["sku"], "revenue": i["revenue30d"], "prevRevenue": i["revenuePrev60d"], "revenueChangePct": round(long_change * 100, 1), "units": i["units30d"], "prevUnits": i["unitsPrev60d"], "window": "30d_vs_prev60d"},
                    period={"current": period["current30d"], "previous": period["previous30d"]},
                    source=["sales_line_items"],
                    confidence="high" if long_change <= -0.5 else "medium",
                    estimated_impact={"kind": "estimated", "explanation": "Evitar la caída sostenida", "marginPotential": None},
                    recommended_action="Revisa stock, visibilidad, precio o competencia de este producto.",
                ))
        # Tendencia 30d (relativa a los datos): unidades y revenue bastan.
        if i["unitsPrev30d"] >= MIN_PERIOD_UNITS:
            change_rev = (i["revenue30d"] - i["revenuePrev30d"]) / i["revenuePrev30d"] if i["revenuePrev30d"] else 0.0
            change_units = (i["units30d"] - i["unitsPrev30d"]) / i["unitsPrev30d"] if i["unitsPrev30d"] else 0.0
            if change_rev <= -CHANGE_PCT and i["revenuePrev30d"] >= 50:
                findings.append(make_finding(
                    finding_type="product_declining",
                    severity="high" if change_rev <= -0.5 else "medium",
                    category="problem",
                    title=f"{i['sku']} en caída de ingresos",
                    observation=(
                        f"{i['sku']} cae un {round(change_rev*100,1)}% en revenue en los últimos 30 días "
                        f"({i['revenuePrev30d']:.2f}€ → {i['revenue30d']:.2f}€); unidades {round(change_units*100,1)}%."
                    ),
                    evidence=[
                        f"Revenue 30d anteriores {i['revenuePrev30d']:.2f}€ → 30d actuales {i['revenue30d']:.2f}€",
                        f"Unidades {i['unitsPrev30d']} → {i['units30d']}",
                    ],
                    metrics={"sku": i["sku"], "revenue": i["revenue30d"], "prevRevenue": i["revenuePrev30d"], "revenueChangePct": round(change_rev * 100, 1), "units": i["units30d"], "prevUnits": i["unitsPrev30d"]},
                    period={"current": period["current30d"], "previous": period["previous30d"]},
                    source=["sales_line_items"],
                    confidence="high" if change_rev <= -0.5 else "medium",
                    estimated_impact={"kind": "estimated", "explanation": "Evitar la caída sostenida", "marginPotential": None},
                    recommended_action="Revisa stock, visibilidad, precio o competencia de este producto.",
                ))
            elif change_rev >= CHANGE_PCT and i["revenue30d"] >= MIN_PERIOD_UNITS * 5 and i["units30d"] >= MIN_PERIOD_UNITS:
                findings.append(make_finding(
                    finding_type="product_growing",
                    severity="low",
                    category="positive",
                    title=f"{i['sku']} en crecimiento",
                    observation=f"{i['sku']} crece un {round(change_rev*100,1)}% en revenue (30d previos {i['revenuePrev30d']:.2f}€ → 30d actuales {i['revenue30d']:.2f}€).",
                    evidence=[f"Revenue {i['revenuePrev30d']:.2f}€ → {i['revenue30d']:.2f}€", f"Unidades {i['unitsPrev30d']} → {i['units30d']}"],
                    metrics={"sku": i["sku"], "revenue": i["revenue30d"], "prevRevenue": i["revenuePrev30d"], "revenueChangePct": round(change_rev * 100, 1)},
                    period={"current": period["current30d"], "previous": period["previous30d"]},
                    source=["sales_line_items"],
                    confidence="medium",
                    estimated_impact={"kind": "estimated", "explanation": "Reforzar el canal que está funcionando"},
                    recommended_action="Refuerza stock y visibilidad de este producto.",
                ))
    # PRODUCT LEAP — concentración de producto RAZONADA: si un solo producto
    # concentra >=25% del revenue es un riesgo estratégico y, cuando existen
    # sustitutos con comportamiento compatible, una oportunidad de diversificar.
    # Nunca se emite sin evidencia: share real del revenue + catálogo.
    with_rev = [i for i in prod if i["revenue"] > 0]
    if with_rev:
        top_prod = max(with_rev, key=lambda i: i["revenueShare"])
        if top_prod["revenueShare"] >= PRODUCT_CONCENTRATION_SHARE and top_prod["revenue"] >= PRODUCT_CONCENTRATION_MIN_REVENUE:
            # CAPA DE VITALIDAD DE PRODUCTO (SPEC vitalidad, P1.2): antes de
            # emitir una señal de riesgo/oportunidad sobre un producto, se
            # consulta su vitalidad (ventas reales en los últimos 90 días contra
            # la fecha de referencia del dataset). Un producto MUERTO (0 ventas
            # en 90d) no es una señal real: se descarta la dependencia y se
            # emite como `no_signal` con explicación en €. Si está en declive
            # (ventas en 180d pero 0 en 90d), se emite como hallazgo informativo
            # de declive, no como riesgo de dependencia.
            vitality = product_vitality(top_prod["sku"], sales or [])
            if not vitality.get("calculable"):
                # Sin datos de ventas con fecha: no se puede validar vitalidad.
                # Degradar a estimated (regla de honestidad, no inventar vida).
                # Se mantiene la lógica normal de concentración (con diversifiers)
                # pero con kind='estimated' y nota honesta.
                def _prod_change(item: dict[str, Any]) -> float | None:
                    if item.get("revenuePrev30d"):
                        return (item.get("revenue30d", 0.0) - item["revenuePrev30d"]) / item["revenuePrev30d"]
                    return None
                top_change = _prod_change(top_prod)
                candidates = [
                    i for i in with_rev
                    if i["sku"] != top_prod["sku"]
                    and i["revenue30d"] >= top_prod["revenue30d"] * 0.05
                    and (_prod_change(i) or 0.0) >= 0.0
                ]
                candidates.sort(key=lambda i: i["revenue"], reverse=True)
                declining = top_change is not None and top_change <= -CHANGE_PCT
                f = make_finding(
                    finding_type="product_concentration",
                    severity="high" if declining else "medium",
                    category="opportunity",
                    title=f"Dependencia de un solo producto: {top_prod['sku']}",
                    observation=(
                        f"El producto {top_prod['sku']} concentra el {round(top_prod['revenueShare']*100,1)}% del revenue "
                        f"({top_prod['revenue']:.2f}€). No hay suficientes datos de ventas con fecha para validar su vitalidad."
                    ),
                    evidence=[
                        f"Revenue {top_prod['revenue']:.2f}€ = {round(top_prod['revenueShare']*100,1)}% del total",
                        "No hay suficientes datos de ventas con fecha para validar la vitalidad de este producto.",
                    ] + ([f"Sustitutos con crecimiento compatible: {', '.join(i['sku'] for i in candidates[:3])}"] if candidates else []),
                    metrics={"sku": top_prod["sku"], "revenue": top_prod["revenue"], "revenueShare": top_prod["revenueShare"], "changePct": round(top_change * 100, 1) if top_change is not None else None, "diversifiers": [i["sku"] for i in candidates[:3]]},
                    period={"current": period["current30d"], "previous": period["previous30d"]},
                    source=["sales_line_items"],
                    confidence="low",
                    estimated_impact={"kind": "estimated", "explanation": "No hay suficientes datos de ventas para validar la vitalidad de este producto.", "revenueAtRisk": round(top_prod["revenue"], 2)},
                    recommended_action="Conecta ventas con fecha para validar la vitalidad de este producto.",
                )
                f["kind"] = "estimated"
                findings.append(f)
            elif not vitality.get("es_vivo") and vitality.get("en_declive"):
                # Producto en declive: tuvo ventas en 180d pero 0 en 90d. Se
                # emite como hallazgo INFORMATIVO de declive, no como riesgo de
                # dependencia (evita el falso positivo).
                f = make_finding(
                    finding_type="product_decline",
                    severity="low",
                    category="risk",
                    title=f"Producto en declive: {top_prod['sku']}",
                    observation=(
                        f"El producto {top_prod['sku']} tuvo ventas en el trimestre pero ninguna en los últimos 90 días. "
                        "Está dejando de venderse — revisar si es una línea que se va a descontinuar."
                    ),
                    evidence=[
                        f"Sin ventas en los últimos {VITALITY_WINDOW_DAYS} días, pero con ventas en la ventana de {DECLINE_WINDOW_DAYS} días",
                        f"Concentra {round(top_prod['revenueShare']*100,1)}% del revenue histórico ({top_prod['revenue']:.2f}€)",
                    ],
                    metrics={"sku": top_prod["sku"], "revenue": top_prod["revenue"], "revenueShare": top_prod["revenueShare"], "vitality": "declining"},
                    period={"current": period["current30d"], "previous": period["previous30d"]},
                    source=["sales_line_items"],
                    confidence="high",
                    estimated_impact={"kind": "info", "explanation": "Producto en declive — revisar si se descontinúa."},
                    recommended_action="Revisa si el producto se va a descontinuar o necesita reposición de demanda.",
                )
                f["kind"] = "info"
                findings.append(f)
            elif not vitality.get("es_vivo"):
                # Producto MUERTO (0 ventas en 90d, sin declive): descartar la
                # dependencia como no_signal con explicación honesta en €.
                ultima = vitality.get("ultima_venta_dias")
                ultima_txt = f"última venta hace {ultima} días" if ultima is not None else "sin ventas registradas"
                f = make_finding(
                    finding_type="product_concentration",
                    severity="low",
                    category="product",
                    title=f"[Descartada] Dependencia de {top_prod['sku']} — no es un riesgo real",
                    observation=(
                        f"Este producto no se vende en los últimos {VITALITY_WINDOW_DAYS} días ({ultima_txt}). "
                        "Concentra revenue histórico, pero de algo que ya no se vende. Sin riesgo real en €."
                    ),
                    evidence=[
                        f"Última venta hace {ultima} días" if ultima is not None else "Sin ventas recientes",
                        f"Concentra {round(top_prod['revenueShare']*100,1)}% del revenue histórico ({top_prod['revenue']:.2f}€)",
                        "Producto obsoleto/fuera de catálogo — la dependencia no es una señal real",
                    ],
                    metrics={"sku": top_prod["sku"], "revenue": top_prod["revenue"], "revenueShare": top_prod["revenueShare"], "vitality": "dead"},
                    period={"current": period["current30d"], "previous": period["previous30d"]},
                    source=["sales_line_items"],
                    confidence="high",
                    estimated_impact={"kind": "none", "explanation": "Producto sin ventas en 90 días — sin riesgo real en €."},
                    recommended_action="No es una oportunidad accionable: el producto ya no se vende.",
                )
                f["kind"] = "no_signal"
                findings.append(f)
            else:
                def _prod_change(item: dict[str, Any]) -> float | None:
                    if item.get("revenuePrev30d"):
                        return (item.get("revenue30d", 0.0) - item["revenuePrev30d"]) / item["revenuePrev30d"]
                    return None

                top_change = _prod_change(top_prod)
                candidates = [
                    i for i in with_rev
                    if i["sku"] != top_prod["sku"]
                    and i["revenue30d"] >= top_prod["revenue30d"] * 0.05
                    and (_prod_change(i) or 0.0) >= 0.0
                ]
                candidates.sort(key=lambda i: i["revenue"], reverse=True)
                declining = top_change is not None and top_change <= -CHANGE_PCT
                findings.append(make_finding(
                    finding_type="product_concentration",
                    severity="high" if declining else "medium",
                    category="opportunity",
                    title=f"Dependencia de un solo producto: {top_prod['sku']}",
                    observation=(
                        f"El producto {top_prod['sku']} concentra el {round(top_prod['revenueShare']*100,1)}% del revenue "
                        f"({top_prod['revenue']:.2f}€). "
                        + (
                            f"Además, su revenue cae {round(top_change*100,1)}% en 30d — el riesgo se está materializando."
                            if declining
                            else "Si pierde demanda, una parte importante de los ingresos queda expuesta."
                        )
                    ),
                    evidence=[
                        f"Revenue {top_prod['revenue']:.2f}€ = {round(top_prod['revenueShare']*100,1)}% del total",
                    ] + (
                        [f"Sustitutos con crecimiento compatible: {', '.join(i['sku'] for i in candidates[:3])}"]
                        if candidates
                        else ["Sin sustitutos con crecimiento compatible en el catálogo todavía"]
                    ),
                    metrics={"sku": top_prod["sku"], "revenue": top_prod["revenue"], "revenueShare": top_prod["revenueShare"], "changePct": round(top_change * 100, 1) if top_change is not None else None, "diversifiers": [i["sku"] for i in candidates[:3]]},
                    period={"current": period["current30d"], "previous": period["previous30d"]},
                    source=["sales_line_items"],
                    confidence="high",
                    estimated_impact={"kind": "estimated", "explanation": "Diversificar la base de revenue reduce el riesgo de dependencia", "revenueAtRisk": round(top_prod["revenue"], 2)},
                    recommended_action=(
                        "El producto dominante está cayendo: investiga la causa y acelera la diversificación del catálogo."
                        if declining
                        else "Prioriza la diversificación: impulsa los sustitutos con crecimiento compatible antes de que el producto dominante pierda demanda."
                    ),
                ))

    # FASE B (anti-inundación): "alto margen pero poco revenue" es ubicuo en
    # catálogos con cola larga (Zipf): casi todo producto de la cola tiene share
    # bajo y margen alto. Solo se retienen las oportunidades de MAYOR VALOR —
    # las realmente accionables — para no convertir el informe en ruido genérico.
    opps = [f for f in findings if f.get("type") == "low_revenue_high_margin"]
    if len(opps) > 8:
        # Ordena por VALOR DE OPORTUNIDAD = beneficio potencial (revenue × margen):
        # un producto con revenue relevante y margen alto (p.ej. 1.600 € al 45%)
        # vale más que uno con margen altísimo pero revenue irrelevante, y no
        # debe quedar oculto tras la cola larga con revenue casi nulo.
        opps.sort(key=lambda f: (f["metrics"].get("revenue") or 0) * (f["metrics"].get("marginPct") or 0), reverse=True)
        keep = {f["id"] for f in opps[:8]}
        findings = [f for f in findings if f.get("type") != "low_revenue_high_margin" or f["id"] in keep]
    return findings


def _emit_margin_findings(findings: list[dict[str, Any]], i: dict[str, Any], avg_margin: float, period: dict[str, Any]) -> None:
    """Hallazgos de margen: solo con coste real del catálogo (nunca se inventa)."""
    # Mucho revenue + poco margen
    if i["revenueShare"] >= HIGH_REV_SHARE and i["marginPct"] <= avg_margin - MARGIN_GAP_POINTS:
        # MEGA UPDATE (A2): impacto económico CUANTIFICADO — cuánto gana la
        # empresa si recupera la mitad del gap de margen (diferencia entre su
        # margen y el promedio) sobre el revenue de la ventana.
        gap_points = max(0.0, avg_margin - i["marginPct"])
        recover = gap_points / 2.0
        margin_potential = round(i["revenue"] * (recover / 100.0), 2) if i["revenue"] > 0 else None
        impact = {
            "kind": "calculated" if margin_potential is not None else "estimated",
            "explanation": (
                f"Subir {recover:.1f} puntos de margen (mitad del gap con el promedio "
                f"{round(avg_margin,1)}%) sobre el revenue de la ventana"
            ),
        }
        if margin_potential is not None:
            impact["marginPotential"] = margin_potential
            impact["economicImpactEuro"] = margin_potential
        findings.append(make_finding(
            finding_type="high_revenue_low_margin",
            severity="high",
            category="problem",
            title=f"{i['sku']} genera mucho revenue con margen bajo",
            observation=(
                f"{i['sku']} representa el {round(i['revenueShare']*100,1)}% del revenue "
                f"({i['revenue']:.2f}€) con un margen del {i['marginPct']}% frente a un "
                f"promedio de empresa del {round(avg_margin,1)}%."
            ),
            evidence=[
                f"Revenue {i['revenue']:.2f}€ = {round(i['revenueShare']*100,1)}% del total",
                f"Margen {i['marginPct']}% vs promedio empresa {round(avg_margin,1)}% (coste del catálogo por SKU)",
            ],
            metrics={"sku": i["sku"], "revenue": i["revenue"], "revenueShare": i["revenueShare"], "marginPct": i["marginPct"], "avgMarginPct": round(avg_margin, 1)},
            period={"current": period["current30d"], "previous": period["previous30d"]},
            source=["sales_line_items", "catalog"],
            confidence="high" if i["revenueShare"] >= 0.2 else "medium",
            estimated_impact=impact,
            recommended_action="Revisa precio o coste; si el coste no puede bajar, úsalo como producto de entrada para cross-selling con mayor margen.",
        ))
    # Poco revenue + alto margen
    elif i["revenueShare"] <= 0.05 and i["marginPct"] >= avg_margin + MARGIN_GAP_POINTS and i["revenue"] >= 100:
        findings.append(make_finding(
            finding_type="low_revenue_high_margin",
            severity="medium",
            category="opportunity",
            title=f"{i['sku']} tiene alto margen pero poco revenue",
            observation=(
                f"{i['sku']} tiene un margen del {i['marginPct']}% ({avg_margin+0:.1f}% promedio) "
                f"pero solo representa el {round(i['revenueShare']*100,1)}% del revenue."
            ),
            evidence=[
                f"Margen {i['marginPct']}% vs promedio {round(avg_margin,1)}%",
                f"Revenue {i['revenue']:.2f}€ = {round(i['revenueShare']*100,1)}% del total",
            ],
            metrics={"sku": i["sku"], "revenue": i["revenue"], "revenueShare": i["revenueShare"], "marginPct": i["marginPct"], "avgMarginPct": round(avg_margin, 1)},
            period={"current": period["current30d"], "previous": period["previous30d"]},
            source=["sales_line_items", "catalog"],
            confidence="medium",
            estimated_impact={"kind": "estimated", "explanation": "Potencial de crecimiento si se promociona", "marginPotential": None},
            recommended_action="Analiza por qué vende poco y si puede crecer con visibilidad o bundle.",
        ))


def detect_cross_selling(sales: list[dict[str, Any]], products: list[dict[str, Any]], quality: dict[str, Any], ref: datetime | None = None) -> list[dict[str, Any]]:
    if quality["ordersTotal"] < MIN_ORDERS_TOTAL:
        return []
    pairs = _cross_sell_pairs(sales, products)
    findings: list[dict[str, Any]] = []
    for pair in pairs[:5]:
        a, b = pair["pair"]
        findings.append(make_finding(
            finding_type="cross_sell",
            severity="medium",
            category="opportunity",
            title=f"Cross-selling: {a} + {b}",
            observation=(
                f"{a} y {b} aparecen juntos en {pair['ordersTogether']} de {pair['ordersWithA']} pedidos "
                f"que contienen {a} ({round(pair['frequency']*100,1)}%)."
            ),
            evidence=[
                f"Co-aparición {pair['ordersTogether']}/{pair['ordersWithA']} pedidos ({round(pair['frequency']*100,1)}%)",
                "Frecuencia ≥ 15% con al menos 10 pedidos base",
            ],
            metrics={"pair": f"{a}+{b}", "ordersTogether": pair["ordersTogether"], "ordersWithA": pair["ordersWithA"], "frequency": pair["frequency"]},
            period={"current": _period_bounds(90, ref)},
            source=["sales_line_items"],
            confidence="medium" if pair["ordersWithA"] >= 15 else "low",
            estimated_impact={"kind": "calculated", "explanation": "Frecuencia y volumen reales de co-compra; el revenue potencial requiere margen por SKU", "ordersPotential": pair["ordersTogether"]},
            recommended_action="Prueba un bundle o una recomendación de producto cruzada durante 14 días.",
        ))
    return findings


def detect_aov(aov: dict[str, Any], quality: dict[str, Any], ref: datetime | None = None, sales: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if quality["ordersTotal"] < MIN_ORDERS_TOTAL or aov["changePct"] is None:
        return []
    if aov["currentOrders"] < MIN_ORDERS_PER_PERIOD or aov["previousOrders"] < MIN_ORDERS_PER_PERIOD:
        return []
    if abs(aov["changePct"]) < AOV_CHANGE_PCT * 100:
        return []
    category = "positive" if aov["changePct"] > 0 else "problem"
    findings = [make_finding(
        finding_type="aov_change",
        severity="low" if aov["changePct"] > 0 else "medium",
        category=category,
        title=("Ticket medio al alza" if aov["changePct"] > 0 else "Ticket medio a la baja"),
        observation=(
            f"El ticket medio pasa de {aov['previousAov']:.2f}€ a {aov['currentAov']:.2f}€ "
            f"({aov['changePct']:+.1f}%) comparando 30 días equivalentes."
        ),
        evidence=[
            f"30d anteriores: {aov['previousAov']:.2f}€ en {aov['previousOrders']} pedidos",
            f"30d actuales: {aov['currentAov']:.2f}€ en {aov['currentOrders']} pedidos",
        ],
        metrics={"currentAov": aov["currentAov"], "previousAov": aov["previousAov"], "changePct": aov["changePct"],
                 "currentOrders": aov.get("currentOrders") or 0, "previousOrders": aov.get("previousOrders") or 0},
        period={"current": _period_bounds(30, ref), "previous": _period_bounds(60, ref)},
        source=["sales"],
        confidence="medium",
        estimated_impact={"kind": "calculated", "explanation": "Impacto directo por pedido (diferencia de AOV)"} if aov["changePct"] > 0 else {"kind": "estimated", "explanation": "Recuperar el ticket medio requiere acciones comerciales"},
        recommended_action="Refuerza el cross-selling y los bundles para subir el ticket." if aov["changePct"] <= 0 else "Mantén las palancas que están subiendo el ticket.",
    )]
    # PRODUCT LEAP — razonar la CAUSA del AOV a la baja solo con evidencia:
    # si además de caer el ticket caen los pedidos multiproducto, hay una
    # palanca concreta (bundle/cross-sell). Si no cae la parte multiproducto,
    # NO se afirma causalidad: el AOV a la baja se queda como problema sin
    # palanca demostrada (UNKNOWN ≠ 0, no inventar).
    if aov["changePct"] <= -AOV_CHANGE_PCT * 100 and ref is not None and sales:
        now_d = ref.date()
        cur_from = now_d - timedelta(days=30)
        prev_to = cur_from - timedelta(days=1)
        prev_from = cur_from - timedelta(days=30)
        cur_multi = _multi_item_share(sales, cur_from, now_d)
        prev_multi = _multi_item_share(sales, prev_from, prev_to)
        if (
            cur_multi is not None and prev_multi is not None
            and prev_multi - cur_multi >= AOV_MULTI_ITEM_DROP_PP
        ):
            findings.append(make_finding(
                finding_type="aov_multi_item_opportunity",
                severity="medium",
                category="opportunity",
                title="El ticket baja y los pedidos multiproducto caen",
                observation=(
                    f"El ticket medio cae {aov['changePct']:+.1f}% y los pedidos con 2+ "
                    f"productos pasan del {prev_multi:.1f}% al {cur_multi:.1f}% de los pedidos "
                    f"(-{prev_multi - cur_multi:.1f} puntos). La caída del ticket tiene una "
                    "causa concreta: se venden menos artículos por pedido."
                ),
                evidence=[
                    f"Pedidos multiproducto: {prev_multi:.1f}% → {cur_multi:.1f}% (30d equivalentes)",
                    f"Ticket medio: {aov['previousAov']:.2f}€ → {aov['currentAov']:.2f}€ ({aov['changePct']:+.1f}%)",
                ],
                metrics={"multiItemSharePrev": prev_multi, "multiItemShareNow": cur_multi, "changePct": aov["changePct"], "currentAov": aov["currentAov"], "previousAov": aov["previousAov"]},
                period={"current": _period_bounds(30, ref), "previous": _period_bounds(60, ref)},
                source=["sales", "sales_line_items"],
                confidence="medium",
                estimated_impact={"kind": "estimated", "explanation": "Recuperar el número de artículos por pedido subiría el ticket (potencial = diferencia de AOV por pedido)"},
                recommended_action="Prueba un bundle o recomendación cruzada durante 14 días y mide el AOV y la proporción multiproducto.",
            ))
    return findings


def detect_expenses(exp: dict[str, Any], quality: dict[str, Any]) -> list[dict[str, Any]]:
    if not quality["canAnalyzeExpenses"] or exp["growthPct"] is None:
        return []
    findings: list[dict[str, Any]] = []
    if exp["growthPct"] >= EXPENSE_GROWTH_PCT * 100 and exp["currentTotal"] is not None and exp["previousTotal"] is not None:
        findings.append(make_finding(
            finding_type="expenses_growing",
            severity="medium",
            category="problem",
            title="Gastos en crecimiento",
            observation=(
                f"Los gastos (facturas recibidas) pasan de {exp['previousTotal']:.2f}€ a "
                f"{exp['currentTotal']:.2f}€ ({exp['growthPct']:+.1f}%) entre {exp['previousMonth']} y {exp['currentMonth']}."
            ),
            evidence=[f"{exp['previousMonth']}: {exp['previousTotal']:.2f}€", f"{exp['currentMonth']}: {exp['currentTotal']:.2f}€"],
            metrics={"currentTotal": exp["currentTotal"], "previousTotal": exp["previousTotal"], "growthPct": exp["growthPct"], "scope": "gastos"},
            period={"current": exp["currentMonth"], "previous": exp["previousMonth"]},
            source=["facturas_recibidas"],
            confidence="medium",
            estimated_impact={"kind": "estimated", "explanation": "Contener el crecimiento de gasto", "savingPotential": None},
            recommended_action="Revisa las partidas de gasto del mes y negocia con los proveedores de mayor aumento.",
        ))
    return findings


def detect_treasury(tm: dict[str, Any], quality: dict[str, Any], ref: datetime | None = None) -> list[dict[str, Any]]:
    if not quality["canAnalyzeTreasury"]:
        return []
    findings: list[dict[str, Any]] = []
    if tm["upcomingDuePaymentsTotal"] > 0 and tm["collectionsTotal"] > 0 and tm["upcomingVsCollectionsPct"] is not None and tm["upcomingVsCollectionsPct"] >= 50:
        findings.append(make_finding(
            finding_type="upcoming_payments_concentration",
            severity="medium",
            category="problem",
            title="Concentración de pagos próximos",
            observation=(
                f"{tm['upcomingDuePaymentsTotal']:.2f}€ en pagos vencen en los próximos 30 días "
                f"({tm['upcomingDuePaymentsCount']} facturas recibidas), lo que equivale al "
                f"{tm['upcomingVsCollectionsPct']}% de los cobros del período."
            ),
            evidence=[
                f"Vencimientos 30d: {tm['upcomingDuePaymentsTotal']:.2f}€ ({tm['upcomingDuePaymentsCount']} facturas)",
                f"Cobros del período: {tm['collectionsTotal']:.2f}€",
                "NO se puede afirmar tensión de liquidez: no hay saldo bancario real.",
            ],
            metrics={"upcomingDuePaymentsTotal": tm["upcomingDuePaymentsTotal"], "collectionsTotal": tm["collectionsTotal"], "ratioPct": tm["upcomingVsCollectionsPct"], "scope": "tesorería"},
            period={"current": _period_bounds(30, ref)},
            source=["facturas_recibidas", "cobros"],
            confidence="high",
            estimated_impact={"kind": "calculated", "explanation": "Importe real de pagos que vencen; el efecto sobre liquidez no es evaluable sin saldo bancario", "cashRequired": tm["upcomingDuePaymentsTotal"]},
            recommended_action="Prioriza los cobros pendientes y negocia el calendario de pagos si hay concentración.",
        ))
    return findings


# ---------------------------------------------------------------------------
# FASE B — detectores de señales empresariales (inventario, clientes,
# proveedores, gastos recurrentes). Consumen business_signals y respetan la
# regla UNKNOWN ≠ 0: sin dato (stock/coste/histórico) → INSUFFICIENT_EVIDENCE,
# jamás un hallazgo inventado.
# ---------------------------------------------------------------------------

# Umbrales (documentados — reglas de evidencia)
STOCKOUT_DAYS = 14            # días de stock por debajo = riesgo de rotura
OVERSTOCK_DAYS = 180          # días de stock por encima = exceso
DEAD_STOCK_MIN_VALUE = 5000.0 # valor de inventario parado mínimo (€) — solo los grandes
DEAD_STOCK_MAX_VELOCITY = 0.01  # velocidad de venta ≈ 0 (uds/día)
STOCK_FINDING_CAP = 6         # máximo de hallazgos de stock por tipo (los de mayor valor)
OVERSTOCK_FINDING_CAP = 8     # máximo de hallazgos de exceso de stock (por valor de inventario)
SUPPLIER_DEPENDENCY_SHARE = 0.40   # un proveedor > 40% del gasto
SUPPLIER_SKU_DEPENDENCY_SHARE = 0.40  # un proveedor suministra > 40% de los SKUs comprados
SUPPLIER_SKU_DEPENDENCY_MIN = 5        # y al menos 5 SKUs distintos (evita ruido con pocas líneas)
SUPPLIER_PRICE_INCREASE = 0.20     # +20% de precio unitario
CUSTOMER_CONCENTRATION_SHARE = 0.30  # un cliente > 30% del revenue
CUSTOMER_CHURN_LAST_ORDER_DAYS = 60  # sin comprar hace 60 días
CUSTOMER_CHURN_MIN_ORDERS = 2        # era un cliente recurrente
CUSTOMER_CHURN_MIN_REVENUE = 200.0   # y tenía valor
CUSTOMER_CHURN_CAP = 8               # máximo de clientes en declive (por revenue)
CUSTOMER_NO_ORDERS_CAP = 8           # máximo de clientes sin ningún pedido (por potencial)
# PRODUCT LEAP — Opportunity Engine (evidencia mínima real, nunca umbrales
# inventados): declive de clientes de alto valor, reactivación agregada,
# concentración de producto razonada y causa multiproducto del AOV.
CUSTOMER_DECLINE_MIN_REVENUE = 500.0    # cliente de alto valor
CUSTOMER_DECLINE_MIN_ORDERS = 2         # recurrente (no un comprador puntual)
CUSTOMER_DECLINE_TREND_PCT = -50.0      # caída >= 50% en revenue 30d vs 30d previos
REACTIVATION_MIN_ORDERS = 2             # era recurrente
REACTIVATION_MIN_REVENUE = 300.0        # con valor histórico
REACTIVATION_LAST_ORDER_DAYS = 60       # inactivo hace 60+ días
REACTIVATION_MIN_CUSTOMERS = 3          # al menos 3 clientes recuperables
REACTIVATION_MIN_COMBINED = 1000.0      # y valor conjunto >= 1.000 €
PRODUCT_CONCENTRATION_SHARE = 0.25      # un producto > 25% del revenue
PRODUCT_CONCENTRATION_MIN_REVENUE = 500.0
AOV_MULTI_ITEM_DROP_PP = 5.0            # caída >= 5 puntos porcentuales en pedidos multiproducto
EXPENSE_GROUP_GROWTH = 0.20         # gasto recurrente +20%
EXPENSE_GROUP_MIN_ROWS = 3          # pagos mínimos para serie recurrente


def _norm_text(value: Any) -> str:
    import re as _re

    return _re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _customers_without_orders(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Clientes del fichero de clientes sin NINGÚN pedido en las ventas."""
    customers = [c for c in (data.get("organizedCustomers") or []) if isinstance(c, dict)]
    sales = [s for s in (data.get("organizedSales") or []) if isinstance(s, dict)]
    if not customers:
        return []
    buyer_names = {_norm_text(s.get("customer")) for s in sales}
    buyer_emails = {_norm_text(s.get("customerEmail")) for s in sales}

    out: list[dict[str, Any]] = []
    for c in customers:
        name = _norm_text(c.get("name"))
        email = _norm_text(c.get("email"))
        if not name and not email:
            continue
        if name in buyer_names or email in buyer_emails:
            continue
        # Un cliente derivado de una venta (sin fichero previo) no cuenta:
        # solo los que vienen del fichero de clientes con 0 pedidos.
        if str(c.get("source") or "").lower() in ("excel", "file", "import", "csv") or c.get("sourceFile"):
            out.append({"name": c.get("name") or email, "id": c.get("id") or ""})
    # Prioriza por orden de fichero; sin revenue no hay más señal de valor.
    return out[:CUSTOMER_NO_ORDERS_CAP]


def detect_data_quality(data: dict[str, Any], ref: datetime | None = None) -> list[dict[str, Any]]:
    """FASE C (B8) — detectores de CALIDAD DE DATOS que convierten anomalías
    PRESERVADAS (nunca borradas) en findings con evidencia:
      duplicate_sku / missing_sku / duplicate_customer / missing_cost /
      inconsistent_order_total. UNKNOWN ≠ 0: solo se emiten con registro real."""
    import re as _re

    findings: list[dict[str, Any]] = []
    products = [p for p in (data.get("organizedProducts") or []) if isinstance(p, dict)]
    customers = [c for c in (data.get("organizedCustomers") or []) if isinstance(c, dict)]
    sales = [s for s in (data.get("organizedSales") or []) if isinstance(s, dict)]

    # Duplicate SKU
    by_sku: dict[str, list[dict[str, Any]]] = {}
    for p in products:
        sku = str(p.get("sku") or "").strip().lower()
        if sku:
            by_sku.setdefault(sku, []).append(p)
    dup_skus = [sku for sku, rows in by_sku.items() if len(rows) > 1]
    for sku in dup_skus[:5]:
        rows = by_sku[sku]
        findings.append(make_finding(
            finding_type="duplicate_sku",
            severity="medium",
            category="problem",
            title=f"SKU duplicado: {sku}",
            observation=(
                f"El SKU '{sku}' aparece en {len(rows)} registros del catálogo "
                f"({', '.join(str(r.get('name') or '')[:24] for r in rows)}). "
                "Ambos se han conservado y marcado NEEDS_REVIEW."
            ),
            evidence=[f"{len(rows)} registros comparten el SKU '{sku}'", "Registros preservados (no borrados)"],
            metrics={"scope": "product", "sku": sku, "records": len(rows)},
            period={"current": _period_bounds(30, ref)},
            source=["catalog"],
            confidence="high",
            estimated_impact={"kind": "estimated", "explanation": "El coste/margen de este SKU no es fiable hasta consolidar", "records": len(rows)},
            recommended_action="Revisa y consolida los registros del SKU antes de usar su coste o margen para decisiones.",
        ))

    # Missing SKU
    missing_sku = [p for p in products if not str(p.get("sku") or "").strip()]
    if missing_sku:
        findings.append(make_finding(
            finding_type="missing_sku",
            severity="medium",
            category="problem",
            title="Productos sin referencia (SKU)",
            observation=(
                f"{len(missing_sku)} producto(s) del catálogo no tienen SKU "
                f"({', '.join(str(p.get('name') or '')[:24] for p in missing_sku[:3])}...). "
                "Sin referencia no se pueden reconciliar con ventas ni costes."
            ),
            evidence=[f"{len(missing_sku)} registros sin SKU", "Registros preservados (no borrados)"],
            metrics={"scope": "product", "count": len(missing_sku), "skus": [str(p.get("name") or "") for p in missing_sku[:5]]},
            period={"current": _period_bounds(30, ref)},
            source=["catalog"],
            confidence="high",
            estimated_impact={"kind": "estimated", "explanation": "Ventas y costes de estos productos no son trazables", "count": len(missing_sku)},
            recommended_action="Asigna una referencia a cada producto o corrígelo en el sistema de origen.",
        ))

    # Duplicate customer identity (email/NIF)
    by_email: dict[str, list[dict[str, Any]]] = {}
    for c in customers:
        email = str(c.get("email") or "").strip().lower()
        if email:
            by_email.setdefault(email, []).append(c)
    dup_emails = sorted([em for em, rows in by_email.items() if len(rows) > 1])[:5]
    for em in dup_emails:
        rows = by_email[em]
        findings.append(make_finding(
            finding_type="duplicate_customer",
            severity="medium",
            category="problem",
            title=f"Cliente duplicado: {em}",
            observation=(
                f"{len(rows)} clientes comparten el email '{em}' "
                f"({', '.join(str(r.get('name') or '')[:24] for r in rows)}). "
                "Ambos se han conservado y marcado NEEDS_REVIEW."
            ),
            evidence=[f"{len(rows)} registros comparten identidad", "Registros preservados (no borrados)"],
            metrics={"scope": "customer", "email": em, "records": len(rows)},
            period={"current": _period_bounds(30, ref)},
            source=["customers"],
            confidence="high",
            estimated_impact={"kind": "estimated", "explanation": "Revenue y deuda pueden estar divididos entre dos registros", "records": len(rows)},
            recommended_action="Consolida los registros duplicados antes de analizar clientes.",
        ))

    # Missing cost (products whose margin cannot be calculated)
    from . import product_identity as _pi
    missing_cost = [p for p in products if _pi.resolve_cost(p).get("costStatus") == "missing"]
    if missing_cost:
        findings.append(make_finding(
            finding_type="missing_cost",
            severity="high" if len(missing_cost) >= 5 else "medium",
            category="problem",
            title="Productos sin coste verificable",
            observation=(
                f"{len(missing_cost)} producto(s) del catálogo no tienen coste de adquisición "
                f"verificable ({', '.join(str(p.get('name') or '')[:20] for p in missing_cost[:4])}...). "
                "Consecuencia empresarial: VANOVA no puede calcular el margen de estos productos "
                "y, por tanto, no puede determinar con confianza cuáles son realmente rentables "
                "(UNKNOWN, no 0). Cualquier decisión de pricing o de catálogo basada en margen "
                "queda sin evidencia para esta parte de la cartera."
            ),
            evidence=[f"{len(missing_cost)} productos con costStatus=missing", "Coste == PVD sin evidencia no cuenta como coste", "El margen de estos productos no es calculable (UNKNOWN, no 0)"],
            metrics={"scope": "product", "count": len(missing_cost), "skus": [str(p.get("name") or "") for p in missing_cost[:5]]},
            period={"current": _period_bounds(30, ref)},
            source=["catalog"],
            confidence="high",
            estimated_impact={"kind": "estimated", "explanation": "Sin coste no hay margen: impide saber qué productos son rentables y tomar decisiones de pricing", "count": len(missing_cost)},
            recommended_action="Importa el coste real de estos productos (CSV de costes, proveedor o ERP) antes de decidir por margen; VANOVA puede prepararte la plantilla.",
        ))

    # Inconsistent order totals (line items vs total)
    mismatches: list[dict[str, Any]] = []
    for s in sales:
        lines = s.get("line_items")
        if not isinstance(lines, list) or not lines:
            continue
        total = business_model._as_float(s.get("total"))
        line_total = 0.0
        for li in lines:
            if not isinstance(li, dict):
                continue
            price = business_model._as_float(li.get("price"))
            qty = business_model._as_float(li.get("quantity")) or 1.0
            if price is not None:
                line_total += price * qty
        if total is not None and abs(total - line_total) > max(0.5, abs(total) * 0.02):
            mismatches.append({"id": s.get("id") or s.get("order_id") or "?", "total": total, "lineTotal": round(line_total, 2), "delta": abs(total - line_total)})
    # Prioriza por magnitud de desvío (no por orden de lista): los desvíos
    # mayores —y los negativos, líneas > total— se muestran primero.
    mismatches.sort(key=lambda m: m.get("delta") or 0.0, reverse=True)
    for m in mismatches[:5]:
        findings.append(make_finding(
            finding_type="inconsistent_order_total",
            severity="medium",
            category="problem",
            title=f"Pedido con total incoherente: {m['id']}",
            observation=(
                f"El pedido {m['id']} registra un total de {m['total']:.2f}€ pero sus líneas "
                f"suman {m['lineTotal']:.2f}€. Los importes no cuadran. El desvío puede "
                "corresponder a envío/impuestos/descuentos no desglosados en las líneas."
            ),
            evidence=[f"Total {m['total']:.2f}€ vs líneas {m['lineTotal']:.2f}€", "Registro preservado (no borrado)"],
            metrics={"scope": "order", "orderId": m["id"], "total": m["total"], "lineTotal": m["lineTotal"]},
            period={"current": _period_bounds(30, ref)},
            source=["sales"],
            confidence="high",
            estimated_impact={"kind": "estimated", "explanation": "Revenue y márgenes derivados de este pedido no son fiables"},
            recommended_action="Revisa el pedido en el sistema de origen y corrige el total o las líneas.",
        ))
    return findings


def _recurring_key(ref: str) -> str:
    """Normaliza una referencia recurrente a su base estable: 'rent-01' → 'rent',
    'services-01' → 'services', 'payment-RCV-0001' → 'payment-rcv'."""
    import re as _re

    s = (ref or "").strip().lower()
    s = _re.sub(r"[-_\s\d]+$", "", s)
    return s.strip("-_").strip() or (ref or "").strip().lower()


def detect_inventory(prod: list[dict[str, Any]], ref: datetime | None = None) -> list[dict[str, Any]]:
    """Riesgo de stockout, exceso de stock y dead stock a partir de stock real
    + velocidad de venta. Solo emite si hay stock (hasStock). Se emiten los de
    MAYOR impacto (valor de inventario) para no inundar con cola larga."""
    dead: list[dict[str, Any]] = []
    over: list[dict[str, Any]] = []
    stockout: list[dict[str, Any]] = []
    for p in prod:
        if not p.get("hasStock"):
            continue
        sku = p["sku"]
        stock = p["stock"]
        vel = p["velocityPerDay"]
        days = p["daysOfStock"]
        inv_value = p["inventoryValue"] or 0.0
        # Dead stock: stock relevante y velocidad ≈ 0 (lleva meses sin venderse)
        if stock is not None and stock > 0 and vel is not None and vel <= DEAD_STOCK_MAX_VELOCITY and inv_value >= DEAD_STOCK_MIN_VALUE:
            dead.append(make_finding(
                finding_type="dead_stock",
                severity="medium",
                category="problem",
                title=f"{sku} es stock muerto (sin ventas)",
                observation=(
                    f"{sku} tiene {stock:g} unidades en stock (valor {inv_value:.2f} €) "
                    f"y velocidad de venta ≈ 0 en el histórico — capital inmovilizado sin rotación."
                ),
                evidence=[
                    f"Stock actual {stock:g} uds",
                    f"Valor de inventario {inv_value:.2f} € (stock × coste)",
                    f"Velocidad de venta {vel:.3f} uds/día (≈ 0)",
                ],
                metrics={"sku": sku, "stock": stock, "inventoryValue": inv_value, "velocityPerDay": vel},
                period={"current": _period_bounds(30, ref)},
                source=["catalog", "sales_line_items"],
                confidence="high" if vel == 0 else "medium",
                estimated_impact={"kind": "calculated", "explanation": "Capital inmovilizado en stock sin rotación", "inventoryValue": inv_value},
                recommended_action="Liquida o renegocia este stock para liberar caja; revisa por qué dejó de venderse.",
            ))
            continue
        # Stockout: stock agotado (0) o pocos días de cobertura con rotación real
        if stock is not None and vel > 0 and ((stock <= 0) or (days is not None and days <= STOCKOUT_DAYS)):
            already_out = stock <= 0
            # MEGA UPDATE (A2): impacto € de la rotura = revenue de la ventana
            # 30d × fracción de días sin cobertura (o 100% si ya está a 0).
            revenue30 = p.get("revenue30d") or 0.0
            lost_share = 1.0 if already_out else ((STOCKOUT_DAYS - (days or 0)) / STOCKOUT_DAYS) if (days or 0) < STOCKOUT_DAYS else 0.0
            lost_revenue = round(revenue30 * max(0.0, min(1.0, lost_share)), 2)
            stockout.append(make_finding(
                finding_type="stockout_risk",
                severity="high" if (already_out or (days is not None and days <= 7)) else "medium",
                category="problem",
                title=f"{sku} en riesgo de rotura de stock",
                observation=(
                    f"{sku} tiene {stock:g} unidades (≈{days} días de stock al ritmo actual de "
                    f"{vel:.2f} uds/día). Riesgo de quedarse sin stock."
                ),
                evidence=[
                    f"Stock actual {stock:g} uds",
                    f"Velocidad de venta {vel:.2f} uds/día",
                    f"Días de cobertura estimados: {days} (umbral {STOCKOUT_DAYS})",
                ],
                metrics={"sku": sku, "stock": stock, "velocityPerDay": round(vel, 3), "daysOfStock": days, "revenue30d": revenue30, "lostRevenueEstimate": lost_revenue},
                period={"current": _period_bounds(30, ref)},
                source=["catalog", "sales_line_items"],
                confidence="high",
                estimated_impact={
                    "kind": "estimated",
                    "explanation": "Venta perdida estimada por rotura de stock (revenue 30d × días sin cobertura)",
                    "marginPotential": lost_revenue,
                    "economicImpactEuro": lost_revenue,
                },
                recommended_action="Repón este producto con urgencia y revisa el punto de pedido.",
            ))
        # Overstock: cobertura muy larga con rotación real y valor relevante
        if days is not None and days >= OVERSTOCK_DAYS and inv_value >= DEAD_STOCK_MIN_VALUE:
            over.append(make_finding(
                finding_type="overstock",
                severity="medium",
                category="problem",
                title=f"{sku} tiene exceso de stock",
                observation=(
                    f"{sku} tiene {stock:g} unidades (≈{days} días de cobertura, valor {inv_value:.2f} €) "
                    f"frente a una venta de {vel:.2f} uds/día — capital inmovilizado."
                ),
                evidence=[
                    f"Stock actual {stock:g} uds",
                    f"Días de cobertura estimados: {days} (umbral {OVERSTOCK_DAYS})",
                    f"Valor de inventario {inv_value:.2f} €",
                ],
                metrics={"sku": sku, "stock": stock, "velocityPerDay": round(vel, 3), "daysOfStock": days, "inventoryValue": inv_value},
                period={"current": _period_bounds(30, ref)},
                source=["catalog", "sales_line_items"],
                confidence="high" if days >= 365 else "medium",
                estimated_impact={"kind": "calculated", "explanation": "Capital inmovilizado en exceso de stock", "inventoryValue": inv_value},
                recommended_action="Reduce compras de este SKU y promociónalo para rotar el excedente.",
            ))
    dead.sort(key=lambda f: f["estimatedImpact"].get("inventoryValue") or 0, reverse=True)
    over.sort(key=lambda f: f["estimatedImpact"].get("inventoryValue") or 0, reverse=True)
    stockout.sort(key=lambda f: f["metrics"].get("velocityPerDay") or 0, reverse=True)
    return stockout[:STOCK_FINDING_CAP] + over[:OVERSTOCK_FINDING_CAP] + dead[:STOCK_FINDING_CAP]


def detect_customers(cust: list[dict[str, Any]], data: dict[str, Any] | None = None, ref: datetime | None = None) -> list[dict[str, Any]]:
    """Concentración de revenue, churn, clientes sin pedidos y cliente de alto
    valor con margen bajo."""
    if data is None:
        data = {}
    _no_orders_data = data
    findings: list[dict[str, Any]] = []
    if not cust:
        return findings
    # Concentración: el mayor cliente acapara demasiado revenue
    top = cust[0]
    if top["revenueShare"] >= CUSTOMER_CONCENTRATION_SHARE:
        findings.append(make_finding(
            finding_type="customer_concentration",
            severity="medium",
            category="problem",
            title=f"Concentración de ventas en un cliente",
            observation=(
                f"El cliente {top['name']} concentra el {round(top['revenueShare']*100,1)}% del revenue "
                f"({top['revenue']:.2f} €) — dependencia excesiva de un solo cliente."
            ),
            evidence=[
                f"Revenue {top['revenue']:.2f} € = {round(top['revenueShare']*100,1)}% del total",
                f"{top['orders']} pedidos",
            ],
            metrics={"scope": "customer", "customer": top["name"], "revenue": top["revenue"], "revenueShare": top["revenueShare"]},
            period={"current": _period_bounds(90, ref)},
            source=["sales"],
            confidence="high",
            estimated_impact={"kind": "estimated", "explanation": "Riesgo si el cliente se va", "revenueAtRisk": top["revenue"]},
            recommended_action="Diversifica la base de clientes y protege la relación con este cliente clave.",
        ))
    # Churn: clientes recurrentes que dejaron de comprar (recencia, no ventana ruidosa)
    churn: list[dict[str, Any]] = []
    for c in cust:
        if c.get("orders", 0) < CUSTOMER_CHURN_MIN_ORDERS or c.get("revenue", 0) < CUSTOMER_CHURN_MIN_REVENUE:
            continue
        days_since = c.get("daysSinceLastOrder")
        if days_since is None:
            continue
        # Fecha relativa a los datos: sin comprar en los últimos N días
        if days_since >= CUSTOMER_CHURN_LAST_ORDER_DAYS:
            # MEGA UPDATE (A2): impacto € = revenue del cliente anualizado
            # (ventana del histórico) en riesgo si no se reactiva.
            churn_impact = round(c.get("revenue") or 0.0, 2)
            churn.append(make_finding(
                finding_type="customer_churn",
                severity="medium" if churn_impact >= 1000 else "low",
                category="problem",
                title=f"Cliente inactivo: {c['name']}",
                observation=(
                    f"{c['name']} hizo {c['orders']} pedidos ({c['revenue']:.2f} €) pero su última compra "
                    f"fue hace {days_since} días — cliente recurrente que dejó de comprar."
                ),
                evidence=[
                    f"Revenue histórico {c['revenue']:.2f} € en {c['orders']} pedidos",
                    f"Última compra {c['lastOrder'][:10]} (hace {days_since} días)",
                ],
                metrics={"scope": "customer", "customer": c["name"], "revenue": c["revenue"], "orders": c["orders"], "lastOrder": c["lastOrder"], "revenueAtRisk": churn_impact},
                period={"current": _period_bounds(30, ref)},
                source=["sales"],
                confidence="medium",
                estimated_impact={"kind": "estimated", "explanation": "Revenue en riesgo por cliente inactivo (histórico del cliente)", "revenueAtRisk": churn_impact, "economicImpactEuro": churn_impact},
                recommended_action="Reactiva a este cliente con una campaña de retención; averigua por qué dejó de comprar.",
            ))
    churn.sort(key=lambda f: f["estimatedImpact"].get("revenueAtRisk") or 0, reverse=True)
    findings += churn[:CUSTOMER_CHURN_CAP]
    # Clientes en el fichero de clientes SIN ningún pedido registrado: un CRM
    # con contactos que nunca compraron es señal de listas frías / oportunidad
    # de activación, y un cliente que dejó de comprar del todo no sale en las
    # ventas. UNKNOWN ≠ 0: solo se emite cuando el fichero de clientes existe
    # y el pedido no aparece en ninguna venta.
    for c in _customers_without_orders(_no_orders_data):
        findings.append(make_finding(
            finding_type="customer_no_orders",
            severity="low",
            category="problem",
            title=f"Cliente sin pedidos: {c['name']}",
            observation=(
                f"{c['name']} figura en el fichero de clientes pero no tiene NINGÚN pedido "
                f"registrado en las ventas — lista fría o contacto por activar."
            ),
            evidence=[
                "Presente en el fichero de clientes (CRM/exportación)",
                "0 pedidos en las ventas registradas",
            ],
            metrics={"scope": "customer", "customer": c["name"], "orders": 0},
            period={"current": _period_bounds(90, ref)},
            source=["customers", "sales"],
            confidence="medium",
            estimated_impact={"kind": "estimated", "explanation": "Potencial de venta sin explotar", "revenueAtRisk": None},
            recommended_action="Verifica si este cliente debería estar comprando; actívalo con una campaña o limpia el registro si es un error.",
        ))
    # Alto valor + margen bajo (cliente que compra mucho pero deja poco).
    # FASE C (B7): este bloque estaba tras un `return` anterior (código muerto);
    # se emite SOLO con margen estimado real (nunca con UNKNOWN → 0).
    low_margin: list[dict[str, Any]] = []
    for c in cust[:25]:
        if c.get("marginPct") is None or c["revenue"] < 500 or c["orders"] < 2:
            continue
        if c["marginPct"] <= 15:
            low_margin.append(make_finding(
                finding_type="customer_low_margin",
                severity="medium",
                category="problem",
                title=f"Cliente de alto revenue con margen bajo: {c['name']}",
                observation=(
                    f"{c['name']} compra {c['revenue']:.2f} € en {c['orders']} pedidos pero con margen "
                    f"estimado del {c['marginPct']}% — revisa precios/descuentos a este cliente."
                ),
                evidence=[
                    f"Revenue {c['revenue']:.2f} € en {c['orders']} pedidos",
                    f"Margen estimado {c['marginPct']}% (coste de las líneas compradas)",
                ],
                metrics={"scope": "customer", "customer": c["name"], "revenue": c["revenue"], "marginPct": c["marginPct"]},
                period={"current": _period_bounds(90, ref)},
                source=["sales", "catalog"],
                confidence="medium",
                estimated_impact={"kind": "estimated", "explanation": "Margen no capturado en un cliente grande"},
                recommended_action="Revisa las condiciones/precios de este cliente; considera subir precio o reducir descuento.",
            ))
    low_margin.sort(key=lambda f: f["metrics"].get("revenue") or 0, reverse=True)
    # PRODUCT LEAP — cliente de ALTO VALOR cuyo comportamiento empeora: su
    # revenue 30d cae >=50% vs los 30d anteriores. Señal temprana de pérdida
    # (antes del churn total). Solo con revenue y pedidos reales.
    declining: list[dict[str, Any]] = []
    for c in cust[:25]:
        if c.get("revenue", 0) < CUSTOMER_DECLINE_MIN_REVENUE or c.get("orders", 0) < CUSTOMER_DECLINE_MIN_ORDERS:
            continue
        trend = c.get("trendPct")
        if trend is None or trend > CUSTOMER_DECLINE_TREND_PCT:
            continue
        declining.append(make_finding(
            finding_type="customer_declining",
            severity="medium" if c["revenue"] >= 2000 else "low",
            category="problem",
            title=f"Cliente de alto valor en declive: {c['name']}",
            observation=(
                f"{c['name']} (histórico {c['revenue']:.2f}€ en {c['orders']} pedidos) reduce su "
                f"compra un {round(-trend,1)}% en los últimos 30 días frente a los 30 anteriores. "
                "Es una señal temprana: aún no ha dejado de comprar del todo."
            ),
            evidence=[
                f"Revenue 30d actuales vs 30d previos: {trend:+.1f}%",
                f"Pedidos 30d actuales: {c.get('orders30d', 0)}",
            ],
            metrics={"scope": "customer", "customer": c["name"], "revenue": c["revenue"], "trendPct": trend, "orders": c["orders"], "orders30d": c.get("orders30d", 0)},
            period={"current": _period_bounds(30, ref), "previous": _period_bounds(60, ref)},
            source=["sales"],
            confidence="medium",
            estimated_impact={"kind": "estimated", "explanation": "Pérdida parcial del valor histórico del cliente", "revenueAtRisk": round(c["revenue"] * 0.5, 2)},
            recommended_action="Contacta a este cliente antes de que deje de comprar; revisa pedidos recientes y posibles fricciones.",
        ))
    declining.sort(key=lambda f: (f["metrics"].get("revenue") or 0), reverse=True)
    findings += declining[:3]
    # PRODUCT LEAP — REACTIVACIÓN agregada (oportunidad): varios clientes de
    # alto valor llevan 60+ días sin comprar. Es una oportunidad concreta de
    # recuperar revenue con una campaña segmentada. Se emite UN SOLO finding
    # agregado (anti-spam) y solo cuando hay masa crítica real.
    candidates = [
        c for c in cust
        if c.get("orders", 0) >= REACTIVATION_MIN_ORDERS
        and c.get("revenue", 0) >= REACTIVATION_MIN_REVENUE
        and (c.get("daysSinceLastOrder") or 0) >= REACTIVATION_LAST_ORDER_DAYS
    ]
    candidates.sort(key=lambda c: c.get("revenue") or 0, reverse=True)
    combined = sum(c.get("revenue") or 0.0 for c in candidates)
    if len(candidates) >= REACTIVATION_MIN_CUSTOMERS and combined >= REACTIVATION_MIN_COMBINED:
        names = ", ".join(c["name"] for c in candidates[:3])
        findings.append(make_finding(
            finding_type="customer_reactivation",
            severity="medium" if combined >= 3000 else "low",
            category="opportunity",
            title="Oportunidad: clientes de alto valor inactivos",
            observation=(
                f"{len(candidates)} clientes con historial de compra recurrente llevan "
                f"{REACTIVATION_LAST_ORDER_DAYS}+ días sin comprar. Su valor histórico "
                f"conjunto es {combined:.2f}€ — es la oportunidad de reactivación "
                "con mayor retorno potencial."
            ),
            evidence=[
                f"{len(candidates)} clientes con >= {REACTIVATION_MIN_ORDERS} pedidos e inactivos {REACTIVATION_LAST_ORDER_DAYS}+ días",
                f"Valor histórico conjunto {combined:.2f}€ (top: {names})",
            ],
            metrics={"scope": "customer", "count": len(candidates), "combinedRevenue": round(combined, 2), "top": [c["name"] for c in candidates[:5]], "lastOrderDays": REACTIVATION_LAST_ORDER_DAYS},
            period={"current": _period_bounds(30, ref)},
            source=["sales"],
            confidence="medium",
            estimated_impact={"kind": "estimated", "explanation": "Recuperar una fracción del valor histórico de clientes inactivos", "revenueAtRisk": round(combined, 2)},
            recommended_action="Prepara una campaña de reactivación segmentada por valor histórico (los 5 con mayor revenue primero).",
        ))
    return findings + low_margin[:3]


def detect_suppliers(supp: list[dict[str, Any]], supp_price: list[dict[str, Any]], supp_skus: list[dict[str, Any]] | None = None, ref: datetime | None = None) -> list[dict[str, Any]]:
    """Dependencia de proveedor (por gasto Y por nº de SKUs suministrados) y
    encarecimiento de precios de compra. MEGA UPDATE (A1): la dependencia no
    solo se mide por concentración de gasto — un proveedor que suministra la
    mayoría de los SKUs del catálogo también crea dependencia, aunque su
    gasto sea bajo. UNKNOWN ≠ 0: sin señal de SKUs no se emite dependencia
    por SKU."""
    findings: list[dict[str, Any]] = []
    seen_dependency: set[str] = set()

    # Dependencia por nº de SKUs (trazabilidad proveedor→producto→SKU).
    for s in supp_skus or []:
        sku_share = s.get("skuShare") or 0.0
        sku_count = s.get("skuCount") or 0
        if sku_share < SUPPLIER_SKU_DEPENDENCY_SHARE or sku_count < SUPPLIER_SKU_DEPENDENCY_MIN:
            continue
        seen_dependency.add(str(s.get("name") or s.get("id") or ""))
        findings.append(make_finding(
            finding_type="supplier_dependency",
            severity="high" if sku_share >= 0.6 else "medium",
            category="problem",
            title=f"Dependencia del proveedor {s['name']} por catálogo",
            observation=(
                f"{s['name']} suministra {sku_count} de los {s.get('totalTrackedSkus')} SKUs "
                f"distintos comprados ({round(sku_share*100,1)}% del catálogo de compra) — "
                "dependencia por cobertura de producto, no solo por gasto."
            ),
            evidence=[
                f"{sku_count} SKUs distintos suministrados de {s.get('totalTrackedSkus')} comprados",
                f"Cobertura {round(sku_share*100,1)}% del catálogo de compra",
            ],
            metrics={"scope": "supplier", "supplier": s["name"], "skuCount": sku_count, "skuShare": sku_share},
            period={"current": _period_bounds(180, ref)},
            source=["facturas_recibidas", "invoice_lines"],
            confidence="high" if sku_share >= 0.6 else "medium",
            estimated_impact={"kind": "estimated", "explanation": "Si falla este proveedor, una gran parte del catálogo queda sin reponer", "skusAtRisk": sku_count},
            recommended_action="Busca un segundo proveedor para estos SKUs y negocia condiciones alternativas.",
        ))

    # Dependencia: un proveedor concentra demasiado gasto
    for s in supp:
        if s.get("spendShare") is None or s["spendShare"] < SUPPLIER_DEPENDENCY_SHARE:
            continue
        if str(s.get("name") or s.get("id") or "") in seen_dependency:
            continue  # mismo proveedor ya señalado por SKUs — no duplicar
        findings.append(make_finding(
            finding_type="supplier_dependency",
            severity="medium",
            category="problem",
            title=f"Dependencia del proveedor {s['name']}",
            observation=(
                f"{s['name']} concentra el {round(s['spendShare']*100,1)}% del gasto de compras "
                f"({s['spend']:.2f} € en {s['invoices']} facturas)."
            ),
            evidence=[
                f"Gasto {s['spend']:.2f} € = {round(s['spendShare']*100,1)}% del total",
                f"{s['invoices']} facturas recibidas",
            ],
            metrics={"scope": "supplier", "supplier": s["name"], "spend": s["spend"], "spendShare": s["spendShare"]},
            period={"current": _period_bounds(90, ref)},
            source=["facturas_recibidas"],
            confidence="high",
            estimated_impact={"kind": "estimated", "explanation": "Riesgo de negociación si un proveedor es irremplazable"},
            recommended_action="Busca proveedores alternativos y negocia condiciones con este proveedor.",
        ))
    # Encarecimiento: el precio unitario de sus productos subió
    for sp in supp_price:
        if sp.get("priceTrendPct") is not None and sp["priceTrendPct"] >= SUPPLIER_PRICE_INCREASE * 100:
            inc = sp["increasingSkus"]
            top_sku = inc[0] if inc else {}
            # MEGA UPDATE (A2): coste extra estimado = unidades compradas del
            # SKU encarecido × diferencia de precio (último vs primero). Sin
            # unidades conocidas → se expresa como % sin inventar €.
            extra_euro = None
            if top_sku.get("lastPrice") is not None and top_sku.get("firstPrice") is not None:
                diff = float(top_sku["lastPrice"]) - float(top_sku["firstPrice"])
                if diff > 0 and top_sku.get("units") is not None:
                    extra_euro = round(diff * float(top_sku["units"]), 2)
            impact = {
                "kind": "calculated" if extra_euro is not None else "estimated",
                "explanation": (
                    f"Coste extra por unidad comprada del SKU {top_sku.get('sku','')}: "
                    f"{top_sku.get('firstPrice')}€ → {top_sku.get('lastPrice')}€"
                ),
            }
            if extra_euro is not None:
                impact["economicImpactEuro"] = extra_euro
            findings.append(make_finding(
                finding_type="supplier_cost_increase",
                severity="medium",
                category="problem",
                title=f"El proveedor {sp['name']} ha subido sus precios",
                observation=(
                    f"{sp['name']} encarece sus productos: {top_sku.get('sku','')} pasa de "
                    f"{top_sku.get('firstPrice')}€ a {top_sku.get('lastPrice')}€ "
                    f"({top_sku.get('changePct')}%)."
                ),
                evidence=[
                    f"SKU {top_sku.get('sku')}: {top_sku.get('firstPrice')}€ → {top_sku.get('lastPrice')}€ ({top_sku.get('changePct')}%)",
                    f"{sp.get('trackedSkus')} SKUs con histórico de precio de este proveedor",
                ],
                metrics={"scope": "supplier", "supplier": sp["name"], "priceIncreasePct": sp["priceTrendPct"], "sku": top_sku.get("sku"), "extraCostEuro": extra_euro},
                period={"current": _period_bounds(180, ref)},
                source=["facturas_recibidas", "invoice_lines"],
                confidence="high" if sp["priceTrendPct"] >= 40 else "medium",
                estimated_impact=impact,
                recommended_action="Renegocia precios con este proveedor o busca alternativa para esos SKUs.",
            ))
    return findings


def detect_expense_growth(finance: dict[str, Any], data: dict[str, Any], ref: datetime | None = None) -> list[dict[str, Any]]:
    """Gastos recurrentes crecientes: agrupa pagos por su base de referencia
    (rent-01→rent, services-01→services) y detecta series al alza."""
    findings: list[dict[str, Any]] = []
    payments = [f for f in (data.get("organizedFinance") or []) if isinstance(f, dict) and f.get("type") == "payment"]
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in payments:
        ref = str(f.get("reference") or f.get("id") or "").strip()
        if not ref:
            continue
        key = _recurring_key(ref)
        amount = business_model._as_float(f.get("amount"))
        if amount is None:
            continue
        groups.setdefault(key, []).append({"date": f.get("date"), "amount": amount})
    for key, rows in groups.items():
        if len(rows) < EXPENSE_GROUP_MIN_ROWS:
            continue
        rows.sort(key=lambda r: r["date"] or "")
        first, last = rows[0]["amount"], rows[-1]["amount"]
        if first <= 0:
            continue
        growth = round((last - first) / first * 100, 1)
        if growth >= EXPENSE_GROUP_GROWTH * 100:
            findings.append(make_finding(
                finding_type="expense_growing",
                severity="medium",
                category="problem",
                title=f"Gasto recurrente en alza: {key}",
                observation=(
                    f"El gasto recurrente '{key}' pasa de {first:.2f}€ a {last:.2f}€ "
                    f"({growth:+.1f}%) en {len(rows)} pagos."
                ),
                evidence=[
                    f"Primer pago {first:.2f}€, último {last:.2f}€",
                    f"{len(rows)} pagos en la serie",
                ],
                metrics={"scope": "expense", "category": key, "first": first, "last": last, "growthPct": growth},
                period={"current": _period_bounds(180, ref)},
                source=["tesorería"],
                confidence="high" if growth >= 40 else "medium",
                estimated_impact={"kind": "calculated", "explanation": "Aumento de gasto recurrente", "monthlyIncrease": round(last - first, 2)},
                recommended_action="Revisa esta partida de gasto: renegocia o busca una alternativa más barata.",
            ))
    return findings


# ---------------------------------------------------------------------------
# Orquestación + dedupe + lifecycle
# ---------------------------------------------------------------------------


def _load_stored(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stored = data.get("businessFindings") or []
    by_sig: dict[str, dict[str, Any]] = {}
    if isinstance(stored, list):
        for f in stored:
            if isinstance(f, dict) and f.get("signature"):
                by_sig[f["signature"]] = f
    return by_sig


def run_detection(data: dict[str, Any] | None = None, *, persist: bool = True) -> dict[str, Any]:
    """Ejecuta todos los detectores, deduplica por firma y aplica el lifecycle
    (new → active → acknowledged → resolved → archived)."""
    if data is None:
        data = config_store.load()
    quality = data_quality(data)
    sales = data.get("organizedSales") or []
    products = data.get("organizedProducts") or []
    invoices = data.get("organizedInvoices") or []
    if not isinstance(sales, list):
        sales = []
    if not isinstance(products, list):
        products = []
    if not isinstance(invoices, list):
        invoices = []

    # FASE B — señales empresariales (inventario, clientes, proveedores,
    # gastos recurrentes) desde el modelo canónico, con UNKNOWN ≠ 0.
    from . import business_signals

    try:
        signals = business_signals.compute_signals(data)
    except Exception:  # noqa: BLE001 — las señales nunca deben romper el motor
        signals = {"products": [], "customers": [], "suppliers": [], "supplierPrices": [], "finance": {}, "period": {}}

    aov = _aov_metrics(sales)
    exp = _expense_metrics(invoices)
    tm = _treasury_metrics(data)

    # MEGA UPDATE (A2/A4): fecha de referencia de los DATOS para que las
    # ventanas de todos los detectores sean estables (misma fuente que las
    # señales). Sin esto, la firma cambiaba con "hoy" y el mismo finding se
    # duplicaba cada día.
    ref = _reference_date(sales) or _reference_date(invoices) or datetime.now(timezone.utc)

    fresh: list[dict[str, Any]] = []
    fresh += detect_products(signals.get("products") or [], quality, signals.get("period") or {}, sales)
    fresh += detect_cross_selling(sales, products, quality, ref)
    fresh += detect_aov(aov, quality, ref, sales)
    fresh += detect_expenses(exp, quality)
    fresh += detect_treasury(tm, quality, ref)
    # FASE B — señales
    fresh += detect_inventory(signals.get("products") or [], ref)
    fresh += detect_customers(signals.get("customers") or [], data, ref)
    fresh += detect_suppliers(
        signals.get("suppliers") or [],
        signals.get("supplierPrices") or [],
        signals.get("supplierSkus") or [],
        ref,
    )
    fresh += detect_expense_growth(signals.get("finance") or {}, data, ref)
    # FASE C (B8) — calidad de datos (anomalías PRESERVADAS → findings)
    fresh += detect_data_quality(data, ref)

    # Dedupe + lifecycle: un hallazgo que persiste NO crea copias.
    stored = _load_stored(data)
    now = _now()
    merged: list[dict[str, Any]] = []
    # BUG-001-INTRA (hallazgo de Mathew): dedupe INTRA-RUN. Con la firma
    # estable (type:entity), dos detectores distintos pueden emitir la misma
    # firma en un mismo run (p.ej. detect_products emite product_declining
    # desde la ventana 60d y desde la 30d para el mismo SKU). El dedupe contra
    # stored no basta: hay que colapsar los fresh duplicados entre sí,
    # quedándose con el de mayor severidad (y más reciente en caso de empate).
    fresh_by_sig: dict[str, dict[str, Any]] = {}
    for f in fresh:
        sig = f.get("signature")
        if not sig:
            continue
        prev_fresh = fresh_by_sig.get(sig)
        if prev_fresh is None or _severity_rank(f.get("severity")) > _severity_rank(prev_fresh.get("severity")):
            fresh_by_sig[sig] = f
    fresh = list(fresh_by_sig.values())
    fresh_sigs = {f["signature"] for f in fresh}
    for f in fresh:
        prev = stored.get(f["signature"])
        if prev:
            f["id"] = prev["id"]
            f["createdAt"] = prev["createdAt"]
            f["status"] = prev["status"]
            f["timesSeen"] = int(prev.get("timesSeen") or 0) + 1
            if f["status"] in ("resolved", "archived"):
                # Reapareció después de resolverse → vuelve a ACTIVE para revisión
                f["status"] = "active"
        f["updatedAt"] = now
        f["lastSeenAt"] = now
        merged.append(f)
    # Los almacenados que ya no se detectan quedan con lastSeenAt viejo
    for sig, f in stored.items():
        if sig not in fresh_sigs:
            merged.append(f)

    merged.sort(key=lambda f: _severity_rank(f.get("severity")), reverse=True)
    # PRODUCT LEAP: firmas DETECTADAS EN ESTA EJECUCION (no las almacenadas
    # que solo se conservan con lastSeenAt viejo). Permite a los consumidores
    # (recomendaciones, insights) distinguir "activo ahora" de "histórico".
    result = {
        "ok": True,
        "ranAt": now,
        "quality": quality,
        "blockedReasons": list(quality.get("notes") or []),
        "findings": merged,
        "freshSignatures": sorted(fresh_sigs),
        "counts": {"problems": sum(1 for f in merged if f.get("category") == "problem" and f.get("status") not in ("resolved", "archived")), "opportunities": sum(1 for f in merged if f.get("category") == "opportunity" and f.get("status") not in ("resolved", "archived")), "positive": sum(1 for f in merged if f.get("category") == "positive" and f.get("status") not in ("resolved", "archived"))},
    }
    if persist:
        try:
            config_store.save({"businessFindings": merged, "detectionRunAt": now})
        except Exception:
            pass
    return result


def _severity_rank(sev: str | None) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(sev or "", 0)


def _impact_euro(f: dict[str, Any]) -> float | None:
    """Importe económico cuantificado de un finding, si existe. UNKNOWN ≠ 0:
    sin importe real devuelve None (nunca 0, para no inventar precisión)."""
    imp = f.get("estimatedImpact") or {}
    for key in ("economicImpactEuro", "inventoryValue", "revenueAtRisk", "marginPotential", "cashRequired", "monthlyIncrease"):
        v = imp.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


# MEGA UPDATE (A10) — semáforo de salud empresarial por dimensión.
# Estados: GOOD / WARNING / CRITICAL / UNKNOWN. UNKNOWN ≠ 0: una dimensión
# SIN DATOS no se marca GOOD (no hay evidencia de salud), se marca UNKNOWN.
HEALTH_DIMENSION_TYPES: dict[str, tuple[str, ...]] = {
    "ventas": ("product_declining", "aov_change", "low_revenue_high_margin"),
    "margen": ("high_revenue_low_margin", "low_revenue_high_margin", "missing_cost", "customer_low_margin"),
    "inventario": ("stockout_risk", "overstock", "dead_stock"),
    "clientes": ("customer_churn", "customer_concentration", "customer_low_margin", "customer_no_orders", "duplicate_customer"),
    "proveedores": ("supplier_dependency", "supplier_cost_increase"),
    "finanzas": ("expenses_growing", "expense_growing", "upcoming_payments_concentration", "inconsistent_order_total"),
    "datos": ("duplicate_sku", "missing_sku", "duplicate_customer", "missing_cost", "inconsistent_order_total"),
}
HEALTH_DIMENSION_LABELS = {
    "ventas": "Ventas", "margen": "Margen", "inventario": "Inventario",
    "clientes": "Clientes", "proveedores": "Proveedores", "finanzas": "Finanzas", "datos": "Calidad de datos",
}


def health_scores(findings: list[dict[str, Any]] | None = None, quality: dict[str, Any] | None = None) -> dict[str, Any]:
    """Semáforo por dimensión desde hallazgos ACTIVOS y calidad de datos.
    CRITICAL = problema high activo; WARNING = problema medium activo;
    GOOD = dimensión con datos y sin problemas; UNKNOWN = sin datos suficientes
    para juzgar (nunca GOOD sin evidencia). El agregado sigue el peor estado.

    MEGA UPDATE (A9): si el llamador ya tiene findings y quality cargados, NO
    se vuelve a leer config (una sola lectura por request)."""
    if findings is None or quality is None:
        data = config_store.load()
    if findings is None:
        stored = data.get("businessFindings") or []
        findings = stored if isinstance(stored, list) else []
    # UNKNOWN ≠ 0 / existente ≠ VERIFIED: un finding resuelto o archivado NO
    # cuenta para el semáforo (no es un problema actual).
    findings = [f for f in findings if isinstance(f, dict) and str(f.get("status") or "").lower() not in ("resolved", "archived")]
    if quality is None:
        quality = data_quality(data)

    dims: dict[str, dict[str, Any]] = {}
    for dim, types in HEALTH_DIMENSION_TYPES.items():
        related = [f for f in findings if f.get("type") in types]
        problems = [f for f in related if f.get("category") == "problem"]
        if problems:
            sev = max(3 if f.get("severity") == "high" else (2 if f.get("severity") == "medium" else 1) for f in problems)
            state = "CRITICAL" if sev == 3 else "WARNING"
        elif dim == "datos":
            # UNKNOWN != 0 / existente != VERIFIED: GOOD solo si hay entidades
            # reales que auditar y ninguna con problemas. Sin datos, UNKNOWN.
            has_data = bool(quality and (quality.get("ordersTotal") or 0) + (quality.get("productsTotal") or 0) > 0)
            state = "GOOD" if has_data else "UNKNOWN"
        else:
            state = "UNKNOWN"
        dims[dim] = {
            "label": HEALTH_DIMENSION_LABELS[dim],
            "state": state,
            "findings": len(related),
            "problems": len(problems),
        }

    # El semáforo usa señales reales para marcar GOOD solo cuando hay datos:
    # ventas/margen requieren pedidos analizables; finanzas requiere facturas.
    if quality.get("canAnalyzeProducts") and dims["ventas"]["state"] == "UNKNOWN":
        dims["ventas"]["state"] = "GOOD"
    if quality.get("canAnalyzeMargin") and dims["margen"]["state"] == "UNKNOWN":
        dims["margen"]["state"] = "GOOD"
    if quality.get("canAnalyzeTreasury") and dims["finanzas"]["state"] == "UNKNOWN":
        dims["finanzas"]["state"] = "GOOD"
    if quality.get("canAnalyzeExpenses") and dims["finanzas"]["state"] == "UNKNOWN":
        dims["finanzas"]["state"] = "GOOD"

    order = ("CRITICAL", "WARNING", "UNKNOWN", "GOOD")
    rank = {s: i for i, s in enumerate(order)}
    # El agregado es el PEOR estado (menor rank), no el mejor.
    overall = min(dims, key=lambda d: rank[dims[d]["state"]])
    return {
        "ok": True,
        "overall": {
            "state": dims[overall]["state"],
            "label": HEALTH_DIMENSION_LABELS[overall],
        },
        "dimensions": dims,
    }


def executive_brief(findings: list[dict[str, Any]] | None = None, quality: dict[str, Any] | None = None) -> dict[str, Any]:
    """MEGA UPDATE (A11) — brief ejecutivo con evidencia del motor, para que
    Hermes y la UI respondan "¿cómo está mi empresa? / ¿cuál es el mayor
    problema? / ¿cuánto dinero está en riesgo? / ¿qué hacer hoy?" sin que el
    LLM invente nada. Todo sale de findings activos y calidad real.

    MEGA UPDATE (A9): si findings y quality ya están cargados, no se vuelve a
    leer config (una sola lectura por request)."""
    if findings is None or quality is None:
        data = config_store.load()
    if findings is None:
        stored = data.get("businessFindings") or []
        findings = stored if isinstance(stored, list) else []
    if quality is None:
        quality = data_quality(data)
    health = health_scores(findings, quality)

    active = [f for f in findings if isinstance(f, dict) and str(f.get("status") or "").lower() not in ("resolved", "archived")]
    problems = [f for f in active if f.get("category") == "problem"]
    opps = [f for f in active if f.get("category") == "opportunity"]

    def _score(f: dict[str, Any]) -> float:
        euro = _impact_euro(f) or 0.0
        conf = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(str(f.get("confidence") or ""), 0.5)
        return euro * conf

    top_problem = max(problems, key=_score) if problems else None
    top_opp = max(opps, key=_score) if opps else None
    # UNKNOWN != 0: si ningún problema tiene impacto cuantificado, el dinero
    # en riesgo NO es 0, es desconocido. Solo se suma lo cuantificado.
    _euros = [_impact_euro(f) for f in problems]
    money_at_risk = round(sum(e for e in _euros if e is not None), 2) if any(e is not None for e in _euros) else None
    _euros_o = [_impact_euro(f) for f in opps]
    opp_potential = round(sum(e for e in _euros_o if e is not None), 2) if any(e is not None for e in _euros_o) else None

    return {
        "ok": True,
        "health": health["overall"]["state"],
        "healthLabel": health["overall"]["label"],
        "summary": (
            f"La salud general es {health['overall']['state'].lower()} "
            f"(dimensión más afectada: {health['overall']['label'].lower()})."
        ),
        "topProblem": top_problem,
        "moneyAtRisk": money_at_risk,
        "topOpportunity": top_opp,
        "opportunityPotential": opp_potential,
        "actionPlan": action_plan(limit=3, findings=findings),
        "missingInfo": list(quality.get("notes") or []),
    }


def action_plan(limit: int = 5, findings: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """MEGA UPDATE (A3) — "¿Qué hacer hoy?": prioriza los hallazgos activos
    por IMPACTO ECONÓMICO × confianza × severidad. Sin importe cuantificado
    el finding se ordena por severidad (nunca se le inventa un €). Devuelve
    las N acciones de mayor valor para que la UI y Hermes las presenten como
    prioridad, sin duplicar la lógica de ranking en el frontend."""
    if findings is None:
        data = config_store.load()
        stored = data.get("businessFindings") or []
        findings = stored if isinstance(stored, list) else []
    active = [f for f in findings if isinstance(f, dict) and str(f.get("status") or "").lower() not in ("resolved", "archived")]
    if not active:
        return []

    conf_w = {"high": 1.0, "medium": 0.7, "low": 0.4}.get
    sev_w = {"high": 1.0, "medium": 0.6, "low": 0.3}.get

    def _score(f: dict[str, Any]) -> float:
        euro = _impact_euro(f)
        base = float(euro or 0.0) * conf_w(str(f.get("confidence") or ""), 0.5)
        if euro is None:
            # Sin importe cuantificado: severidad sola, por debajo de los cuantificados
            base = sev_w(str(f.get("severity") or ""), 0.0)
        return base

    ranked = sorted(active, key=_score, reverse=True)
    out: list[dict[str, Any]] = []
    for f in ranked[:limit]:
        out.append({
            "id": f.get("id"),
            "type": f.get("type"),
            "category": f.get("category"),
            "severity": f.get("severity"),
            "confidence": f.get("confidence"),
            "title": f.get("title"),
            "observation": f.get("observation"),
            "recommendedAction": f.get("recommendedAction"),
            "impactEuro": _impact_euro(f),
            "impactExplanation": (f.get("estimatedImpact") or {}).get("explanation"),
            "metrics": f.get("metrics"),
        })
    return out


def list_findings(status: str = "") -> dict[str, Any]:
    data = config_store.load()
    stored = data.get("businessFindings") or []
    if not isinstance(stored, list):
        stored = []
    status = (status or "").strip().lower()
    if status:
        stored = [f for f in stored if str(f.get("status") or "").lower() == status]
    q = data_quality(data)
    return {
        "ok": True,
        "count": len(stored),
        "findings": copy.deepcopy(stored),
        "quality": q,
        "actionPlan": action_plan(findings=stored),
        "healthScores": health_scores(stored, q),
        "executiveBrief": executive_brief(stored, q),
    }


def update_finding_status(finding_id: str, new_status: str) -> dict[str, Any]:
    new_status = (new_status or "").strip().lower()
    if new_status not in FINDING_STATUSES:
        return {"ok": False, "error": f"Estado inválido ({new_status}); usa {', '.join(FINDING_STATUSES)}"}
    # BUG-008 FIX: RMW atómico bajo un solo lock. Antes hacía load() → modificar
    # → save() sin serializar el ciclo completo; con ThreadingHTTPServer (API
    # server) y el scheduler en background escribiendo businessFindings a la vez,
    # dos hilos podían hacer lost-update (el estado del finding se perdía).
    outcome: dict[str, Any] = {"ok": False, "error": "Hallazgo no encontrado"}

    def _mutate(cfg: dict[str, Any]) -> dict[str, Any]:
        nonlocal outcome
        stored = cfg.get("businessFindings") or []
        if not isinstance(stored, list):
            stored = []
        changed = False
        for f in stored:
            if isinstance(f, dict) and f.get("id") == finding_id:
                f["status"] = new_status
                f["updatedAt"] = _now()
                # BUG-004 FIX: rellenar acknowledgedAt cuando el finding se marca
                # como acknowledged (antes solo se actualizaba updatedAt genérico).
                if new_status == "acknowledged" and not f.get("acknowledgedAt"):
                    f["acknowledgedAt"] = _now()
                changed = True
        if not changed:
            return cfg  # no-op: no escribir, devolver estado sin cambios
        cfg["businessFindings"] = stored
        outcome = {"ok": True, "status": new_status}
        return cfg

    config_store.update(_mutate)
    return outcome
