"""Agent data tools — the single source of truth agents consult.

Every agent (Tareas, Hermes chat, routines) reads business data through this
layer, which reads the SAME persisted state the Dashboard renders
(config_store ``organizedProducts`` / ``organizedSales`` + file inventory).
There is exactly one source of truth: files -> Hermes processing -> normalized
rows in config_store -> this module -> Dashboard AND agents.

Tools (exposed over /api/agent/data/<tool>):
  get_products()                 all product rows
  get_product_by_sku(sku)        one product + derived margin
  get_product_prices(sku)        cost (netPrice) + sale (rrp) + margin
  get_inventory()                stock columns when the source has them
  get_sales(start, end)          order rows (alias get_orders)
  get_orders(start, end)         alias of get_sales
  get_product_performance()      units/revenue per SKU from sales data
  get_uploaded_files()           imported/scanned files
  get_imported_dataset(dataset)  'products' | 'sales' full rows

``availability()`` reports exactly which datasets exist — agents must state
what is missing instead of asking the user to re-upload what already exists.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from . import business_model, config_store, file_inventory
from .logger import get_logger

log = get_logger("maios.agent.data", "agent-data")

# Safety cap only: tools return the FULL real dataset — silently truncating
# the catalog would make agents present partial data as complete (H1).
# Display-level truncation lives in render_context_block(); data tools never
# cap real business scale (20k rows >> any pyme catalog/order history).
MAX_DATA_ROWS = 20_000

TOOL_NAMES = (
    "get_products",
    "get_product_by_sku",
    "get_product_prices",
    "get_inventory",
    "get_sales",
    "get_orders",
    "get_customers",
    "get_product_performance",
    "get_uploaded_files",
    "get_imported_dataset",
    "get_invoices",
    "get_invoice_lines",
    "get_treasury",
    "get_suppliers",
    "get_profitability",
    "get_finance_overview",
    "get_business_findings",
    "get_product_reconciliation",
    "get_cost_coverage",
    "get_identity_coverage",
    "data_availability",
)

TOOL_DOCS: dict[str, str] = {
    "get_products": "Todos los productos (name, sku, netPrice=coste, rrp=PVD/venta).",
    "get_product_by_sku": "Un producto por SKU + margen calculado (netPrice vs rrp).",
    "get_product_prices": "Coste (netPrice) y venta (rrp) de un SKU + margen.",
    "get_inventory": "Columnas de stock existentes en el catálogo (si las hay).",
    "get_sales": "Pedidos/ventas (order id, cliente, total, fecha) con filtro opcional por fechas.",
    "get_orders": "Alias de get_sales.",
    "get_customers": "Clientes normalizados (nombre, contacto, país/provincia si existen, pedidos y gasto).",
    "get_product_performance": "Unidades y facturación por SKU a partir de los datos de ventas.",
    "get_invoices": "Facturas de FacturaScripts (emitidas y recibidas) con importes, pagadas/pendientes y vencimientos.",
    "get_invoice_lines": "Líneas de factura (SKU, cantidad, precio, descuento, IVA) con la relación resuelta a producto y coste cuando el SKU existe.",
    "get_treasury": "Tesorería: cobros y pagos REALES de FacturaScripts + derivados CALCULADOS (pendientes, vencimientos 30d, movimiento neto de caja) + saldo bancario NO DISPONIBLE.",
    "get_suppliers": "Proveedores sincronizados desde FacturaScripts.",
    "get_profitability": "Rentabilidad por producto, pedido y período: revenue, coste, margen (sobre venta) y markup (sobre coste) SIEMPRE separados. Coste resuelto SOLO con identidad + coste verificado.",
    "get_finance_overview": "Panorama financiero canónico: facturas, líneas, tesorería categorizada, reconciliación y rentabilidad — todo del modelo central.",
    "get_business_findings": "Hallazgos del motor de detección empresarial (problemas/oportunidades/positivos) con evidencia, confianza e impacto estimado. NO inventes hallazgos: usa esta tool.",
    "get_product_reconciliation": "Conciliación de identidad producto: cuántos SKUs de venta tienen match con el catálogo, por qué método (sku/barcode/variant_id/manual), cuántos requieren revisión y cuáles están huérfanos.",
    "get_cost_coverage": "Qué porcentaje del REVENUE tiene coste verificado/importado (identidad + coste real). Si es bajo, el margen no es calculable: dilo con estos números.",
    "get_identity_coverage": "Qué porcentaje del REVENUE y de las líneas tiene identidad de producto fiable contra el catálogo.",
    "get_uploaded_files": "Archivos importados/escaneados (categoría productos/ventas).",
    "get_imported_dataset": "Dataset completo: 'products' o 'sales'.",
    "data_availability": "Qué datasets existen y cuántas filas tiene cada uno.",
}


# --------------------------------------------------------------------------
# Lectura desde la fuente de verdad (la misma que usa el Dashboard)
# --------------------------------------------------------------------------

def _products() -> list[dict[str, Any]]:
    from .file_organizer import _is_product_entity

    rows = config_store.load().get("organizedProducts") or []
    if not isinstance(rows, list):
        rows = []
    return [p for p in rows if _is_product_entity(p)][:MAX_DATA_ROWS]


def _sales() -> list[dict[str, Any]]:
    rows = config_store.load().get("organizedSales") or []
    if not isinstance(rows, list):
        rows = []
    return [s for s in rows if isinstance(s, dict)][:MAX_DATA_ROWS]


def _files() -> list[dict[str, Any]]:
    info = file_inventory.list_imported_files()
    return info.get("files") or []


def _customers() -> list[dict[str, Any]]:
    from .file_organizer import get_customers

    rows = get_customers().get("customers") or []
    return rows[:MAX_DATA_ROWS] if isinstance(rows, list) else []


# --------------------------------------------------------------------------
# Herramientas
# --------------------------------------------------------------------------

def availability() -> dict[str, Any]:
    products = _products()
    sales = _sales()
    customers = _customers()
    files = _files()
    from . import product_identity

    with_cost = [p for p in products if product_identity.cost_available(p)]
    with_rrp = [p for p in products if isinstance(p.get("rrp"), (int, float))]
    with_stock = [
        p for p in products
        if p.get("stock") not in (None, "", 0) or p.get("stockQty") not in (None, "", 0)
    ]
    sales_with_date = [s for s in sales if str(s.get("date") or "") not in ("", "—")]
    return {
        "products": {
            "available": bool(products),
            "count": len(products),
            "withCostPrice": len(with_cost),
            "withVerifiedCost": sum(1 for p in products if product_identity.resolve_cost(p).get("costStatus") == "verified"),
            "withMissingCost": sum(1 for p in products if product_identity.resolve_cost(p).get("costStatus") == "missing"),
            "withSalePrice": len(with_rrp),
            "withStock": len(with_stock),
            "sampleSkus": [p.get("sku") for p in products[:5] if p.get("sku")],
        },
        "sales": {
            "available": bool(sales),
            "count": len(sales),
            "withDate": len(sales_with_date),
            "revenue": _revenue(sales),
        },
        "customers": {
            "available": bool(customers),
            "count": len(customers),
            "withEmail": sum(1 for c in customers if c.get("email")),
        },
        "files": {
            "available": bool(files),
            "count": len(files),
            "productFiles": sum(1 for f in files if f.get("category") == "products"),
            "salesFiles": sum(1 for f in files if f.get("category") == "sales"),
        },
    }


def get_products() -> dict[str, Any]:
    rows = _products()
    return {"ok": True, "count": len(rows), "products": rows}


def get_product_by_sku(sku: str) -> dict[str, Any]:
    sku = (sku or "").strip().lower()
    if not sku:
        return {"ok": False, "error": "Falta el parámetro sku"}
    for p in _products():
        if str(p.get("sku") or "").strip().lower() == sku:
            return {"ok": True, "product": _with_margin(p)}
    return {"ok": False, "error": f"No existe ningún producto con SKU {sku!r}"}


def get_product_prices(sku: str) -> dict[str, Any]:
    result = get_product_by_sku(sku)
    if not result.get("ok"):
        return result
    p = result["product"]
    from . import product_identity

    rc = product_identity.resolve_cost(p)
    return {
        "ok": True,
        "sku": p.get("sku"),
        "name": p.get("name"),
        "costPrice": rc.get("cost") if rc.get("costStatus") in ("verified", "imported") else None,
        "costStatus": rc.get("costStatus"),
        "costSource": rc.get("costSource"),
        "salePrice": p.get("rrp"),
        "margin": p.get("margin"),
        "marginPct": p.get("marginPct"),
        "markupPct": p.get("markupPct"),
    }


def get_product_reconciliation() -> dict[str, Any]:
    """FASE 11 — conciliación de identidad de producto (P4)."""
    from . import product_identity

    data = config_store.load()
    products = data.get("organizedProducts") or []
    sales = data.get("organizedSales") or []
    return {"ok": True, **product_identity.build_reconciliation(products, sales)}


def get_cost_coverage() -> dict[str, Any]:
    """FASE 11 — qué parte del revenue tiene coste verificado (P7)."""
    from . import product_identity

    data = config_store.load()
    return {"ok": True, **product_identity.cost_coverage(
        data.get("organizedSales") or [],
        data.get("organizedProducts") or [],
    )}


def get_identity_coverage() -> dict[str, Any]:
    """FASE 11 — qué parte del revenue tiene identidad fiable (P8)."""
    from . import product_identity

    data = config_store.load()
    return {"ok": True, **product_identity.identity_coverage(
        data.get("organizedSales") or [],
        data.get("organizedProducts") or [],
    )}


def get_inventory() -> dict[str, Any]:
    rows = []
    for p in _products():
        stock = p.get("stock")
        if stock in (None, "", 0):
            stock = p.get("stockQty")
        if stock in (None, "", 0):
            continue
        rows.append({"sku": p.get("sku"), "name": p.get("name"), "stock": stock})
    return {"ok": True, "count": len(rows), "inventory": rows}


def get_sales(start: str = "", end: str = "") -> dict[str, Any]:
    rows = _sales()
    if start or end:
        rows = [s for s in rows if _in_range(s.get("date") or "", start, end)]
    return {"ok": True, "count": len(rows), "sales": rows, "summary": _sales_summary(rows)}


def get_orders(start: str = "", end: str = "") -> dict[str, Any]:
    return get_sales(start=start, end=end)


def get_customers() -> dict[str, Any]:
    rows = _customers()
    return {"ok": True, "count": len(rows), "customers": rows}


def get_product_performance() -> dict[str, Any]:
    """Units + revenue per SKU, derived from the sales dataset when it carries
    a product/sku column or per-order `line_items` (Shopify). If sales lack
    per-SKU detail, report honestly."""
    sales = _sales()
    if not sales:
        return {"ok": True, "count": 0, "performance": [], "note": "Sin datos de ventas"}
    by_sku: dict[str, dict[str, Any]] = {}
    from_line_items = False
    for s in sales:
        lines = s.get("line_items")
        if isinstance(lines, list) and lines:
            from_line_items = True
            for li in lines:
                sku = str(li.get("sku") or li.get("product") or "").strip()
                if not sku:
                    continue
                qty = li.get("quantity") if isinstance(li.get("quantity"), (int, float)) else 1
                price = li.get("price") if isinstance(li.get("price"), (int, float)) else None
                row = by_sku.setdefault(
                    sku.lower(),
                    {"sku": sku, "name": li.get("title") or sku, "units": 0, "revenue": 0.0},
                )
                row["units"] += int(qty or 1)
                if price is not None:
                    row["revenue"] += float(price) * int(qty or 1)
            continue
        sku = str(s.get("sku") or s.get("product_sku") or s.get("product") or "").strip()
        qty = s.get("qty") if isinstance(s.get("qty"), (int, float)) else 1
        total = s.get("total") if isinstance(s.get("total"), (int, float)) else 0.0
        if not sku:
            continue
        row = by_sku.setdefault(sku.lower(), {"sku": sku, "name": sku, "units": 0, "revenue": 0.0})
        row["units"] += int(qty or 1)
        row["revenue"] += float(total or 0.0)
    if not by_sku:
        return {
            "ok": True,
            "count": 0,
            "performance": [],
            "note": "Los pedidos no llevan SKU por línea — no puedo desglosar ventas por producto.",
        }
    # FASE 12 (H21): ordenar por revenue descendente — el "top ventas" debe
    # ser realmente el top, no el orden de inserción de los dicts.
    performance = sorted(by_sku.values(), key=lambda r: (r["revenue"], r["units"]), reverse=True)
    result: dict[str, Any] = {"ok": True, "count": len(by_sku), "performance": performance}
    if from_line_items:
        result["source"] = "line_items de pedidos"
    return result


def get_invoices(kind: str = "", start: str = "", end: str = "") -> dict[str, Any]:
    """Facturas desde el modelo financiero de VANOVA (FacturaScripts).
    kind: "issued" (emitidas), "received" (recibidas) o vacío (todas)."""
    rows = config_store.load().get("organizedInvoices") or []
    if not isinstance(rows, list):
        rows = []
    rows = [r for r in rows if business_model.validate_invoice(r)[0]]
    kind = (kind or "").strip().lower()
    if kind in ("issued", "emitidas", "emitida"):
        rows = [r for r in rows if r.get("type") == "issued"]
    elif kind in ("received", "recibidas", "recibida"):
        rows = [r for r in rows if r.get("type") == "received"]
    if start or end:
        rows = [r for r in rows if _in_range(r.get("date") or "", start, end)]
    issued = [r for r in rows if r.get("type") == "issued"]
    received = [r for r in rows if r.get("type") == "received"]
    return {
        "ok": True,
        "count": len(rows),
        "invoices": rows,
        "source": "facturascript",
        "summary": {
            "issued": len(issued),
            "received": len(received),
            "issuedTotal": _revenue(issued),
            "receivedTotal": _revenue(received),
            "pendingCollections": sum(
                r.get("total", 0) for r in issued if not r.get("paid") and isinstance(r.get("total"), (int, float))
            ),
        },
    }


def get_treasury() -> dict[str, Any]:
    """Tesorería categorizada: REAL (cobros/pagos), CALCULADO (pendientes,
    vencimientos, movimiento neto) y NO DISPONIBLE (saldo bancario). Nunca se
    mezclan categorías."""
    from .facturascripts_sync import treasury_summary

    t = treasury_summary()
    if not t.get("available"):
        return {"ok": True, "available": False, "note": "Sin datos de tesorería de FacturaScripts todavía", "categories": []}
    return {"ok": True, "available": True, "treasury": t, "categories": ["real", "calculated", "not_available"]}


def get_invoice_lines() -> dict[str, Any]:
    """Líneas de factura con relación resuelta a producto (por SKU, nunca por
    nombre). Las líneas sin producto asociado se declaran explícitamente."""
    data = config_store.load()
    lines = data.get("organizedInvoiceLines") or []
    if not isinstance(lines, list):
        lines = []
    lines = [l for l in lines if business_model.validate_invoice_line(l)[0]]
    products = data.get("organizedProducts") or []
    resolved: list[dict[str, Any]] = []
    matched = unmatched = 0
    for line in lines:
        rel = business_model.resolve_line_product(line, products)
        row = dict(line)
        row.update(rel)
        if rel.get("productMatched"):
            matched += 1
        else:
            unmatched += 1
        resolved.append(row)
    return {
        "ok": True,
        "count": len(resolved),
        "lines": resolved,
        "source": "facturascript",
        "relations": {"matchedToProduct": matched, "unmatched": unmatched},
        "rules": "asociación por SKU/referencia; sin SKU o sin match → productMatched=false (nunca por nombre)",
    }


def get_profitability() -> dict[str, Any]:
    """Rentabilidad por producto/pedido/período. Margen (sobre venta) y markup
    (sobre coste) SIEMPRE separados; coste del catálogo; sin coste → se declara."""
    report = business_model.profitability()
    return {"ok": True, **report}


def get_business_findings(status: str = "") -> dict[str, Any]:
    """FASE 8 — hallazgos del motor determinista (no inventados por el LLM)."""
    from .detection_engine import list_findings

    return list_findings(status=status)


def get_finance_overview() -> dict[str, Any]:
    """Panorama financiero canónico del modelo central — lo que consume el
    dashboard y Hermes por la misma vía."""
    data = config_store.load()
    from .facturascripts_sync import treasury_summary

    invoices = data.get("organizedInvoices") or []
    if not isinstance(invoices, list):
        invoices = []
    invoices = [i for i in invoices if business_model.validate_invoice(i)[0]]
    issued = [i for i in invoices if i.get("type") == "issued"]
    received = [i for i in invoices if i.get("type") == "received"]
    treasury = treasury_summary()
    return {
        "ok": True,
        "fetchedAt": _now(),
        "invoices": {
            "issued": len(issued),
            "received": len(received),
            "issuedTotal": _revenue(issued),
            "receivedTotal": _revenue(received),
        },
        "treasury": treasury if treasury.get("available") else None,
        "reconciliation": data.get("financialReconciliation"),
        "source": "modelo canónico VANOVA",
    }


def get_suppliers() -> dict[str, Any]:
    rows = config_store.load().get("organizedSuppliers") or []
    if not isinstance(rows, list):
        rows = []
    rows = [r for r in rows if business_model.validate_customer(r)[0]]
    return {"ok": True, "count": len(rows), "suppliers": rows, "source": "facturascript"}


def get_uploaded_files() -> dict[str, Any]:
    files = _files()
    return {"ok": True, "count": len(files), "files": files}


def get_imported_dataset(dataset: str) -> dict[str, Any]:
    dataset = (dataset or "").strip().lower()
    if dataset in ("products", "productos", "product"):
        return get_products()
    if dataset in ("sales", "ventas", "orders", "pedidos"):
        return get_sales()
    if dataset in ("customers", "clientes", "customer", "client"):
        return get_customers()
    if dataset in ("files", "archivos", "file"):
        return get_uploaded_files()
    return {"ok": False, "error": f"Dataset desconocido: {dataset!r} (usa 'products' o 'sales')"}


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def _with_margin(p: dict[str, Any]) -> dict[str, Any]:
    # FASE 3: canonical margin (marginPct on sale price) — single implementation.
    return business_model.with_margin(p)


def _revenue(sales: list[dict[str, Any]]) -> float | None:
    return business_model.revenue(sales)


def _sales_summary(sales: list[dict[str, Any]]) -> dict[str, Any]:
    # FASE 3: same summary the dashboard uses — Hermes and the UI can never
    # diverge on orders/revenue/margin again.
    return business_model.sales_summary(sales)


def _in_range(value: str, start: str, end: str) -> bool:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            d = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except ValueError:
            return True  # fecha desconocida: no filtrar
    if start:
        try:
            if d < datetime.fromisoformat(start):
                return False
        except ValueError:
            pass
    if end:
        try:
            if d > datetime.fromisoformat(end):
                return False
        except ValueError:
            pass
    return True


# --------------------------------------------------------------------------
# Inyección en el contexto de los agentes (prompt)
# --------------------------------------------------------------------------

def _question_domain(message: str) -> str:
    """MEGA UPDATE (A6) — clasifica el dominio de la pregunta para seleccionar
    el contexto. Conservador: si no hay coincidencia clara devuelve 'general'
    (contexto completo). Los dominios product/stock mantienen las filas de
    producto; customer/supplier/finance las omiten (ruido para esas preguntas).
    Regla anti-FP: una pregunta ambigua NUNCA se trunca."""
    m = (message or "").lower().strip()
    if not m:
        return "general"
    if any(k in m for k in ("cliente", "clientes", "customer", "customers", "comprador", "recurrent", "retencion", "retención", "churn", "fidel")):
        return "customer"
    if any(k in m for k in ("proveedor", "proveedores", "supplier", "suppliers", "compras a", "negocia", "renegocia", "dependencia de proveedor")):
        return "supplier"
    if any(k in m for k in ("tesorer", "caja", "cobro", "cobros", "pago", "pagos", "liquidez", "cash", "gasto", "gastos", "finanza", "finanzas", "factura", "facturas", "impuesto", "deuda")):
        return "finance"
    if any(k in m for k in ("stock", "inventario", "rotación", "rotacion", "inmoviliz", "quedarme sin")):
        return "stock"
    if any(k in m for k in ("producto", "productos", "sku", "vend", "margen", "vende", "venden", "vender")):
        return "product"
    return "general"


def render_context_block(limit: int = 30, precomputed_coverage: dict[str, Any] | None = None, domain: str = "general") -> str:
    """Compact text block with REAL rows + explicit availability, injected into
    agent prompts so they never claim data is missing when it exists.

    ``precomputed_coverage`` ({"cc": …, "ic": …}) evita recalcular dos veces
    las coberturas de coste/identidad cuando el llamador (build del contexto
    de Hermes) ya las calculó; en ese caso tampoco se repite la línea CALIDAD
    DE DATOS porque el llamador ya la escribió.

    MEGA UPDATE (A6): ``domain`` selecciona las secciones relevantes a la
    pregunta. customer/supplier/finance omiten las filas de producto (30 filas
    de ruido para una pregunta de clientes) pero conservan el resto del bloque
    (ventas, clientes, financiero, motor de detección) y su resumen empresarial
    (BUSINESS HEALTH + TOP RISKS + OPORTUNIDADES). stock/product/general =
    contexto completo."""
    av = availability()
    lines: list[str] = ["[DATOS REALES DE VANOVA — usa estas filas; NO pidas al usuario que suba archivos que ya existen]"]

    prods = _products()
    lines.append(f"- Productos: {len(prods)} filas "
                 f"(con coste: {av['products']['withCostPrice']}, con PVD: {av['products']['withSalePrice']})")
    show_product_rows = domain in ("general", "product", "stock")
    if prods and show_product_rows:
        shown = prods[:limit]
        for p in shown:
            net = p.get("netPrice")
            rrp = p.get("rrp")
            net_s = f"{net:.2f}" if isinstance(net, (int, float)) else "?"
            rrp_s = f"{rrp:.2f}" if isinstance(rrp, (int, float)) else "?"
            lines.append(f"  * {p.get('sku') or '—'} | {p.get('name') or ''} | coste={net_s} | PVD={rrp_s}")
        if len(prods) > limit:
            lines.append(f"  … y {len(prods) - limit} productos más (consulta get_products()).")
    elif prods and not show_product_rows:
        lines.append("  … filas por producto disponibles vía get_products() si las necesitas.")

    # FASE 12 (P10): revenue por producto en el contexto — sin esto Hermes no
    # podía responder "¿qué productos venden más?" y decía que no tenía el dato
    # aunque la tool get_product_performance lo devuelve (misma clase que H19).
    try:
        if show_product_rows:
            perf = get_product_performance()
            top = (perf.get("performance") or [])[:10]
            if top:
                lines.append("- Top ventas por producto (revenue de líneas de pedido):")
                for t in top:
                    lines.append(
                        f"  * {t.get('sku') or '—'} | {str(t.get('name') or '')[:60]} | "
                        f"{t.get('units')} uds | {t.get('revenue')} €"
                    )
                if perf.get("count") and perf["count"] > len(top):
                    lines.append(f"  … y {perf['count'] - len(top)} más (consulta get_product_performance()).")
    except Exception:
        pass

    # FASE 11 — calidad de datos: cobertura de coste e identidad (P7/P8/P10)
    # FASE HERMES (P1): si el llamador ya calculó las coberturas, se reutilizan
    # (evita el doble cálculo) y no se repite la línea porque el llamador ya la
    # escribió en su bloque CALIDAD DE DATOS.
    try:
        from . import product_identity

        if precomputed_coverage and precomputed_coverage.get("cc") is not None and precomputed_coverage.get("ic") is not None:
            cc = precomputed_coverage["cc"]
            ic = precomputed_coverage["ic"]
        else:
            sales_rows = _sales()
            cc = product_identity.cost_coverage(sales_rows, prods)
            ic = product_identity.identity_coverage(sales_rows, prods)
            _rev_ok = float(cc.get('revenueWithVerifiedCost') or 0.0)
            _rev_miss = float(cc.get('revenueWithMissingCost') or 0.0)
            _total_rev = round(_rev_ok + _rev_miss, 2)
            lines.append(
                f"- CALIDAD DE DATOS: revenue con coste real {cc.get('coveragePct')}% "
                f"({_rev_ok:.2f}€ de {_total_rev:.2f}€; {cc.get('productsCoveragePct')}% de los productos tienen coste — "
                "bases distintas); "
                f"identidad de producto {ic.get('coveragePct')}% del revenue ("
                f"{ic.get('matchedLines')} líneas con match / {ic.get('unmatchedLines')} sin match). "
                "Sin coste verificado → el margen NO es calculable; dilo con estos números, nunca inventes un coste."
            )
    except Exception:
        pass

    sales = _sales()
    lines.append(f"- Ventas/pedidos: {len(sales)} filas (con fecha: {av['sales']['withDate']})")
    if sales:
        shown = sales[:5]
        for s in shown:
            lines.append(
                f"  * {s.get('order_id') or s.get('order') or s.get('id') or '—'} | "
                f"{s.get('customer') or '—'} | {s.get('total') if s.get('total') is not None else '?'} | {s.get('date') or '—'}"
            )
        if len(sales) > 5:
            lines.append(f"  … y {len(sales) - 5} pedidos más (consulta get_sales()).")

    if av["sales"]["available"] and av["sales"]["withDate"] == 0:
        lines.append("- NOTA: hay pedidos pero SIN fecha por fila — no puedo agrupar ventas por día.")
    if not av["sales"]["available"]:
        lines.append("- NOTA: no existen datos de ventas históricas todavía (dilo si te lo preguntan).")

    customers = _customers()
    lines.append(f"- Clientes normalizados: {len(customers)} filas (con email: {av['customers']['withEmail']})")

    # FASE 8 / FASE B — hallazgos del motor de detección PERSISTIDOS.
    # Una sola lectura, reutilizada por el resumen ejecutivo (render_business_brief)
    # y por el resumen por categoría. El contexto NUNCA re-ejecuta run_detection:
    # eso recomputaría data_quality/coberturas (ya calculadas arriba) y sería un
    # doble trabajo por cada request de Hermes.
    try:
        from .detection_engine import list_findings

        fz = list_findings()
    except Exception:
        fz = {"findings": []}

    # FASE B — BUSINESS HEALTH + TOP RISKS + OPORTUNIDADES (evidencia, no opinión)
    try:
        lines.extend(render_business_brief(fz))
    except Exception:
        pass

    try:
        active = [f for f in fz.get("findings") or [] if f.get("status") not in ("resolved", "archived")]
        if active:
            probs = sum(1 for f in active if f.get("category") == "problem")
            opps = sum(1 for f in active if f.get("category") == "opportunity")
            pos = sum(1 for f in active if f.get("category") == "positive")
            lines.append(
                f"- Motor de detección (persistido): {probs} problema(s), {opps} oportunidad(es), {pos} positivo(s)."
            )
    except Exception:
        pass

    # FASE 4+ — modelo financiero (FacturaScripts) cuando existe
    try:
        from .facturascripts_sync import sync_status as _fs_status, treasury_summary as _fs_treasury

        fs = _fs_status()
        if fs.get("configured") and fs.get("ok") and fs.get("counts"):
            c = fs["counts"]
            parts = []
            if c.get("invoices"):
                parts.append(f"{c.get('invoices')} facturas")
            if c.get("lines"):
                parts.append(f"{c.get('lines')} líneas")
            if c.get("collections"):
                parts.append(f"{c.get('collections')} cobros")
            if c.get("payments"):
                parts.append(f"{c.get('payments')} pagos")
            if parts:
                lines.append(f"- FacturaScripts sincronizado: {', '.join(parts)} (consulta get_invoices / get_invoice_lines / get_treasury / get_suppliers / get_profitability).")
            t = _fs_treasury()
            if t.get("available"):
                m = t["metrics"]
                pc = m.get("pendingCollections") or {}
                pd = m.get("upcomingDue") or {}
                nm = m.get("netCashMovement") or {}
                lines.append(
                    f"- Tesorería (FacturaScripts): pendiente de cobro {pc.get('value')}€ ({pc.get('count')} facturas, CÁLCULO); "
                    f"vencimientos 30d {pd.get('value')}€; movimiento neto caja {nm.get('value')}€ (CÁLCULO; saldo bancario NO DISPONIBLE)."
                )
        elif fs.get("configured") and fs.get("error"):
            lines.append(f"- FacturaScripts configurado pero su última sync falló: {fs.get('error')[:120]}")
    except Exception:
        pass

    lines.append(
        "- Herramientas internas disponibles: get_products, get_product_by_sku, "
        "get_product_prices, get_inventory, get_sales, get_orders, get_customers, "
        "get_product_performance, get_invoices, get_invoice_lines, get_treasury, "
        "get_suppliers, get_profitability, get_finance_overview, get_product_reconciliation, "
        "get_cost_coverage, get_identity_coverage, get_uploaded_files, "
        "get_imported_dataset. Si necesitas un dato que no está arriba, dilo y VANOVA "
        "lo consultará por ti."
    )
    lines.append(
        "- REGLA: responde con los datos de arriba. Si algo no existe de verdad "
        "(p. ej. ventas por fecha), di exactamente qué falta; nunca pidas que te "
        "vuelvan a subir un archivo que VANOVA ya ha importado."
    )
    return "\n".join(lines)


def render_business_brief(findings: dict[str, Any] | None = None) -> list[str]:
    """FASE B — resumen empresarial estructurado para el contexto de Hermes:
    BUSINESS HEALTH (métricas clave) + TOP CLIENTES + PROVEEDORES + TOP RISKS
    + OPPORTUNITIES, derivado de las señales y de los hallazgos PERSISTIDOS del
    motor (evidencia, no opinión).

    El motor de detección se ejecuta y persiste en /api/business/analyze (botón
    de análisis del dashboard); este bloque SOLO LEE los hallazgos persistidos
    vía ``findings``/list_findings() — nunca re-ejecuta run_detection, para no
    recomputar coberturas ni duplicar trabajo en cada request de Hermes.

    FASE B (anti-inundación + cobertura): los riesgos se agrupan POR TIPO para
    que el contexto muestre una muestra diversificada (margen, stock,
    proveedores, clientes, gastos...) en vez de N hallazgos del mismo tipo que
    desplazarían a los demás (p. ej. 6 sobrestock ocultando el hallazgo de
    proveedor o de cliente)."""
    lines: list[str] = []
    try:
        from . import business_signals, detection_engine

        signals = business_signals.compute_signals()
        fin = signals.get("finance") or {}
        counts = signals.get("counts") or {}
        lines.append("- BUSINESS HEALTH:")
        lines.append(
            f"  · Revenue (ventas): {fin.get('revenue')} € · Gastos (compras facturadas): {fin.get('expenses')} € "
            f"· Margen bruto: {fin.get('marginPct')}%"
        )
        lines.append(
            f"  · Pendiente de cobro: {fin.get('pendingCollections')} € · Pendiente de pago: {fin.get('pendingPayments')} €"
        )
        lines.append(
            f"  · Productos con stock: {counts.get('productsWithStock')}/{counts.get('products')} · "
            f"Clientes: {counts.get('customers')} · Proveedores: {counts.get('suppliers')}"
        )

        # Agregación por cliente/proveedor — Hermes la necesita para responder
        # "¿quiénes son mis mejores clientes?" / "¿qué proveedor me cuesta más?"
        # sin una cadena de tools.
        customers = signals.get("customers") or []
        if customers:
            lines.append("- TOP CLIENTES (por revenue):")
            for c in customers[:3]:
                days = c.get("daysSinceLastOrder")
                days_s = f"{days}d" if isinstance(days, int) else "?"
                lines.append(
                    f"  · {c.get('name')} — {c.get('revenue')} € ({c.get('orders')} pedidos, "
                    f"{round((c.get('revenueShare') or 0) * 100, 1)}% del revenue, última compra hace {days_s})"
                )
        suppliers = signals.get("suppliers") or []
        if suppliers:
            lines.append("- PROVEEDORES (por gasto):")
            for s in suppliers[:3]:
                lines.append(
                    f"  · {s.get('name')} — {s.get('spend')} € ({s.get('invoices')} facturas, "
                    f"{round((s.get('spendShare') or 0) * 100, 1)}% del gasto)"
                )

        # Hallazgos PERSISTIDOS del motor, agrupados por tipo (evidencia + acción).
        if findings is None:
            findings = detection_engine.list_findings()
        active = [f for f in (findings.get("findings") or []) if f.get("status") not in ("resolved", "archived")]

        # MEGA UPDATE (A11): brief ejecutivo del motor — salud + dinero en
        # riesgo + mayor problema/oportunidad, para que Hermes responda
        # "¿cuánto dinero está en riesgo? / ¿cuál es el mayor problema?" con
        # las cifras YA calculadas (nunca las inventa el LLM).
        #
        # El brief llega en el payload de list_findings (que ya computó
        # coberturas); NO se recalcula aquí para no romper el contrato de
        # precomputed_coverage ni duplicar data_quality por build.
        try:
            eb = (findings or {}).get("executiveBrief")
            if eb and eb.get("ok"):
                risk_txt = f"{eb['moneyAtRisk']:,.2f} €" if eb.get("moneyAtRisk") else "sin importe cuantificado"
                lines.append(
                    f"- SALUD GENERAL: {eb.get('healthLabel')} ({eb.get('health')}). "
                    f"Dinero en riesgo por problemas activos: {risk_txt}. "
                )
                tp = eb.get("topProblem")
                if tp:
                    lines.append(f"  · MAYOR PROBLEMA: {tp.get('title')} — {tp.get('observation')}")
                to = eb.get("topOpportunity")
                if to:
                    lines.append(f"  · MAYOR OPORTUNIDAD: {to.get('title')} — {to.get('observation')}")
                mi = eb.get("missingInfo") or []
                if mi:
                    lines.append(f"  · PARA ANALIZAR MEJOR FALTA: {' '.join(mi)}")
        except Exception:
            pass
        problems = _top_per_type([f for f in active if f.get("category") == "problem"], per_type=2, max_total=10)
        opportunities = _top_per_type([f for f in active if f.get("category") == "opportunity"], per_type=2, max_total=6)

        if problems:
            lines.append("- TOP RISKS (agrupados por tipo, con evidencia e impacto €):")
            for f in problems:
                value = _economic_value(f)
                value_txt = f" · Impacto ~{value:,.0f} €" if value > 0 else ""
                lines.append(
                    f"  · [{f.get('type')}] {f.get('title')} — {f.get('observation')}{value_txt} "
                    f"Acción: {f.get('recommendedAction')}"
                )
        if opportunities:
            lines.append("- OPORTUNIDADES (con impacto € estimado):")
            for f in opportunities:
                value = _economic_value(f)
                value_txt = f" · Potencial ~{value:,.0f} €" if value > 0 else ""
                lines.append(
                    f"  · [{f.get('type')}] {f.get('title')} — {f.get('observation')}{value_txt} "
                    f"Acción: {f.get('recommendedAction')}"
                )
        # FASE C (B9) — DATA QUALITY: salud de los datos preservados.
        # Resume por tipo los hallazgos de calidad (duplicados, sin SKU, sin
        # coste, pedidos incoherentes) para que Hermes pueda afirmar QUÉ no es
        # fiable sin inventar cifras ni ocultar la revisión pendiente.
        quality_findings = [f for f in active if f.get("type") in (
            "duplicate_sku", "missing_sku", "duplicate_customer",
            "missing_cost", "inconsistent_order_total",
        )]
        if quality_findings:
            lines.append("- DATA QUALITY (anomalías preservadas, no borradas):")
            q_by_type: dict[str, list[dict[str, Any]]] = {}
            for f in quality_findings:
                q_by_type.setdefault(f.get("type") or "other", []).append(f)
            type_label = {
                "duplicate_sku": "SKU duplicados", "missing_sku": "Productos sin SKU",
                "duplicate_customer": "Clientes duplicados", "missing_cost": "Productos sin coste",
                "inconsistent_order_total": "Pedidos con total incoherente",
            }
            for qtype, fs in q_by_type.items():
                title = type_label.get(qtype, qtype)
                lines.append(f"  · {title}: {len(fs)} ({fs[0].get('title')})")
            lines.append("  · Regla: los registros afectados están marcados NEEDS_REVIEW; no usarlos para márgenes ni decisiones hasta revisar.")
        if not active:
            lines.append("- Motor de detección: sin hallazgos persistidos (ejecuta el análisis de negocio).")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"- BUSINESS HEALTH no disponible en este momento ({exc}).")
    return lines


def _economic_value(f: dict[str, Any]) -> float:
    """MEGA UPDATE (A4): valor económico de un finding para ordenar por impacto.
    Extrae economicImpactEuro / inventoryValue / revenueAtRisk / marginPotential
    del impacto o las métricas; 0 si no hay cifra (UNKNOWN ≠ 0: no se fabrica)."""
    imp = f.get("estimatedImpact") or {}
    for key in ("economicImpactEuro", "inventoryValue", "revenueAtRisk", "marginPotential"):
        v = imp.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    metrics = f.get("metrics") or {}
    for key in ("economicImpactEuro", "inventoryValue", "revenueAtRisk", "marginPotential", "extraCostEuro"):
        v = metrics.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return 0.0


def _business_score(f: dict[str, Any]) -> float:
    """Score de prioridad = impacto € (si lo hay) × confianza × severidad.
    Sin cifra económica, se usa la severidad como señal débil (evita ordenar
    por capricho). El score es relativo, nunca se muestra al usuario."""
    value = _economic_value(f)
    conf = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(str(f.get("confidence") or "medium"), 0.7)
    sev = {"high": 1.5, "medium": 1.0, "low": 0.6}.get(str(f.get("severity") or "medium"), 1.0)
    if value > 0:
        # Escala log para que 10.000€ no aplaste 500€ pero el orden sea real.
        return (1.0 + value / 1000.0) * conf * sev
    return sev * conf * 0.5


def _top_per_type(findings: list[dict[str, Any]], per_type: int = 2, max_total: int = 10) -> list[dict[str, Any]]:
    """Agrupa findings por tipo y devuelve los ``per_type`` de MAYOR VALOR
    ECONÓMICO de cada tipo, con un máximo global. Así el contexto muestra una
    muestra DIVERSIFICADA (margen, stock, proveedores, clientes, gastos...) en
    vez de N hallazgos del mismo tipo, priorizando los que más dinero implican.
    MEGA UPDATE (A4): dentro de cada tipo se ordena por _business_score (impacto
    € × confianza × severidad), no solo por severidad."""
    by_type: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        by_type.setdefault(f.get("type") or "other", []).append(f)
    ordered_types = sorted(
        by_type,
        key=lambda t: max(_business_score(f) for f in by_type[t]),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for t in ordered_types:
        fs = sorted(by_type[t], key=_business_score, reverse=True)
        out.extend(fs[:per_type])
        if len(out) >= max_total:
            break
    return out


def _sev_rank(sev: str | None) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(sev or "", 0)


def tool_manifest() -> list[dict[str, str]]:
    return [{"name": n, "description": TOOL_DOCS[n]} for n in TOOL_NAMES]


def call_tool(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    try:
        if name == "data_availability":
            return {"ok": True, "availability": availability()}
        if name == "get_products":
            return get_products()
        if name in ("get_product_by_sku", "get_product_prices"):
            return globals()[name](str(params.get("sku") or ""))
        if name in ("get_sales", "get_orders"):
            return get_sales(start=str(params.get("start") or ""), end=str(params.get("end") or ""))
        if name == "get_customers":
            return get_customers()
        if name == "get_product_performance":
            return get_product_performance()
        if name == "get_inventory":
            return get_inventory()
        if name == "get_invoices":
            return get_invoices(
                kind=str(params.get("kind") or ""),
                start=str(params.get("start") or ""),
                end=str(params.get("end") or ""),
            )
        if name == "get_treasury":
            return get_treasury()
        if name == "get_suppliers":
            return get_suppliers()
        if name == "get_invoice_lines":
            return get_invoice_lines()
        if name == "get_profitability":
            return get_profitability()
        if name == "get_finance_overview":
            return get_finance_overview()
        if name == "get_business_findings":
            return get_business_findings(status=str(params.get("status") or ""))
        if name == "get_product_reconciliation":
            return get_product_reconciliation()
        if name == "get_cost_coverage":
            return get_cost_coverage()
        if name == "get_identity_coverage":
            return get_identity_coverage()
        if name == "get_uploaded_files":
            return get_uploaded_files()
        if name == "get_imported_dataset":
            return get_imported_dataset(str(params.get("dataset") or ""))
    except Exception as exc:  # noqa: BLE001
        log.warning("tool %s failed: %s", name, exc)
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": f"Herramienta desconocida: {name}"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
