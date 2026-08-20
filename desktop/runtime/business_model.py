"""VANOVA canonical business model — FASE 3.

Single source of truth for entity shape, validation and derived metrics.

* Every dataset stored in config_store must pass through the validators here,
  so an integration error can never become a business entity (products like
  "Faltan permisos de Shopify" are rejected at the model boundary, not by
  string-matching a handful of known messages).
* Margin, revenue and summary math live HERE and only here. The dashboard,
  Hermes and the analytics layer consume the same numbers — no more
  "el dashboard dice €X y Hermes dice €Y" because two modules compute
  independently.
* Provenance: entities carry ``_source``, ``_fetchedAt``, ``_updatedAt`` and
  ``_validated`` so every datum can answer: where does it come from, when was
  it obtained/updated, was it validated? Whether a value is real data, a
  calculation, an inference or a recommendation stays explicit in tool payloads
  and reports (the "NO INVENTAR" rule).

Margin definition (canonical, accounting standard):
  marginPct  = (rrp - net) / rrp * 100   → gross margin ON SALE PRICE
  markupPct  = (rrp - net) / net * 100   → markup ON COST
  margin     = rrp - net                  → absolute gross margin
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp(entity: dict[str, Any], source: str, fetched_at: str | None = None) -> dict[str, Any]:
    """Attach provenance to a raw entity before it enters the model."""
    row = dict(entity)
    ts = fetched_at or _now()
    row["_source"] = source
    row["_fetchedAt"] = ts
    row["_updatedAt"] = ts
    row["_validated"] = True
    return row


def mark_updated(entity: dict[str, Any], updated_at: str | None = None) -> dict[str, Any]:
    row = dict(entity)
    row["_updatedAt"] = updated_at or _now()
    return row


# ---------------------------------------------------------------------------
# Validation — error payloads never become business entities
# ---------------------------------------------------------------------------

# Payload shapes that are clearly diagnostics, not business rows.
_META_ONLY_KEYS = {"status", "error", "message", "detail", "errors", "exception", "traceback", "ok", "success"}

_ERROR_TEXT_MARKERS = (
    "faltan permisos",
    "no se pudieron descargar",
    "shopify conectado pero faltan",
    "error de permisos",
    "error de conexion",
    "api error",
    "http 40",
    "http 50",
    "connection error",
    "timeout",
    "no responde",
    "invalid credentials",
    "unable to",
    "failed to",
)


def is_error_payload(row: Any) -> bool:
    """Return True when a row is an integration error/diagnostic, not a real
    business entity. Works for ANY integration — it does not depend on a list
    of known messages."""
    if not isinstance(row, dict):
        return False
    name = str(row.get("name") or row.get("description") or row.get("title") or row.get("message") or "")
    lower = name.lower()
    if any(marker in lower for marker in _ERROR_TEXT_MARKERS):
        return True
    keys = set(row.keys())
    if keys and keys.issubset(_META_ONLY_KEYS):
        return True
    return False


def _as_float(value: Any) -> float | None:
    """VANOVA 3.0 (auditoría): NaN/Inf y cadenas ambiguas NUNCA se convierten en
    un número — se declaran UNKNOWN (None). Un total de venta no puede ser
    nan/inf aunque el float parse con éxito."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        if result != result or result in (float("inf"), float("-inf")):
            return None
        return result
    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        if normalized.count(".") > 1:
            parts = normalized.split(".")
            last = parts[-1]
            int_parts = parts[:-1]
            middle = int_parts[1:]
            # Solo formato europeo de miles: 1.234,56 -> 1234.56. Cualquier
            # patrón ambiguo (10.5.5) es UNKNOWN, nunca un número adivinado.
            if not (1 <= len(last) <= 2
                    and int_parts and 1 <= len(int_parts[0]) <= 3
                    and all(p and len(p) == 3 and p.isdigit() for p in middle)
                    and all(p.isdigit() for p in int_parts)):
                return None
            # Quitar los separadores de miles (puntos) conservando el decimal.
            normalized = int_parts[0] + "".join(middle) + "." + last
        try:
            result = float(normalized)
        except ValueError:
            return None
        if result != result or result in (float("inf"), float("-inf")):
            return None
        return result
    return None


def normalize_sale_lines(sale: dict[str, Any]) -> list[dict[str, Any]]:
    """FASE 13 (P8): normaliza las líneas de un pedido a un formato canónico
    de línea (sku/variant_id/quantity/price/title).

    Soporta DOS formas:
      * pedido con `line_items` (Shopify, WooCommerce, PrestaShop)
      * fila plana de CSV/Excel con sku/qty/total a nivel de pedido → se
        convierte en UNA línea canónica (un SKU por fila).

    Así el core (profitability, detección, métricas) trata EXACTAMENTE igual
    un pedido de Shopify que una fila de un CSV antiguo."""
    lines = sale.get("line_items")
    if isinstance(lines, list) and lines:
        return [li for li in lines if isinstance(li, dict)]
    sku = str(sale.get("sku") or sale.get("product_sku") or sale.get("product") or "").strip()
    if not sku:
        return []
    qty = _as_float(sale.get("quantity") or sale.get("qty") or sale.get("units")) or 1.0
    total = _as_float(sale.get("total"))
    price = total / qty if total is not None and qty else total
    return [{
        "sku": sku,
        "title": str(sale.get("productName") or sale.get("product_name") or sale.get("name") or sku),
        "quantity": qty,
        "price": price,
        "variant_id": str(sale.get("variant_id") or "").strip() or None,
    }]


def validate_product(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "no es un dict"
    if is_error_payload(row):
        return False, "payload de error de integración"
    name = str(row.get("name") or "").strip()
    if not name:
        return False, "falta el nombre"
    if not (str(row.get("sku") or "").strip() or name):
        return False, "sin identidad (sku/nombre)"
    net = _as_float(row.get("netPrice"))
    rrp = _as_float(row.get("rrp"))
    for label, val in (("netPrice", net), ("rrp", rrp)):
        if val is None and str(row.get(label) or "").strip() not in ("", "—", "?", "N/A"):
            return False, f"{label} no es numérico"
    return True, ""


def validate_sale(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "no es un dict"
    if is_error_payload(row):
        return False, "payload de error de integración"
    ident = str(row.get("order_id") or row.get("order") or row.get("id") or "").strip()
    total = _as_float(row.get("total"))
    if not ident and total is None:
        return False, "sin id de pedido ni importe"
    if total is None and str(row.get("total") or "").strip() not in ("", "—", "?", "N/A"):
        return False, "total no numérico"
    return True, ""


def validate_customer(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "no es un dict"
    if is_error_payload(row):
        return False, "payload de error de integración"
    if not (
        str(row.get("name") or "").strip()
        or str(row.get("email") or "").strip()
        or str(row.get("taxId") or row.get("cifnif") or "").strip()
    ):
        return False, "sin nombre, email ni NIF"
    return True, ""


def validate_invoice(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "no es un dict"
    if is_error_payload(row):
        return False, "payload de error de integración"
    if not str(row.get("id") or row.get("code") or "").strip():
        return False, "sin id ni código de factura"
    if row.get("type") not in ("issued", "received"):
        return False, "tipo de factura desconocido"
    if _as_float(row.get("total")) is None:
        return False, "total no numérico"
    return True, ""


def validate_cash_row(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "no es un dict"
    if is_error_payload(row):
        return False, "payload de error de integración"
    if row.get("type") not in ("collection", "payment"):
        return False, "tipo de movimiento desconocido"
    if _as_float(row.get("amount")) is None:
        return False, "importe no numérico"
    return True, ""


# ---------------------------------------------------------------------------
# Canonical derived metrics — ONE implementation for the whole product
# ---------------------------------------------------------------------------


def margin(net: Any, rrp: Any) -> dict[str, Any]:
    """Canonical margin. Returns explicit, non-ambiguous fields:
    margin (abs), marginPct (ON SALE PRICE) and markupPct (ON COST)."""
    net_f = _as_float(net)
    rrp_f = _as_float(rrp)
    if net_f is None or rrp_f is None:
        return {"margin": None, "marginPct": None, "markupPct": None}
    diff = round(rrp_f - net_f, 2)
    return {
        "margin": diff,
        "marginPct": round(diff / rrp_f * 100, 1) if rrp_f else None,
        "markupPct": round(diff / net_f * 100, 1) if net_f else None,
    }


def with_margin(product: dict[str, Any]) -> dict[str, Any]:
    """Attach canonical margin fields to a product row.

    FASE 11: el coste se resuelve por ``product_identity.resolve_cost`` — si el
    producto no tiene coste VERIFICADO/importado con evidencia (p. ej.
    netPrice == rrp sin fuente), el margen es ``None`` con ``costStatus``
    explícito. Un PVD nunca se usa como coste real.
    """
    row = dict(product)
    from . import product_identity

    rc = product_identity.resolve_cost(product)
    row["costStatus"] = rc.get("costStatus") or "missing"
    row["costSource"] = rc.get("costSource") or "unknown"
    if rc.get("costStatus") in ("verified", "imported") and rc.get("cost") is not None:
        row.update(margin(rc["cost"], row.get("rrp")))
    else:
        row.update({"margin": None, "marginPct": None, "markupPct": None})
    return row


# Límite de plausibilidad por venta individual: ninguna PYME genera pedidos
# de >1 billón de euros; valores así casi siempre son errores de importación
# (puntos decimales mal puestos, ceros extra) que contaminarían las métricas.
_MAX_PLAUSIBLE_TOTAL = 1e12


def _sale_quarter(sale: dict[str, Any]) -> str | None:
    """Canonical quarter key (YYYY-Qn) for a sale, or None when the date is
    missing/unparseable. Same validity gate as _sale_date_key."""
    d = str(sale.get("date") or "").strip()
    if not d or d in ("—", "?"):
        return None
    try:
        dt = datetime.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return None
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


_date_key_cache: dict[str, str | None] = {}


def _sale_date_key(sale: dict[str, Any]) -> str | None:
    """Normalized YYYY-MM date key of a sale, or None when the date is missing
    or impossible/unparseable. Single implementation shared by the summary, the
    period breakdown and revenue validity — a row can never be "in the year"
    for one metric and "invalid" for another.

    Memoizado por string de fecha: con 100k ventas evitamos cientos de miles de
    parses datetime (fromisoformat + strftime dominaban /api/sales)."""
    d = str(sale.get("date") or "").strip()
    if not d or d in ("—", "?"):
        return None
    hit = _date_key_cache.get(d)
    if hit is not None:
        return hit
    try:
        result = datetime.fromisoformat(d[:10]).strftime("%Y-%m")
    except (ValueError, TypeError):
        result = None
    # Cache acotado para no crecer sin límite con datasets de fechas únicas.
    if len(_date_key_cache) < 100_000:
        _date_key_cache[d] = result
    return result


def sale_validation_issue(sale: dict[str, Any]) -> str | None:
    """Human-readable reason why a sale row is NOT financially valid, or None
    when it can be used. A row is valid only when it is a real entity with a
    numeric, non-negative total and a parseable date — rows that cannot be
    determined valid are excluded from financial metrics (UNKNOWN ≠ 0, never
    invented)."""
    if not isinstance(sale, dict) or is_error_payload(sale):
        return "fila de error de integración"
    total = _as_float(sale.get("total"))
    if total is None:
        raw = str(sale.get("total") or "").strip()
        if raw and raw not in ("", "—", "?", "N/A"):
            return "total no numérico"
        return "falta el importe (total)"
    if total < 0:
        return "total negativo"
    # VANOVA 3.0 (red team): un importe absurdo (p.ej. 1e+20 €) no es una venta
    # plausible y destrozaría el revenue y todos los periodos. No se inventa ni
    # se borra: la fila pasa a revisión con evidencia y queda fuera de métricas.
    if total > _MAX_PLAUSIBLE_TOTAL:
        return "total fuera de rango plausible (>1e12 €)"
    if _sale_date_key(sale) is None:
        return "fecha inválida o ausente"
    return None


def is_valid_sale(sale: dict[str, Any]) -> bool:
    """A sale row is financially valid when it passes ``sale_validation_issue``.
    Used by revenue()/sales_summary() so total and period breakdowns share the
    exact same inclusion criteria."""
    return sale_validation_issue(sale) is None


def revenue(sales: list[dict[str, Any]]) -> float | None:
    """Canonical total revenue over a sales list (single implementation). Only
    financially valid rows contribute: rows with impossible dates, non-numeric
    or negative totals never inflate revenue."""
    totals = [_as_float(s.get("total")) for s in sales if is_valid_sale(s)]
    return round(sum(totals), 2) if totals else None


_sale_date_cache: dict[str, Any] = {}
_sale_week_cache: dict[str, str | None] = {}


def _sale_date(sale: dict[str, Any]) -> Any | None:
    """datetime.date of a sale, or None when missing/impossible. Memoizado por
    string de fecha (period_revenue recorre datasets grandes)."""
    from datetime import date

    d = str(sale.get("date") or "").strip()
    if not d or d in ("—", "?"):
        return None
    hit = _sale_date_cache.get(d)
    if hit is not None:
        return hit
    try:
        result = datetime.fromisoformat(d[:10]).date()
    except (ValueError, TypeError):
        result = None
    if len(_sale_date_cache) < 100_000:
        _sale_date_cache[d] = result
    return result


def _sale_year_key(sale: dict[str, Any]) -> str | None:
    """Año (YYYY) de una venta, o None. Comparte el cache de fechas — sin
    parse extra."""
    d = _sale_date(sale)
    return str(d.year) if d is not None else None


def _sale_week_key(sale: dict[str, Any]) -> str | None:
    """ISO week key (YYYY-Www) of a sale's date, or None. Semana natural
    (lunes a domingo) — "esta semana" vs "semana anterior" usan la misma
    clave, así la comparación es homogénea."""
    d = str(sale.get("date") or "").strip()
    if not d or d in ("—", "?"):
        return None
    hit = _sale_week_cache.get(d)
    if hit is not None:
        return hit
    try:
        iso = datetime.fromisoformat(d[:10]).date().isocalendar()
        result = f"{iso[0]}-W{iso[1]:02d}"
    except (ValueError, TypeError):
        result = None
    if len(_sale_week_cache) < 100_000:
        _sale_week_cache[d] = result
    return result


def _period_bucket(rows: list[dict[str, Any]], key_fn, keys: set[str] | None) -> tuple[float | None, int]:
    """(revenue, orders) de las filas cuya clave está en `keys` (o todas si
    keys es None). Solo filas ya validadas por el caller.

    UNKNOWN ≠ 0: si el bucket NO tiene filas (p. ej. no hay datos del periodo
    anterior, o la sincronización aún no cubre hoy), el revenue es None, no 0 €
    — un periodo sin datos no es un periodo con cero ventas."""
    rev = 0.0
    n = 0
    for s in rows:
        k = key_fn(s)
        if keys is None or (k is not None and k in keys):
            t = _as_float(s.get("total"))
            if t is not None:
                rev += t
                n += 1
    return (round(rev, 2) if n else None), n


def _period_block(revenue_now: float | None, orders_now: int,
                  revenue_prev: float | None, orders_prev: int) -> dict[str, Any]:
    """Bloque de periodo con comparación honesta: si el periodo anterior no
    tiene filas válidas o revenue 0, NO se inventa una variación —
    comparable=False ("Sin datos suficientes para comparar")."""
    comparable = (
        revenue_now is not None
        and revenue_prev is not None
        and revenue_prev > 0
    )
    change_pct = None
    if comparable and revenue_now is not None:
        change_pct = round((revenue_now - revenue_prev) / revenue_prev * 100, 1)
    avg_ticket = round(revenue_now / orders_now, 2) if (revenue_now is not None and orders_now) else None
    prev_avg = round(revenue_prev / orders_prev, 2) if (revenue_prev is not None and orders_prev) else None
    return {
        "revenue": revenue_now,
        "orders": orders_now,
        "avgTicket": avg_ticket,
        "prevRevenue": revenue_prev,
        "prevOrders": orders_prev,
        "prevAvgTicket": prev_avg,
        "changePct": change_pct,
        "comparable": comparable,
        "comparisonNote": None if comparable else "Sin datos suficientes para comparar",
    }


def period_revenue(sales: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """VANOVA PROACTIVA — revenue temporal canónico (hoy / semana / mes /
    trimestre / año / total), cada uno con su periodo anterior equivalente y
    variación % cuando hay evidencia suficiente.

    Mismo gate de validez que revenue()/sales_summary(): filas con fecha
    imposible, total no numérico o negativo NUNCA cuentan. Si el periodo
    anterior no tiene datos, comparable=False con note explícito (UNKNOWN ≠ 0).
    """
    from datetime import timedelta

    ref = now or datetime.now(timezone.utc)
    today = ref.date()
    iso = today.isocalendar()
    week_key = f"{iso[0]}-W{iso[1]:02d}"
    prev_week_date = today - timedelta(days=7)
    piso = prev_week_date.isocalendar()
    prev_week_key = f"{piso[0]}-W{piso[1]:02d}"
    month_key = ref.strftime("%Y-%m")
    prev_month_dt = datetime(ref.year - (1 if ref.month == 1 else 0), 12 if ref.month == 1 else ref.month - 1, 1)
    prev_month_key = prev_month_dt.strftime("%Y-%m")
    quarter_key = f"{ref.year}-Q{(ref.month - 1) // 3 + 1}"
    q_idx = (ref.month - 1) // 3
    prev_q_idx = q_idx - 1
    if prev_q_idx < 0:
        prev_q_year, prev_q = ref.year - 1, 3
    else:
        prev_q_year, prev_q = ref.year, prev_q_idx + 1
    prev_quarter_key = f"{prev_q_year}-Q{prev_q}"
    year_key = ref.strftime("%Y")
    prev_year_key = str(ref.year - 1)

    valid: list[dict[str, Any]] = [s for s in sales if is_valid_sale(s)]

    def _today(sale: dict[str, Any]) -> str | None:
        d = _sale_date(sale)
        return str(d) if d is not None else None

    today_rev, today_n = _period_bucket(valid, _today, {str(today)})
    prev_today_rev, prev_today_n = _period_bucket(valid, _today, {str(today - timedelta(days=1))})
    week_rev, week_n = _period_bucket(valid, _sale_week_key, {week_key})
    prev_week_rev, prev_week_n = _period_bucket(valid, _sale_week_key, {prev_week_key})
    month_rev, month_n = _period_bucket(valid, _sale_date_key, {month_key})
    prev_month_rev, prev_month_n = _period_bucket(valid, _sale_date_key, {prev_month_key})
    quarter_rev, quarter_n = _period_bucket(valid, _sale_quarter, {quarter_key})
    prev_quarter_rev, prev_quarter_n = _period_bucket(valid, _sale_quarter, {prev_quarter_key})
    year_rev, year_n = _period_bucket(valid, _sale_year_key, {year_key})
    prev_year_rev, prev_year_n = _period_bucket(valid, _sale_year_key, {prev_year_key})
    total_rev, total_n = _period_bucket(valid, _sale_date_key, None)

    return {
        "computedAt": ref.isoformat() if hasattr(ref, "isoformat") else _now(),
        "today": _period_block(today_rev, today_n, prev_today_rev, prev_today_n),
        "week": _period_block(week_rev, week_n, prev_week_rev, prev_week_n),
        "month": _period_block(month_rev, month_n, prev_month_rev, prev_month_n),
        "quarter": _period_block(quarter_rev, quarter_n, prev_quarter_rev, prev_quarter_n),
        "year": _period_block(year_rev, year_n, prev_year_rev, prev_year_n),
        "total": _period_block(total_rev, total_n, None, 0),
    }


def sales_summary(sales: list[dict[str, Any]], products: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """CANONICAL sales summary — used by the dashboard, Hermes tools and the
    integrity checks. Replaces the two independent implementations that used to
    live in file_organizer (rich) and agent_data_tools (minimal)."""
    rev: float | None = None
    now = datetime.now(timezone.utc)
    month_key = now.strftime("%Y-%m")
    year_key = now.strftime("%Y")

    # Una sola pasada de validación por fila (antes is_valid_sale se llamaba
    # dos veces por venta y _sale_date_key cinco veces — 500k parses de fecha).
    valid_sales: list[dict[str, Any]] = []
    valid_keys: dict[str, str | None] = {}
    for s in sales:
        key = _sale_date_key(s)
        total = _as_float(s.get("total"))
        ok = (
            isinstance(s, dict)
            and not is_error_payload(s)
            and total is not None
            and total >= 0
            and key is not None
            and total <= _MAX_PLAUSIBLE_TOTAL
        )
        if ok:
            valid_sales.append(s)
            valid_keys[id(s)] = key
    if valid_sales:
        rev = round(sum(_as_float(s.get("total")) or 0.0 for s in valid_sales), 2)

    def _period(sale: dict[str, Any]) -> str:
        return valid_keys.get(id(sale)) or ""

    month_rows = [s for s in valid_sales if _period(s) == month_key]
    year_rows = [s for s in valid_sales if _period(s).startswith(year_key)]
    quarter_key = f"{now.year}-Q{(now.month - 1) // 3 + 1}"
    quarter_rows = [s for s in valid_sales if _sale_quarter(s) == quarter_key]

    by_month: dict[str, float] = {}
    by_month_orders: dict[str, int] = {}
    for s in valid_sales:
        period = _period(s)
        if period and period.startswith(year_key):
            by_month[period] = by_month.get(period, 0.0) + (_as_float(s.get("total")) or 0.0)
            by_month_orders[period] = by_month_orders.get(period, 0) + 1

    # Gross margin from the product catalog (net cost vs sale price).
    # FASE 11: solo productos con coste VERIFICADO/importado — un catálogo con
    # coste == PVD (sin evidencia) no produce margen, se declara missing.
    if products is None:
        from . import config_store

        products = config_store.load().get("organizedProducts") or []
    from . import product_identity

    margin_products = [
        p for p in products
        if isinstance(p, dict) and not is_error_payload(p)
        and product_identity.cost_available(p)
        and _as_float(p.get("rrp")) is not None and _as_float(p.get("rrp")) > 0
    ]
    margin_pct: float | None = None
    margin_abs: float | None = None
    if margin_products:
        total_cost = sum(_as_float(product_identity.resolve_cost(p)["cost"]) or 0.0 for p in margin_products)
        total_rrp = sum(_as_float(p.get("rrp")) or 0.0 for p in margin_products)
        margin_abs = round(total_rrp - total_cost, 2)
        margin_pct = round((total_rrp - total_cost) / total_rrp * 100, 1) if total_rrp else None

    return {
        "orders": len(sales),  # pedidos físicos (una fila sin importe sigue siendo un pedido)
        "revenue": rev,
        "month": {
            "orders": len(month_rows),
            "revenue": round(sum(_as_float(s.get("total")) or 0.0 for s in month_rows), 2)
            if month_rows
            else None,
        },
        "quarter": {
            "orders": len(quarter_rows),
            "revenue": round(sum(_as_float(s.get("total")) or 0.0 for s in quarter_rows), 2)
            if quarter_rows
            else None,
        },
        "year": {
            "orders": len(year_rows),
            "revenue": round(sum(_as_float(s.get("total")) or 0.0 for s in year_rows), 2)
            if year_rows
            else None,
        },
        "byMonth": [
            {"period": k, "revenue": round(v, 2), "orders": by_month_orders.get(k, 0)}
            for k, v in sorted(by_month.items())
        ],
        "grossMarginPct": margin_pct,
        "grossMarginAbs": margin_abs,
        "grossMarginProducts": len(margin_products),
        "marginBasis": "catalog",  # derived from catalog costs, not per-unit sold
        "marginNote": (
            "Solo productos con coste verificado/importado (coste == PVD sin evidencia no cuenta)"
            if not margin_products
            else "Margen sobre catálogo con coste verificado"
        ),
    }


def dedupe(rows: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = key_fn(row)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Integrity — the model must never drift from its raw inputs
# ---------------------------------------------------------------------------


def _entity_key(dataset: str, row: dict[str, Any]) -> str:
    if dataset == "organizedProducts":
        return str(row.get("sku") or row.get("name") or "").strip().lower()
    if dataset in ("organizedSales", "sales"):
        return str(row.get("order_id") or row.get("order") or row.get("id") or "").strip().lower()
    if dataset in ("organizedCustomers", "customers"):
        return str(
            row.get("email") or row.get("taxId") or row.get("name") or ""
        ).strip().lower()
    if dataset in ("organizedInvoices", "invoices"):
        return str(row.get("id") or row.get("code") or "").strip().lower()
    if dataset in ("organizedFinance", "treasury"):
        return str(row.get("id") or "").strip().lower()
    return str(row.get("id") or row.get("name") or "").strip().lower()


def integrity_report(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cross-check the stored model: error-like entities, duplicates,
    incomplete records and aggregate-vs-raw reconciliation."""
    if data is None:
        from . import config_store

        data = config_store.load()
    issues: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    validators: dict[str, Callable[[Any], tuple[bool, str]]] = {
        "organizedProducts": validate_product,
        "organizedSales": validate_sale,
        "organizedCustomers": validate_customer,
        "organizedInvoices": validate_invoice,
        "organizedFinance": validate_cash_row,
    }

    for dataset, validator in validators.items():
        rows = data.get(dataset) or []
        if not isinstance(rows, list):
            issues.append({"severity": "high", "dataset": dataset, "detail": f"no es una lista ({type(rows).__name__})"})
            rows = []
        counts[dataset] = len(rows)
        # 1. corrupt / error-like entities
        for i, row in enumerate(rows):
            ok, reason = validator(row)
            if not ok:
                label = str(row.get("name") or row.get("id") or row.get("code") or f"fila {i}")
                issues.append({"severity": "high", "dataset": dataset, "detail": f"entidad inválida ({reason}): {label[:80]}"})
        # 2. duplicates
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _entity_key(dataset, row)
            if not key:
                continue
            if key in seen:
                issues.append({"severity": "medium", "dataset": dataset, "detail": f"duplicado: {key[:80]}"})
            seen.add(key)

    # 3. aggregate vs raw reconciliation
    sales = data.get("organizedSales") or []
    if isinstance(sales, list):
        summary = sales_summary(sales, products=data.get("organizedProducts") or [])
        snapshot = data.get("dashboardSnapshot") or {}
        if isinstance(snapshot, dict):
            overview = snapshot.get("overview") or {}
            if isinstance(overview, dict) and overview.get("revenue") is not None and summary.get("revenue") is not None:
                if abs(float(overview["revenue"]) - float(summary["revenue"])) > 0.01:
                    issues.append(
                        {
                            "severity": "high",
                            "dataset": "snapshot",
                            "detail": (
                                f"revenue del snapshot ({overview['revenue']}) ≠ suma real de ventas "
                                f"({summary['revenue']})"
                            ),
                        }
                    )
            if isinstance(overview, dict) and overview.get("orders") is not None and summary.get("orders") is not None:
                if int(overview["orders"]) != int(summary["orders"]):
                    issues.append(
                        {
                            "severity": "high",
                            "dataset": "snapshot",
                            "detail": (
                                f"pedidos del snapshot ({overview['orders']}) ≠ filas de ventas reales "
                                f"({summary['orders']})"
                            ),
                        }
                    )

    return {
        "ok": not any(i["severity"] == "high" for i in issues),
        "checkedAt": _now(),
        "issues": issues,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Líneas de factura (FASE 4+) y relaciones factura → línea → producto
# ---------------------------------------------------------------------------


def validate_invoice_line(row: Any) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "no es un dict"
    if is_error_payload(row):
        return False, "payload de error de integración"
    if not str(row.get("invoiceId") or "").strip():
        return False, "sin id de factura padre"
    if row.get("invoiceType") not in ("issued", "received"):
        return False, "tipo de factura desconocido"
    if _as_float(row.get("quantity")) is None:
        return False, "cantidad no numérica"
    return True, ""


def resolve_line_product(line: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    """Relación línea → producto por SKU/referencia (NUNCA por nombre).

    Reglas explícitas:
      * match por SKU/referencia (case-insensitive) contra el catálogo;
      * si no hay match → productMatched=False y motivo explícito (nunca se
        crea un producto fantasma ni se asocia por nombre);
      * el coste se resuelve del catálogo en el momento de consultar, así un
        cambio de precio se refleja sin re-sincronizar.
    """
    sku = str(line.get("sku") or "").strip()
    if not sku:
        return {"productMatched": False, "matchReason": "la línea no trae referencia/SKU"}
    key = sku.lower()
    from . import product_identity

    for p in products:
        if not isinstance(p, dict):
            continue
        if str(p.get("sku") or "").strip().lower() == key:
            rc = product_identity.resolve_cost(p)
            cost_ok = rc.get("costStatus") in ("verified", "imported")
            return {
                "productMatched": True,
                "sku": str(p.get("sku") or sku),
                "productName": str(p.get("name") or ""),
                "cost": rc.get("cost") if cost_ok else None,
                "costStatus": rc.get("costStatus") or "missing",
                "costSource": rc.get("costSource") or "unknown",
                "matchReason": "match por SKU",
            }
    return {"productMatched": False, "matchReason": f"no hay producto con SKU {sku!r} en el catálogo"}


# ---------------------------------------------------------------------------
# Reconciliación financiera (FASE 4+) — nunca corregir en silencio
# ---------------------------------------------------------------------------


def financial_reconciliation(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Comprueba matemáticamente que el modelo financiero tiene sentido.

    Regla: si hay discrepancia NO se corrige el dato — se registra qué no
    coincide, cuánto difiere, qué fuentes participan y la severidad.

    Chequeos:
      * Σ líneas ≈ neto de factura (por factura);
      * facturas sin líneas (dato incompleto, severidad baja);
      * Σ facturas emitidas del período ≈ ingresos de ventas del período
        (solo cuando ambas fuentes existen; es una comparación inter-fuente).
    """
    if data is None:
        from . import config_store

        data = config_store.load()
    items: list[dict[str, Any]] = []

    invoices = data.get("organizedInvoices") or []
    lines = data.get("organizedInvoiceLines") or []
    sales = data.get("organizedSales") or []
    if not isinstance(invoices, list):
        invoices = []
    if not isinstance(lines, list):
        lines = []
    if not isinstance(sales, list):
        sales = []

    by_invoice: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        if not isinstance(line, dict):
            continue
        key = f"{line.get('invoiceType')}:{line.get('invoiceId')}"
        by_invoice.setdefault(key, []).append(line)

    for inv in invoices:
        if not isinstance(inv, dict):
            continue
        inv_key = f"{inv.get('type')}:{inv.get('id')}"
        inv_lines = by_invoice.get(inv_key, [])
        if not inv_lines:
            items.append({
                "scope": "invoice_lines",
                "severity": "low",
                "detail": f"Factura {inv.get('code') or inv.get('id')} ({inv.get('type')}) sin líneas sincronizadas",
                "sources": ["facturascript"],
            })
            continue
        line_total = sum(_as_float(l.get("lineTotal")) or 0 for l in inv_lines)
        base = _as_float(inv.get("net")) if _as_float(inv.get("net")) is not None else _as_float(inv.get("total"))
        basis = "neto" if _as_float(inv.get("net")) is not None else "total"
        if base is None:
            items.append({
                "scope": "invoice_lines",
                "severity": "low",
                "detail": f"Factura {inv.get('code') or inv.get('id')} sin importe base para reconciliar",
                "sources": ["facturascript"],
            })
            continue
        diff = round(line_total - base, 2)
        if abs(diff) <= max(0.01, abs(base) * 0.01):
            continue
        severity = "medium" if abs(diff) <= abs(base) * 0.05 else "high"
        items.append({
            "scope": "invoice_lines",
            "severity": severity,
            "detail": (
                f"Factura {inv.get('code') or inv.get('id')} ({inv.get('type')}): Σ líneas {line_total} ≠ "
                f"{basis} factura {base} (dif {diff:+})"
            ),
            "expected": base,
            "actual": line_total,
            "diff": diff,
            "sources": ["facturascript"],
        })

    # Período: Σ facturas emitidas vs Σ ingresos de ventas (inter-fuente)
    if invoices and sales:
        period_rev: dict[str, float] = {}
        for inv in invoices:
            if not isinstance(inv, dict) or inv.get("type") != "issued":
                continue
            total = _as_float(inv.get("total"))
            date = str(inv.get("date") or "")[:7]
            if total is not None and len(date) == 7:
                period_rev[date] = period_rev.get(date, 0.0) + total
        sales_rev: dict[str, float] = {}
        for s in sales:
            if not isinstance(s, dict):
                continue
            total = _as_float(s.get("total"))
            date = str(s.get("date") or "")[:7]
            if total is not None and len(date) == 7:
                sales_rev[date] = sales_rev.get(date, 0.0) + total
        for period in sorted(set(period_rev) & set(sales_rev)):
            diff = round(period_rev[period] - sales_rev[period], 2)
            if abs(diff) <= max(0.01, abs(period_rev[period]) * 0.05):
                continue
            items.append({
                "scope": "period_reconciliation",
                "severity": "medium",
                "detail": (
                    f"{period}: facturas emitidas {period_rev[period]} ≠ ventas {sales_rev[period]} (dif {diff:+})"
                ),
                "expected": sales_rev[period],
                "actual": period_rev[period],
                "diff": diff,
                "sources": ["facturascript", "ventas"],
            })

    return {
        "checkedAt": _now(),
        "ok": not any(i["severity"] == "high" for i in items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Rentabilidad (FASE 7) — margen y markup SIEMPRE separados
# ---------------------------------------------------------------------------


def profitability(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Margen y markup por producto, por pedido y por período, calculados
    SIEMPRE por separado (regla FASE 7). Coste resuelto del catálogo por SKU;
    los pedidos sin coste se excluyen y se declaran — nunca se inventa un coste."""
    if data is None:
        from . import config_store

        data = config_store.load()
    products = data.get("organizedProducts") or []
    sales = data.get("organizedSales") or []
    invoice_lines = data.get("organizedInvoiceLines") or []
    if not isinstance(products, list):
        products = []
    if not isinstance(sales, list):
        sales = []
    if not isinstance(invoice_lines, list):
        invoice_lines = []

    # FASE 11: el coste SOLO se resuelve si el producto del catálogo tiene
    # coste verificado/importado (coste == PVD sin evidencia → missing) y la
    # línea de venta tiene identidad canónica fiable (SKU/barcode/variant-ID/
    # mapping manual). Nunca se estima un coste.
    from . import product_identity

    catalog = [p for p in products if isinstance(p, dict) and not is_error_payload(p)]
    cost_by_canonical: dict[str, dict[str, Any]] = {}
    for p in catalog:
        rc = product_identity.resolve_cost(p)
        sku = str(p.get("sku") or "").strip().lower()
        if sku and rc.get("costStatus") in ("verified", "imported") and rc.get("cost") is not None:
            cost_by_canonical[sku] = {"cost": rc["cost"], "costStatus": rc["costStatus"], "costSource": rc["costSource"]}
    mappings = product_identity.load_mappings()

    def _line_cost(li: dict[str, Any]) -> tuple[float | None, str, str]:
        """Resuelve el coste de una línea: identidad → producto canónico → coste."""
        ident = product_identity.resolve_identity(li, catalog, mappings)
        if not ident.get("matched") or not ident.get("canonicalProductId"):
            return None, "missing", "no_identity"
        entry = cost_by_canonical.get(str(ident["canonicalProductId"]).strip().lower())
        if not entry:
            return None, "missing", "no_cost"
        return entry["cost"], entry["costStatus"], entry["costSource"]

    # Por producto: unidades, ingresos, coste y margen desde las líneas de
    # pedido Y las líneas de factura (FacturaScripts). Se marcan las fuentes.
    per_sku: dict[str, dict[str, Any]] = {}
    orders_with_cost = 0
    orders_total = 0
    for s in sales:
        if not isinstance(s, dict):
            continue
        orders_total += 1
        lines = normalize_sale_lines(s)
        order_has_cost = False
        for li in lines:
            if not isinstance(li, dict):
                continue
            sku = str(li.get("sku") or li.get("product") or "").strip()
            if not sku:
                continue
            qty = _as_float(li.get("quantity")) or 1.0
            price = _as_float(li.get("price"))
            if price is None:
                price = 0.0
            cost, cstatus, csource = _line_cost(li)
            row = per_sku.setdefault(
                sku.lower(),
                {"sku": sku, "name": str(li.get("title") or sku), "units": 0.0, "revenue": 0.0, "cost": 0.0, "sources": set()},
            )
            row["units"] += qty
            row["revenue"] += price * qty
            row["sources"].add("sales_line_items")
            if cost is not None:
                row["cost"] += cost * qty
                order_has_cost = True
        if order_has_cost:
            orders_with_cost += 1

    # Líneas de factura (issued): revenue = neto de línea, coste = coste×qty
    invoice_skus_with_cost = 0
    for li in invoice_lines:
        if not isinstance(li, dict) or li.get("invoiceType") != "issued":
            continue
        sku = str(li.get("sku") or "").strip()
        if not sku:
            continue
        qty = _as_float(li.get("quantity")) or 0.0
        line_total = _as_float(li.get("lineTotal"))
        cost, cstatus, csource = _line_cost(li)
        row = per_sku.setdefault(
            sku.lower(),
            {"sku": sku, "name": str(li.get("description") or sku), "units": 0.0, "revenue": 0.0, "cost": 0.0, "sources": set()},
        )
        row["units"] += qty
        if line_total is not None:
            row["revenue"] += line_total
        row["sources"].add("invoice_lines")
        if cost is not None:
            row["cost"] += cost * qty
            invoice_skus_with_cost += 1

    product_rows: list[dict[str, Any]] = []
    for row in per_sku.values():
        revenue = round(row["revenue"], 2)
        cost = round(row["cost"], 2)
        margin_abs = round(revenue - cost, 2)
        has_cost = cost > 0 or row["cost"] > 0
        product_rows.append({
            "sku": row["sku"],
            "name": row["name"],
            "units": row["units"],
            "revenue": revenue,
            "cost": cost if has_cost else None,
            "margin": margin_abs if has_cost else None,
            "marginPct": round(margin_abs / revenue * 100, 1) if (has_cost and revenue) else None,
            "markupPct": round(margin_abs / cost * 100, 1) if (has_cost and cost) else None,
            "costCoverage": "catalog" if has_cost else "missing",
            "sources": sorted(row.get("sources") or []),
        })
    product_rows.sort(key=lambda r: r["revenue"] or 0, reverse=True)

    # Por período: suma de márgenes de pedidos con coste
    by_period: dict[str, dict[str, float]] = {}
    for s in sales:
        if not isinstance(s, dict):
            continue
        period = str(s.get("date") or "")[:7]
        if len(period) != 7:
            continue
        lines = normalize_sale_lines(s)
        for li in lines:
            price = _as_float(li.get("price"))
            qty = _as_float(li.get("quantity")) or 1.0
            cost, _cs, _cso = _line_cost(li)
            if price is None or cost is None:
                continue
            row = by_period.setdefault(period, {"revenue": 0.0, "cost": 0.0, "margin": 0.0})
            row["revenue"] += price * qty
            row["cost"] += cost * qty
            row["margin"] += (price - cost) * qty
    period_rows = [
        {
            "period": k,
            "revenue": round(v["revenue"], 2),
            "cost": round(v["cost"], 2),
            "margin": round(v["margin"], 2),
            "marginPct": round(v["margin"] / v["revenue"] * 100, 1) if v["revenue"] else None,
        }
        for k, v in sorted(by_period.items())
    ]

    return {
        "orders": {"total": orders_total, "withCost": orders_with_cost},
        "products": product_rows,
        "byPeriod": period_rows,
        "basis": (
            "coste resuelto SOLO con identidad canónica + coste verificado/importado del catálogo; "
            "sin identidad o sin coste → se declara (costCoverage=missing), nunca se inventa"
        ),
    }
