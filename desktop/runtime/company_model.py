"""VANOVA PROACTIVA — modelo estructurado de la empresa.

Construye una comprensión de la empresa a partir del modelo canónico
(ventas, productos, clientes, findings) y la guarda en config (``companyModel``)
como memoria empresarial. Incluye:

* qué vende (categorías, productos principales/secundarios/poca actividad);
* cómo vende (volumen, revenue, ticket medio, frecuencia, concentración);
* qué funciona (estrellas, en crecimiento, en caída);
* riesgos y oportunidades (top findings activos del detection engine);
* qué sabe y qué NO sabe (dataAvailability + dataMissing explícitos);
* cambios desde el último análisis (delta) para el reanálisis inteligente.

Reglas de honestidad (heredadas del benchmark): nunca inventar una dimensión;
si no hay datos → None/UNKNOWN con motivo explícito; los totales SIEMPRE vienen
de business_model (misma validez que el resto del producto).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import business_model

MODEL_KEY = "companyModel"
MODEL_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(v: Any) -> float | None:
    return business_model._as_float(v)


def _valid_sales(data: dict[str, Any]) -> list[dict[str, Any]]:
    sales = data.get("organizedSales") or []
    return [s for s in sales if isinstance(s, dict) and business_model.is_valid_sale(s)]


def _valid_products(data: dict[str, Any]) -> list[dict[str, Any]]:
    products = data.get("organizedProducts") or []
    return [p for p in products if isinstance(p, dict) and not business_model.is_error_payload(p)]


def _valid_customers(data: dict[str, Any]) -> list[dict[str, Any]]:
    customers = data.get("organizedCustomers") or []
    return [c for c in customers if isinstance(c, dict)]


def _line_sku_total(line: dict[str, Any]) -> tuple[str | None, float]:
    """Importe de una línea canónica de venta (price × quantity). Si la línea
    no trae precio ni SKU, devuelve (None, 0.0) — nunca se inventa."""
    sku = str(line.get("sku") or line.get("variant_id") or "").strip()
    qty = _as_float(line.get("quantity")) or 1.0
    price = _as_float(line.get("price"))
    total = (price or 0.0) * qty
    return (sku.lower() if sku else None), total


def _sale_sku_total(sale: dict[str, Any]) -> tuple[str | None, float]:
    """SKU e importe de una venta. Soporta DOS formas reales:
      * fila plana de CSV (sku a nivel de pedido) — una línea;
      * pedido de tienda con `line_items` (Shopify/Woo/Presta) — agrega todas
        las líneas, porque en los datos reales el SKU solo vive en line_items.
    Devuelve (None, 0.0) si la venta no aporta ningún SKU (UNKNOWN ≠ 0)."""
    lines = business_model.normalize_sale_lines(sale)
    if not lines:
        sku = str(sale.get("sku") or sale.get("product_sku") or "").strip()
        total = _as_float(sale.get("total"))
        return (sku.lower() if sku else None), (total or 0.0)
    if len(lines) == 1 and not str(lines[0].get("sku") or "").strip():
        sku = str(sale.get("sku") or sale.get("product_sku") or "").strip()
        total = _as_float(sale.get("total"))
        return (sku.lower() if sku else None), (total or 0.0)
    total_sum = 0.0
    sku_found = None
    for li in lines:
        sku, line_total = _line_sku_total(li)
        if sku:
            if sku_found is None:
                sku_found = sku
            total_sum += line_total
    return sku_found, total_sum


def _product_aggregates(sales: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Revenue/unidades por SKU desde las líneas canónicas de las ventas
    (line_items o fila plana). Si las ventas no aportan SKU, no se inventa:
    solo catálogo (productBasis = "catalog-only")."""
    agg: dict[str, dict[str, Any]] = {}
    for s in sales:
        for li in business_model.normalize_sale_lines(s):
            sku, line_total = _line_sku_total(li)
            if not sku or line_total is None:
                continue
            row = agg.setdefault(sku, {"sku": sku, "revenue": 0.0, "orders": 0, "units": 0.0})
            row["revenue"] += line_total
            row["orders"] += 1
            row["units"] += _as_float(li.get("quantity")) or 1.0
    for row in agg.values():
        row["revenue"] = round(row["revenue"], 2)
        row["units"] = round(row["units"], 2)
    return agg


def _trend(sales: list[dict[str, Any]], ref: datetime) -> dict[str, Any]:
    """Crecimiento del catálogo por SKU: ventana reciente vs anterior (mismas
    semanas de duración). Solo SKUs con ventas en ambas ventanas. None si no
    hay evidencia (UNKNOWN ≠ 0)."""
    from datetime import timedelta

    ref_date = ref.date()
    recent_lo = ref_date - timedelta(days=7)
    recent_hi = ref_date
    prev_hi = recent_lo - timedelta(days=1)
    prev_lo = prev_hi - timedelta(days=6)

    def _win(lo, hi) -> dict[str, float]:
        out: dict[str, float] = {}
        for s in sales:
            d = business_model._sale_date(s)
            if d is None or not (lo <= d <= hi):
                continue
            for li in business_model.normalize_sale_lines(s):
                sku, line_total = _line_sku_total(li)
                if sku and line_total is not None:
                    out[sku] = out.get(sku, 0.0) + line_total
        return out

    recent = _win(recent_lo, recent_hi)
    prev = _win(prev_lo, prev_hi)
    trends: list[dict[str, Any]] = []
    for sku, cur in recent.items():
        base = prev.get(sku)
        if base is None or base <= 0:
            continue
        pct = round((cur - base) / base * 100, 1)
        trends.append({"sku": sku, "revenue": round(cur, 2), "prevRevenue": round(base, 2), "changePct": pct})
    trends.sort(key=lambda t: abs(t["changePct"] or 0), reverse=True)
    return {"windowDays": 7, "items": trends}


def _customer_concentration(sales: list[dict[str, Any]]) -> dict[str, Any]:
    by_customer: dict[str, float] = {}
    for s in sales:
        name = str(s.get("customer") or s.get("customerName") or "").strip()
        if not name or name == "—":
            continue
        total = _as_float(s.get("total"))
        if total is not None:
            by_customer[name] = by_customer.get(name, 0.0) + total
    if not by_customer:
        return {"topShare": None, "topCustomer": None, "customers": 0}
    total = sum(by_customer.values())
    top_name, top_rev = max(by_customer.items(), key=lambda kv: kv[1])
    return {
        "topShare": round(top_rev / total * 100, 1) if total else None,
        "topCustomer": top_name,
        "customers": len(by_customer),
    }


def _data_availability(data: dict[str, Any], products: list[dict[str, Any]],
                       sales: list[dict[str, Any]]) -> dict[str, Any]:
    from . import product_identity

    with_cost = [
        p for p in products
        if product_identity.cost_available(p) and _as_float(p.get("rrp")) is not None
    ]
    has_stock = any(str(p.get("stock") or "").strip() not in ("", "—", "?", "N/A", "0")
                    for p in products)
    invoices = data.get("organizedInvoices") or []
    suppliers = data.get("organizedSuppliers") or []
    return {
        "hasProducts": len(products) > 0,
        "hasSales": len(sales) > 0,
        "hasCustomers": len(_valid_customers(data)) > 0 or any(
            str(s.get("customer") or "").strip() and str(s.get("customer") or "").strip() != "—"
            for s in sales
        ),
        "hasCosts": len(with_cost) > 0,
        "costCoverage": round(len(with_cost) / len(products) * 100, 1) if products else None,
        "hasStock": has_stock,
        "hasInvoices": len([i for i in invoices if isinstance(i, dict)]) > 0,
        "hasSuppliers": len([s for s in suppliers if isinstance(s, dict)]) > 0,
    }


def _missing(data_avail: dict[str, Any], products: list[dict[str, Any]],
             sales: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not data_avail["hasSales"]:
        missing.append("No tengo ventas para analizar los ingresos.")
    if not data_avail["hasProducts"]:
        missing.append("No tengo catálogo de productos.")
    if not data_avail["hasCosts"]:
        missing.append("No tengo costes de producto suficientes para evaluar el margen con confianza.")
    elif data_avail["costCoverage"] is not None and data_avail["costCoverage"] < 60:
        missing.append(
            f"Solo tengo coste verificado para el {data_avail['costCoverage']:.0f}% del catálogo; "
            "el margen agregado es parcial."
        )
    if not data_avail["hasStock"]:
        missing.append("No tengo datos de inventario/stock por producto.")
    if not data_avail["hasInvoices"]:
        missing.append("No tengo facturas para analizar la tesorería.")
    if not data_avail["hasSuppliers"]:
        missing.append("No tengo datos de proveedores.")
    # Ventas sin SKU (ni en la fila ni en line_items) → no se puede desglosar
    # el revenue por producto desde las ventas. UNKNOWN ≠ 0: se declara, no se
    # inventa un desglose.
    if data_avail["hasSales"] and not any(
        str(li.get("sku") or "").strip()
        for s in sales for li in business_model.normalize_sale_lines(s)
    ):
        missing.append("Tus ventas no traen SKU; no puedo desglosar el revenue por producto desde las ventas.")
    return missing


def _findings_summary(data: dict[str, Any]) -> dict[str, Any]:
    findings = data.get("businessFindings") or []
    if not isinstance(findings, list):
        findings = []
    active = [f for f in findings if isinstance(f, dict) and f.get("status") not in ("resolved", "archived")]
    problems = [f for f in active if f.get("category") == "problem"]
    opportunities = [f for f in active if f.get("category") == "opportunity"]
    positives = [f for f in active if f.get("category") == "positive"]

    def _top(items: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
        items = sorted(
            items,
            key=lambda f: (int(f.get("confidenceRank") or 0) * 100 + abs(int(f.get("economicImpact") or 0) or 0)),
            reverse=True,
        )
        return [
            {
                "id": f.get("id"),
                "type": f.get("type"),
                "severity": f.get("severity"),
                "title": f.get("title") or f.get("finding_type") or "",
                "entity": f.get("entity"),
                "economicImpact": f.get("economicImpact"),
                "confidence": f.get("confidence"),
                "confidenceRank": f.get("confidenceRank"),
                "recommendedAction": f.get("recommendedAction") or "",
                "detectedAt": f.get("createdAt") or f.get("detectedAt"),
            }
            for f in items[:n]
        ]

    return {
        "counts": {"problems": len(problems), "opportunities": len(opportunities), "positive": len(positives)},
        "topRisks": _top(problems),
        "topOpportunities": _top(opportunities),
    }


def build_company_model(data: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Construye el modelo estructurado de la empresa. NO persiste (el caller
    decide); devuelve el modelo completo con delta vs el guardado anterior."""
    if data is None:
        from . import config_store

        data = config_store.load()
    ref = now or datetime.now(timezone.utc)
    products = _valid_products(data)
    sales = _valid_sales(data)
    customers = _valid_customers(data)

    periods = business_model.period_revenue(sales, now=ref)
    total = periods["total"]
    product_agg = _product_aggregates(sales)

    top_products = sorted(product_agg.values(), key=lambda r: r["revenue"], reverse=True)
    concentration_products = {
        "topShare": round(top_products[0]["revenue"] / total["revenue"] * 100, 1)
        if top_products and total["revenue"] else None,
        "topSku": top_products[0]["sku"] if top_products else None,
        "productsWithSales": len(top_products),
    } if product_agg else {"topShare": None, "topSku": None, "productsWithSales": 0}
    customer_conc = _customer_concentration(sales)

    trend = _trend(sales, ref)
    trend_by_sku = {t["sku"]: t for t in trend["items"]}
    growing = [t for t in trend["items"] if (t["changePct"] or 0) >= 20][:5]
    declining = [t for t in trend["items"] if (t["changePct"] or 0) <= -20][:5]

    # Productos de catálogo sin actividad en ventas (o sin SKU en ventas).
    sales_skus = set(product_agg.keys())
    catalog_by_sku = {str(p.get("sku") or "").strip().lower(): p for p in products if str(p.get("sku") or "").strip()}
    low_activity = [
        {
            "sku": sku,
            "name": str(p.get("name") or sku),
            "rrp": _as_float(p.get("rrp")),
        }
        for sku, p in catalog_by_sku.items()
        if sku not in sales_skus
    ][:10]

    data_avail = _data_availability(data, products, sales)
    missing = _missing(data_avail, products, sales)

    category_counts: dict[str, int] = {}
    for p in products:
        cat = str(p.get("category") or p.get("type") or "").strip()
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    model = {
        "modelVersion": MODEL_VERSION,
        "builtAt": _now(),
        "company": {
            # BUG-002: una unica fuente de verdad para el nombre de empresa. El
            # nombre vive en companyProfile.identity.name (lo mismo que usa
            # business_scanner para overview.companyName). Antes solo se miraba
            # `companyName` (top-level) o `companyProfile.name` (que no existe:
            # el nombre esta en `.identity.name`), por lo que companyModel
            # quedaba "" y divergia del dashboard.
            "name": str(
                data.get("companyName")
                or ((data.get("companyProfile") or {}).get("identity") or {}).get("name")
                or (data.get("companyProfile") or {}).get("name")
                or ""
            ),
        },
        "revenuePeriods": periods,
        "summary": {
            "revenue": total["revenue"],
            "orders": total["orders"],
            "avgTicket": total["avgTicket"],
            "products": len(products),
            "customers": len(customers) or customer_conc.get("customers", 0),
        },
        "whatSells": {
            "categories": [{"category": k, "products": v} for k, v in sorted(category_counts.items(), key=lambda kv: -kv[1])],
            "topProducts": top_products[:10],
            "lowActivity": low_activity,
            "productBasis": "sales-with-sku" if product_agg else "catalog-only",
        },
        "productPerformance": {
            "growing": growing,
            "declining": declining,
            "trend": {"windowDays": trend["windowDays"], "items": trend["items"][:10]},
        },
        "concentration": {
            "products": concentration_products,
            "customers": customer_conc,
        },
        "findings": _findings_summary(data),
        "dataAvailability": data_avail,
        "dataMissing": missing,
        "lastAnalysisAt": _now(),
    }
    # El delta compara el modelo NUEVO con el guardado anterior (memoria). Se
    # añade después de construir el dict — nunca dentro de su propio literal
    # (referencia a la variable antes de asignarse → UnboundLocalError).
    model["changesSinceLast"] = _delta_vs_stored(data, model)
    return model


def _delta_vs_stored(data: dict[str, Any], new_model: dict[str, Any]) -> dict[str, Any]:
    """Cambios relevantes vs el modelo guardado anterior (reanálisis
    inteligente: qué cambió desde el último análisis)."""
    prev = data.get(MODEL_KEY) or {}
    if not isinstance(prev, dict):
        prev = {}
    changes: list[dict[str, str]] = []

    def _num(path: str, src: dict) -> Any:
        cur = src
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    def _fmt(v: Any) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return str(v)

    pairs = [
        ("summary.revenue", "Ingresos totales"),
        ("summary.orders", "Pedidos totales"),
        ("summary.avgTicket", "Ticket medio"),
        ("summary.products", "Productos"),
        ("findings.counts.problems", "Problemas detectados"),
        ("findings.counts.opportunities", "Oportunidades detectadas"),
    ]
    for path, label in pairs:
        before = _num(path, prev)
        after = _num(path, new_model)
        if before is None and after is None:
            continue
        if before != after:
            changes.append({
                "metric": label,
                "before": _fmt(before),
                "after": _fmt(after),
                "kind": "metric",
            })

    # Variación del periodo: nueva información sobre el mes actual.
    try:
        pv = (prev.get("revenuePeriods") or {}).get("month") or {}
        nv = (new_model.get("revenuePeriods") or {}).get("month") or {}
        if pv.get("revenue") != nv.get("revenue") and nv.get("revenue") is not None:
            changes.append({
                "metric": "Revenue del mes",
                "before": _fmt(pv.get("revenue")),
                "after": _fmt(nv.get("revenue")),
                "kind": "revenue_month",
            })
    except Exception:
        pass

    prev_top = {str(f.get("id")) for f in (prev.get("findings") or {}).get("topRisks", [])}
    new_top = {str(f.get("id")) for f in (new_model.get("findings") or {}).get("topRisks", [])}
    new_risk_ids = new_top - prev_top
    if new_risk_ids:
        changes.append({
            "metric": "Nuevos riesgos destacados",
            "before": f"{len(prev_top)}",
            "after": f"{len(new_top)}",
            "kind": "risks",
            "ids": sorted(new_risk_ids)[:5],
        })

    prev_missing = prev.get("dataMissing") or []
    new_missing = new_model.get("dataMissing") or []
    gained = set(prev_missing) - set(new_missing)
    if gained:
        changes.append({
            "metric": "Información ganada",
            "before": "faltaba",
            "after": "ahora disponible",
            "kind": "data",
            "items": sorted(gained)[:5],
        })

    return {"count": len(changes), "changes": changes}


def refresh(data: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    """Construye el modelo y lo persiste en config (memoria empresarial).
    Devuelve el modelo completo, incluido el delta vs el anterior."""
    from . import config_store

    if data is None:
        data = config_store.load()
    model = build_company_model(data, now=now)
    try:
        config_store.save({MODEL_KEY: model})
    except Exception:
        pass
    return model


def load_stored(data: dict[str, Any] | None = None) -> dict[str, Any]:
    if data is None:
        from . import config_store

        data = config_store.load()
    model = data.get(MODEL_KEY)
    return model if isinstance(model, dict) else {}
