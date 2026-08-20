"""VANOVA Business Signals — FASE B.

Señales empresariales estructuradas calculadas UNA sola vez desde el modelo
canónico (config_store). Son la materia prima del motor de detección y del
contexto que recibe Hermes: en vez de darle texto crudo, se le dan señales con
evidencia (métrica actual + referencia + tendencia + stock + impacto).

Cadena:
  DATOS CANÓNICOS → BUSINESS SIGNALS → DETECTORES → FINDINGS → HERMES → DECISIÓN

Reglas de honestidad (compartidas con todo el producto):
  - UNKNOWN ≠ 0: si falta un dato (stock, coste, histórico) la señal es None y
    el detector produce INSUFFICIENT_EVIDENCE, nunca un hallazgo inventado.
  - Las ventanas temporales son RELATIVAS A LOS DATOS (max(fecha)), no a "hoy",
    para que funcionen con datos desactualizados o históricos.
  - Ninguna señal hardcodea SKUs, nombres ni empresas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import business_model, config_store, product_identity


def _as_float(v: Any) -> float | None:
    return business_model._as_float(v)


def _as_date(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:10]).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _reference_date(rows: list[dict[str, Any]]) -> datetime | None:
    """Fecha de referencia = última fecha real del dataset (no "hoy")."""
    best: datetime | None = None
    for r in rows:
        d = _as_date(r.get("date"))
        if d is not None and (best is None or d > best):
            best = d
    return best


def _bucket_lines(sales: list[dict[str, Any]], lo: datetime, hi: datetime) -> dict[str, dict[str, float]]:
    """Unidades/revenue por SKU dentro de una ventana [lo, hi]."""
    out: dict[str, dict[str, float]] = {}
    for s in sales:
        d = _as_date(s.get("date"))
        if d is None or d.date() < lo.date() or d.date() > hi.date():
            continue
        for li in business_model.normalize_sale_lines(s):
            sku = str(li.get("sku") or "").strip().lower()
            if not sku:
                continue
            qty = _as_float(li.get("quantity")) or 1.0
            price = _as_float(li.get("price"))
            if price is None:
                continue
            row = out.setdefault(sku, {"units": 0.0, "revenue": 0.0})
            row["units"] += qty
            row["revenue"] += price * qty
    return out


def product_signals(sales: list[dict[str, Any]], products: list[dict[str, Any]], ref: datetime) -> list[dict[str, Any]]:
    """Señales por producto canónico: revenue, margen, velocidad, stock, rotación,
    riesgo de stockout, exceso de stock y dead stock. UNKNOWN ≠ 0."""
    catalog = [p for p in products if isinstance(p, dict)]
    cost_by_sku: dict[str, float] = {}
    for p in catalog:
        rc = product_identity.resolve_cost(p)
        sku = str(p.get("sku") or "").strip().lower()
        if sku and rc.get("costStatus") in ("verified", "imported") and rc.get("cost") is not None:
            cost_by_sku[sku] = rc["cost"]

    cur_from = ref - timedelta(days=30)
    prev_from = ref - timedelta(days=60)
    prev_to = cur_from - timedelta(days=1)
    long_from = ref - timedelta(days=90)
    long_to = prev_from - timedelta(days=1)
    cur = _bucket_lines(sales, cur_from, ref)
    prev = _bucket_lines(sales, prev_from, prev_to)
    long = _bucket_lines(sales, long_from, long_to)

    # Unidades totales por SKU (histórico completo) para velocidad/dead stock.
    total = _bucket_lines(sales, ref - timedelta(days=3650), ref)
    span_days = 365.0

    out: list[dict[str, Any]] = []
    for p in catalog:
        sku = str(p.get("sku") or "").strip().lower()
        cost = cost_by_sku.get(sku) if sku else None
        rrp = _as_float(p.get("rrp"))
        c = cur.get(sku, {"units": 0.0, "revenue": 0.0})
        pv = prev.get(sku, {"units": 0.0, "revenue": 0.0})
        lg = long.get(sku, {"units": 0.0, "revenue": 0.0})
        t = total.get(sku, {"units": 0.0, "revenue": 0.0})
        stock = _as_float(p.get("stock") if p.get("stock") not in (None, "") else p.get("stockQty"))

        margin_pct = None
        markup_pct = None
        margin_euro = None
        if cost is not None and rrp is not None and rrp > 0:
            diff = rrp - cost
            margin_euro = round(diff, 2)
            margin_pct = round(diff / rrp * 100, 1)
            markup_pct = round(diff / cost * 100, 1) if cost else None

        velocity = t["units"] / span_days if t["units"] > 0 else 0.0
        days_of_stock = (stock / velocity) if (stock is not None and velocity > 0) else None
        trend_pct = None
        if pv["units"] > 0:
            trend_pct = round((c["units"] - pv["units"]) / pv["units"] * 100, 1)

        inventory_value = round(stock * cost, 2) if (stock is not None and cost is not None) else None

        out.append({
            "sku": sku or p.get("name") or "—",
            "name": p.get("name") or "",
            "cost": cost,
            "salePrice": rrp,
            "hasCost": cost is not None,
            "marginEuro": margin_euro,
            "marginPct": margin_pct,
            "markupPct": markup_pct,
            "units": t["units"],
            "revenue": t["revenue"],
            "revenueShare": 0.0,  # rellenado abajo
            "units30d": c["units"],
            "unitsPrev30d": pv["units"],
            "revenue30d": c["revenue"],
            "revenuePrev30d": pv["revenue"],
            "unitsPrev60d": lg["units"],
            "revenuePrev60d": lg["revenue"],
            "trendPct": trend_pct,
            "velocityPerDay": round(velocity, 3),
            "stock": stock,
            "hasStock": stock is not None,
            "daysOfStock": round(days_of_stock, 1) if days_of_stock is not None else None,
            "inventoryValue": inventory_value,
        })
    # SKUs que aparecen en VENTAS pero NO en el catálogo (líneas sin match):
    # también son señales (tendencia/volumen) aunque sin coste ni stock. Así
    # una caída/crecimiento se detecta aunque el SKU no esté en el catálogo.
    catalog_skus = {x["sku"] for x in out}
    for sku, t in total.items():
        if sku in catalog_skus:
            continue
        c = cur.get(sku, {"units": 0.0, "revenue": 0.0})
        pv = prev.get(sku, {"units": 0.0, "revenue": 0.0})
        lg = long.get(sku, {"units": 0.0, "revenue": 0.0})
        trend_pct = round((c["units"] - pv["units"]) / pv["units"] * 100, 1) if pv["units"] > 0 else None
        out.append({
            "sku": sku,
            "name": sku,
            "cost": None,
            "salePrice": None,
            "hasCost": False,
            "marginEuro": None,
            "marginPct": None,
            "markupPct": None,
            "units": t["units"],
            "revenue": t["revenue"],
            "revenueShare": 0.0,
            "units30d": c["units"],
            "unitsPrev30d": pv["units"],
            "revenue30d": c["revenue"],
            "revenuePrev30d": pv["revenue"],
            "unitsPrev60d": lg["units"],
            "revenuePrev60d": lg["revenue"],
            "trendPct": trend_pct,
            "velocityPerDay": round(t["units"] / span_days, 3) if t["units"] > 0 else 0.0,
            "stock": None,
            "hasStock": False,
            "daysOfStock": None,
            "inventoryValue": None,
        })
    total_rev = sum(x["revenue"] for x in out) or 0.0
    for x in out:
        x["revenueShare"] = round(x["revenue"] / total_rev, 4) if total_rev else 0.0
    out.sort(key=lambda x: x["revenue"], reverse=True)
    return out


def customer_signals(sales: list[dict[str, Any]], products: list[dict[str, Any]], ref: datetime) -> list[dict[str, Any]]:
    """Señales por cliente: revenue, pedidos, ticket medio, concentración,
    tendencia y churn. Derivadas de los pedidos (customer + line_items)."""
    cost_by_sku: dict[str, float] = {}
    for p in products:
        if not isinstance(p, dict):
            continue
        rc = product_identity.resolve_cost(p)
        sku = str(p.get("sku") or "").strip().lower()
        if sku and rc.get("costStatus") in ("verified", "imported") and rc.get("cost") is not None:
            cost_by_sku[sku] = rc["cost"]

    cur_from = ref - timedelta(days=30)
    prev_from = ref - timedelta(days=60)
    prev_to = cur_from - timedelta(days=1)

    def _agg(rows: list[dict[str, Any]], lo: datetime | None, hi: datetime | None) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for s in rows:
            d = _as_date(s.get("date"))
            if lo is not None and (d is None or d.date() < lo.date()):
                continue
            if hi is not None and (d is not None and d.date() > hi.date()):
                continue
            cust = str(s.get("customer") or s.get("customerEmail") or s.get("customer_id") or "").strip()
            if not cust or cust == "—":
                continue
            total = _as_float(s.get("total")) or 0.0
            row = out.setdefault(cust, {"revenue": 0.0, "orders": 0, "cost": 0.0, "last": d})
            row["revenue"] += total
            row["orders"] += 1
            for li in business_model.normalize_sale_lines(s):
                sku = str(li.get("sku") or "").strip().lower()
                qty = _as_float(li.get("quantity")) or 1.0
                cost = cost_by_sku.get(sku)
                if cost is not None:
                    row["cost"] += cost * qty
            if d is not None and (row["last"] is None or d > row["last"]):
                row["last"] = d
        return out

    cur = _agg(sales, cur_from, None)
    prev = _agg(sales, prev_from, prev_to)
    total = _agg(sales, None, None)

    out: list[dict[str, Any]] = []
    for cust, t in total.items():
        c = cur.get(cust, {"revenue": 0.0, "orders": 0})
        pv = prev.get(cust, {"revenue": 0.0, "orders": 0})
        rev = t["revenue"]
        margin_pct = round((rev - t["cost"]) / rev * 100, 1) if rev > 0 else None
        trend_pct = round((c["revenue"] - pv["revenue"]) / pv["revenue"] * 100, 1) if pv["revenue"] > 0 else None
        days_since_last = None
        if t["last"] is not None:
            days_since_last = (ref - t["last"]).days
        out.append({
            "id": cust,
            "name": cust,
            "revenue": round(rev, 2),
            "orders": t["orders"],
            "avgTicket": round(rev / t["orders"], 2) if t["orders"] else None,
            "marginPct": margin_pct,
            "trendPct": trend_pct,
            "lastOrder": t["last"].isoformat() if t["last"] else None,
            "daysSinceLastOrder": days_since_last,
            "orders30d": c["orders"],
            "revenue30d": c["revenue"],
        })
    total_rev = sum(x["revenue"] for x in out) or 0.0
    for x in out:
        x["revenueShare"] = round(x["revenue"] / total_rev, 4) if total_rev else 0.0
    out.sort(key=lambda x: x["revenue"], reverse=True)
    return out


def supplier_signals(invoices: list[dict[str, Any]], ref: datetime) -> list[dict[str, Any]]:
    """Señales por proveedor desde facturas recibidas: gasto, nº facturas,
    tendencia del gasto, dependencia y concentración. UNKNOWN ≠ 0."""
    received = [i for i in invoices if isinstance(i, dict) and i.get("type") == "received"]
    cur_from = ref - timedelta(days=60)
    prev_from = ref - timedelta(days=120)
    prev_to = cur_from - timedelta(days=1)

    def _agg(rows: list[dict[str, Any]], lo: datetime | None, hi: datetime | None) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for i in rows:
            d = _as_date(i.get("date"))
            if lo is not None and (d is None or d.date() < lo.date()):
                continue
            if hi is not None and (d is not None and d.date() > hi.date()):
                continue
            sup = str(i.get("supplierId") or i.get("supplierName") or "").strip()
            if not sup:
                continue
            total = _as_float(i.get("total")) or 0.0
            row = out.setdefault(sup, {"spend": 0.0, "invoices": 0})
            row["spend"] += total
            row["invoices"] += 1
        return out

    cur = _agg(received, cur_from, None)
    prev = _agg(received, prev_from, prev_to)
    total = _agg(received, None, None)

    out: list[dict[str, Any]] = []
    for sup, t in total.items():
        c = cur.get(sup, {"spend": 0.0, "invoices": 0})
        pv = prev.get(sup, {"spend": 0.0, "invoices": 0})
        trend_pct = round((c["spend"] - pv["spend"]) / pv["spend"] * 100, 1) if pv["spend"] > 0 else None
        out.append({
            "id": sup,
            "name": sup,
            "spend": round(t["spend"], 2),
            "invoices": t["invoices"],
            "avgInvoice": round(t["spend"] / t["invoices"], 2) if t["invoices"] else None,
            "spendTrendPct": trend_pct,
            "spend60d": c["spend"],
            "spendPrev60d": pv["spend"],
        })
    total_spend = sum(x["spend"] for x in out) or 0.0
    for x in out:
        x["spendShare"] = round(x["spend"] / total_spend, 4) if total_spend else 0.0
    out.sort(key=lambda x: x["spend"], reverse=True)
    return out


def supplier_sku_signals(invoice_lines: list[dict[str, Any]], invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """TRAZABILIDAD proveedor → producto → SKU (MEGA UPDATE, A1).

    Reconstruye la relación proveedor→SKU desde los datos que SÍ existen:
    línea de factura (sku) → factura recibida (supplierId). Devuelve por
    proveedor cuántos SKUs distintos suministra y qué fracción del total de
    SKUs comprados representa. Es la base de la dependencia por nº de SKUs
    (no solo por gasto) y del "impacto en margen por proveedor".

    UNKNOWN ≠ 0: sin líneas, sin vínculo factura, o sin SKU → la señal se
    omite (no se emite 0). La dependencia solo se puede afirmar si hay
    evidencia real de cobertura."""
    received_by_id = {
        str(i.get("id") or "").strip(): i
        for i in invoices
        if isinstance(i, dict) and i.get("type") == "received"
    }
    skus_by_supplier: dict[str, set[str]] = {}
    for l in invoice_lines:
        if not isinstance(l, dict):
            continue
        inv = received_by_id.get(str(l.get("invoiceId") or "").strip())
        if not inv:
            continue
        sup = str(inv.get("supplierId") or inv.get("supplierName") or "").strip()
        sku = str(l.get("sku") or "").strip().lower()
        if not sup or not sku:
            continue
        skus_by_supplier.setdefault(sup, set()).add(sku)

    all_skus = set().union(*skus_by_supplier.values()) if skus_by_supplier else set()
    total_skus = len(all_skus)
    out: list[dict[str, Any]] = []
    for sup, skus in skus_by_supplier.items():
        n = len(skus)
        out.append({
            "id": sup,
            "name": sup,
            "skuCount": n,
            "skuShare": round(n / total_skus, 4) if total_skus else 0.0,
            "totalTrackedSkus": total_skus,
        })
    out.sort(key=lambda x: x["skuCount"], reverse=True)
    return out


def supplier_price_signals(invoice_lines: list[dict[str, Any]], invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evolución del PRECIO UNITARIO por proveedor desde las líneas de facturas
    recibidas (sku + price + fecha). Detecta proveedores que encarecen: compara
    el precio unitario más antiguo con el más reciente de cada SKU.
    UNKNOWN ≠ 0: sin líneas o sin fecha → sin señal."""
    received_by_id = {
        str(i.get("id") or "").strip(): i
        for i in invoices
        if isinstance(i, dict) and i.get("type") == "received"
    }
    # (supplier, sku) → [(date, price), ...] + unidades compradas acumuladas
    # (MEGA UPDATE A2: para estimar el coste extra € de la subida se necesitan
    # las unidades reales compradas del SKU; sin ellas → solo % sin inventar €).
    series: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    units_by_key: dict[tuple[str, str], float] = {}
    for l in invoice_lines:
        if not isinstance(l, dict):
            continue
        inv = received_by_id.get(str(l.get("invoiceId") or "").strip())
        if not inv:
            continue
        sup = str(inv.get("supplierId") or inv.get("supplierName") or "").strip()
        sku = str(l.get("sku") or "").strip().lower()
        price = _as_float(l.get("price"))
        d = _as_date(inv.get("date"))
        if not sup or not sku or price is None or d is None:
            continue
        key = (sup, sku)
        series.setdefault(key, []).append((d, price))
        qty = _as_float(l.get("quantity")) or 0.0
        if qty:
            units_by_key[key] = units_by_key.get(key, 0.0) + qty

    # Por proveedor: el SKU con mayor encarecimiento (último vs primero).
    per_supplier: dict[str, list[dict[str, Any]]] = {}
    for (sup, sku), rows in series.items():
        rows.sort(key=lambda r: r[0])
        if len(rows) < 2:
            continue
        first = rows[0]
        last = rows[-1]
        if first[1] <= 0:
            continue
        change = round((last[1] - first[1]) / first[1] * 100, 1)
        per_supplier.setdefault(sup, []).append({
            "sku": sku,
            "firstPrice": first[1],
            "lastPrice": last[1],
            "firstDate": first[0].isoformat(),
            "lastDate": last[0].isoformat(),
            "changePct": change,
            "units": round(units_by_key.get((sup, sku), 0.0), 2) or None,
        })

    out: list[dict[str, Any]] = []
    for sup, items in per_supplier.items():
        items.sort(key=lambda x: x["changePct"], reverse=True)
        increases = [x for x in items if x["changePct"] > 0]
        max_inc = increases[0]["changePct"] if increases else 0.0
        out.append({
            "id": sup,
            "name": sup,
            "priceTrendPct": max_inc,
            "increasingSkus": increases[:5],
            "trackedSkus": len(items),
        })
    out.sort(key=lambda x: x["priceTrendPct"], reverse=True)
    return out


def finance_signals(data: dict[str, Any], ref: datetime) -> dict[str, Any]:
    """Señales financieras: revenue (ventas), gastos (facturas recibidas),
    pendientes de cobro/pago, presión de caja y evolución mensual."""
    sales = [s for s in (data.get("organizedSales") or []) if isinstance(s, dict)]
    invoices = [i for i in (data.get("organizedInvoices") or []) if isinstance(i, dict)]
    finance = [f for f in (data.get("organizedFinance") or []) if isinstance(f, dict)]

    revenue = sum(_as_float(s.get("total")) or 0.0 for s in sales)
    received = [i for i in invoices if i.get("type") == "received"]
    issued = [i for i in invoices if i.get("type") == "issued"]
    expenses = sum(_as_float(i.get("total")) or 0.0 for i in received)
    gross_profit = revenue - expenses if revenue else None

    pending_collections = sum(_as_float(i.get("total")) or 0.0 for i in issued if not i.get("paid"))
    pending_payments = sum(_as_float(i.get("total")) or 0.0 for i in received if not i.get("paid"))

    collections = [f for f in finance if f.get("type") == "collection"]
    payments = [f for f in finance if f.get("type") == "payment"]
    collections_total = sum(_as_float(f.get("amount")) or 0.0 for f in collections)
    payments_total = sum(_as_float(f.get("amount")) or 0.0 for f in payments)

    # Evolución mensual de ventas y gastos.
    def _monthly(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in rows:
            d = _as_date(r.get("date"))
            if d is None:
                continue
            month = d.strftime("%Y-%m")
            out[month] = out.get(month, 0.0) + (_as_float(r.get(key)) or 0.0)
        return out

    sales_by_month = _monthly(sales, "total")
    expenses_by_month = _monthly(received, "total")

    return {
        "revenue": round(revenue, 2),
        "expenses": round(expenses, 2),
        "grossProfit": round(gross_profit, 2) if gross_profit is not None else None,
        "marginPct": round((revenue - expenses) / revenue * 100, 1) if revenue else None,
        "pendingCollections": round(pending_collections, 2),
        "pendingPayments": round(pending_payments, 2),
        "collectionsTotal": round(collections_total, 2),
        "paymentsTotal": round(payments_total, 2),
        "netCashMovement": round(collections_total - payments_total, 2) if (collections or payments) else None,
        "salesByMonth": sales_by_month,
        "expensesByMonth": expenses_by_month,
        "bankBalance": None,  # no integración bancaria → UNKNOWN
    }


def compute_signals(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Señales completas para detección y contexto de Hermes."""
    if data is None:
        data = config_store.load()
    sales = [s for s in (data.get("organizedSales") or []) if isinstance(s, dict)]
    products = [p for p in (data.get("organizedProducts") or []) if isinstance(p, dict)]
    invoices = [i for i in (data.get("organizedInvoices") or []) if isinstance(i, dict)]

    ref = _reference_date(sales) or _reference_date(invoices) or datetime.now(timezone.utc)
    prod = product_signals(sales, products, ref)
    cust = customer_signals(sales, products, ref)
    supp = supplier_signals(invoices, ref)
    supp_price = supplier_price_signals(data.get("organizedInvoiceLines") or [], invoices)
    supp_skus = supplier_sku_signals(data.get("organizedInvoiceLines") or [], invoices)
    fin = finance_signals(data, ref)

    return {
        "period": {
            "reference": ref.isoformat(),
            "current30d": [(ref - timedelta(days=30)).isoformat(), ref.isoformat()],
            "previous30d": [(ref - timedelta(days=60)).isoformat(), (ref - timedelta(days=30)).isoformat()],
        },
        "products": prod,
        "customers": cust,
        "suppliers": supp,
        "supplierPrices": supp_price,
        "supplierSkus": supp_skus,
        "finance": fin,
        "counts": {
            "products": len(prod),
            "productsWithCost": sum(1 for x in prod if x["hasCost"]),
            "productsWithStock": sum(1 for x in prod if x["hasStock"]),
            "customers": len(cust),
            "suppliers": len(supp),
            "sales": len(sales),
            "invoices": len(invoices),
        },
    }
