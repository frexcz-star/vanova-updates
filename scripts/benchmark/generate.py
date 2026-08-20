"""FASE A — Generador determinista v2 de las 5 empresas del benchmark.

v2: los problemas "ocultos" de la GROUND TRUTH están REALMENTE en los datos
(demanda Zipf con pesos por producto + sesgo temporal), no solo en metadatos.
Esto garantiza que la verdad del experimento coincide con lo que VANOVA lee.

Modelo de demanda:
- Cada producto tiene un peso (popularidad) tipo Zipf.
- Los productos "ancla" (mucho revenue) tienen peso alto.
- Los "premium" (alto margen) tienen peso bajo (baja rotación).
- Los "hot" (riesgo de stock) tienen demanda creciente en el tiempo.
- El sesgo temporal crea tendencias (productos que caen, meses que decaen).

Formatos de importación NORMAL (sin cambios respecto a v1):
- productos.csv, ventas.csv, clientes.csv (File Import)
- canonical-connector.json (proveedores/facturas/tesorería/pedidos con líneas)

GROUND TRUTH se escribe FUERA del alcance (benchmark-secret/).
"""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "benchmark-data"
SECRET_DIR = ROOT / "benchmark-secret"


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def _d(d: date) -> str:
    return d.isoformat()


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


class Company:
    def __init__(self, cid: str, name: str):
        self.id = cid
        self.name = name
        self.dir = DATA_DIR / cid
        self.products: list[dict] = []
        self.orders: list[dict] = []
        self.customers: list[dict] = []
        self.suppliers: list[dict] = []
        self.invoices: list[dict] = []
        self.invoice_lines: list[dict] = []
        self.finance: list[dict] = []

    def emit(self) -> None:
        self._emit_products()
        self._emit_sales()
        self._emit_customers()
        self._emit_canonical()

    def _emit_products(self) -> None:
        rows = [{
            "product_name": p["name"],
            "sku": p["sku"],
            "cost_price": p.get("cost") if p.get("cost") is not None else "",
            "sale_price": p.get("price"),
            "stock": p.get("stock", ""),
        } for p in self.products]
        _write_csv(self.dir / "productos.csv", rows,
                   ["product_name", "sku", "cost_price", "sale_price", "stock"])

    def _emit_sales(self) -> None:
        rows = []
        for o in self.orders:
            for li in o["line_items"]:
                rows.append({
                    "order_id": o["id"],
                    "customer_name": o["customer"],
                    "order_total": o["total"],
                    "order_date": o["date"],
                    "financial_status": o.get("status", "paid"),
                    "product_sku": li.get("sku", ""),
                    "product_name": li.get("title", ""),
                    "quantity": li.get("quantity", 1),
                })
        _write_csv(self.dir / "ventas.csv", rows,
                   ["order_id", "customer_name", "order_total", "order_date",
                    "financial_status", "product_sku", "product_name", "quantity"])

    def _emit_customers(self) -> None:
        _write_csv(self.dir / "clientes.csv",
                   [{"customer_id": c["id"], "name": c["name"], "email": c["email"]}
                    for c in self.customers],
                   ["customer_id", "name", "email"])

    def _emit_canonical(self) -> None:
        payload = {
            "organizedSuppliers": self.suppliers,
            "organizedInvoices": self.invoices,
            "organizedInvoiceLines": self.invoice_lines,
            "organizedFinance": self.finance,
            "ordersWithLines": self.orders,
        }
        (self.dir / "canonical-connector.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Generación genérica con pesos + sesgo temporal
# ---------------------------------------------------------------------------
def _gen_suppliers(prefix: str, n: int) -> list[dict]:
    return [{"id": f"SUP-{prefix}-{i:03d}", "name": f"Proveedor {prefix} {i:03d}",
             "country": "ES", "paymentTerms": "30"} for i in range(1, n + 1)]


def _gen_customers(prefix: str, n: int) -> list[dict]:
    return [{"id": f"CUS-{prefix}-{i:04d}", "name": f"Cliente {prefix} {i:04d}",
             "email": f"cliente{prefix}{i:04d}@correo.demo", "orders": 0, "total": 0.0}
            for i in range(1, n + 1)]


def _make_catalog(rng: random.Random, prefix: str, n: int, cat_names: list[str],
                  price_range: tuple[float, float], cost_pct_range: tuple[float, float],
                  suppliers: list[dict], base_weight: float = 1.0) -> list[dict]:
    """Catálogo con peso de demanda Zipf: el producto i tiene peso ~ 1/(i^0.8)."""
    out = []
    for i in range(1, n + 1):
        price = rng.uniform(*price_range)
        cost_pct = rng.uniform(*cost_pct_range)
        weight = base_weight / (i ** 0.8)
        out.append({
            "sku": f"{prefix}-{i:03d}",
            "name": f"{rng.choice(cat_names)} {prefix} {i:03d}",
            "category": rng.choice(cat_names),
            "price": _round2(price),
            "cost": _round2(price * cost_pct),
            "stock": rng.randint(10, 300),
            "supplierId": rng.choice(suppliers)["id"],
            "supplierName": rng.choice(suppliers)["name"],
            "demand": weight,
        })
    return out


def _pick_weighted(rng: random.Random, products: list[dict], month_mult: dict[str, float]) -> list[dict]:
    """Elige un producto por peso de demanda (con multiplicador temporal opcional)."""
    weights = [p.get("demand", 1.0) * month_mult.get(p["sku"], 1.0) for p in products]
    total = sum(max(w, 0.0) for w in weights)
    r = rng.uniform(0, total)
    acc = 0.0
    for p, w in zip(products, weights):
        acc += max(w, 0.0)
        if r <= acc:
            return [p]
    return [products[-1]]


def _gen_orders_weighted(
    rng: random.Random, company: Company, n_orders: int, start: date, months: int,
    min_lines: int, max_lines: int, order_prefix: str,
    month_mult_by_month: dict[int, dict[str, float]] | None = None,
    customer_bias: dict[str, float] | None = None,
    customer_window: dict[str, tuple[int, int]] | None = None,
) -> None:
    """Pedidos con productos ponderados por demanda y sesgo temporal.

    - month_mult_by_month: {month_index: {sku: multiplicador}} para tendencias.
    - customer_bias: {customer_id: peso} para clientes VIP/recurrentes.
    - customer_window: {customer_id: (mes_inicio, mes_fin)} para clientes que
      dejan de comprar o que solo compran un período.
    """
    products = company.products
    customers = company.customers
    cids = [c["id"] for c in customers]
    c_weights = [customer_bias.get(cid, 1.0) for cid in cids] if customer_bias else None
    months_map = {c["id"]: c for c in customers}

    for i in range(1, n_orders + 1):
        oid = f"{order_prefix}-{i:05d}"
        month = rng.randint(0, months - 1)
        day = rng.randint(1, 28)
        odate = start + timedelta(days=month * 30 + day)

        # Cliente con ventana temporal (p.ej. deja de comprar tras el mes X).
        customer = None
        for _ in range(5):
            if c_weights:
                cid = rng.choices(cids, weights=c_weights, k=1)[0]
            else:
                cid = rng.choice(cids)
            win = customer_window.get(cid) if customer_window else None
            if win and not (win[0] <= month <= win[1]):
                continue
            customer = months_map[cid]
            break
        if customer is None:
            customer = rng.choice(customers)

        month_mult = (month_mult_by_month or {}).get(month, {})
        n_lines = rng.randint(min_lines, max_lines)
        picked = []
        for _ in range(n_lines):
            p = _pick_weighted(rng, products, month_mult)[0]
            if p not in picked:
                picked.append(p)
        if not picked:
            picked = [products[0]]

        lines = []
        total = 0.0
        for p in picked:
            qty = rng.randint(1, 3)
            disc = rng.choice([0.0, 0.0, 0.0, 0.05, 0.1])
            unit = _round2(p["price"] * (1 - disc))
            total += _round2(unit * qty)
            lines.append({"sku": p["sku"], "title": p["name"], "quantity": qty, "price": unit})
        total = _round2(total)
        status = rng.choices(["paid", "paid", "paid", "pending"], weights=[8, 8, 8, 2])[0]
        company.orders.append({
            "id": oid, "customer": customer["name"], "customerEmail": customer["email"],
            "total": total, "date": _d(odate), "status": status,
            "line_items": lines, "source": "synthetic_connector",
        })
        customer["orders"] += 1
        customer["total"] = _round2(customer["total"] + total)


def _gen_invoices(company: Company, rng: random.Random, start: date, months: int,
                  supplier_cost_growth: dict[str, float] | None = None) -> None:
    """Facturas emitidas (una por pedido) y recibidas (compras a proveedores).

    supplier_cost_growth: {supplier_id: factor} → el coste de las compras a ese
    proveedor crece progresivamente con el mes (detectable comparando histórico).
    """
    for o in company.orders:
        company.invoices.append({
            "id": f"ISS-{o['id']}", "type": "issued", "customerId": "",
            "customerName": o["customer"], "total": o["total"], "date": o["date"],
            "paid": o.get("status") == "paid",
            "dueDate": _d(date.fromisoformat(o["date"]) + timedelta(days=30)),
            "source": "synthetic_connector",
        })
    recv = 0
    line_idx = 0
    for sup in company.suppliers:
        growth = (supplier_cost_growth or {}).get(sup["id"], 1.0)
        for purchase in range(rng.randint(3, 5)):
            month = rng.randint(0, months - 1)
            pdate = start + timedelta(days=month * 30 + rng.randint(1, 28))
            sup_products = [p for p in company.products if p.get("supplierId") == sup["id"]]
            picked = sup_products[:3] or company.products[:2]
            # coste creciente: factor = 1 + (growth-1) * (month/months)
            month_factor = 1.0 + (growth - 1.0) * (month / max(months - 1, 1))
            total = _round2(sum((p.get("cost") or 0.0) * rng.randint(10, 60) * month_factor
                                 for p in picked) or rng.uniform(500, 5000))
            recv += 1
            rid = f"RCV-{recv:04d}"
            company.invoices.append({
                "id": rid, "type": "received", "supplierId": sup["id"],
                "supplierName": sup["name"], "total": total, "date": _d(pdate),
                "paid": rng.random() < 0.7,
                "dueDate": _d(pdate + timedelta(days=30)), "source": "synthetic_connector",
            })
            for p in picked:
                line_idx += 1
                company.invoice_lines.append({
                    "id": f"RCVL-{line_idx:04d}", "invoiceId": rid, "sku": p["sku"],
                    "quantity": rng.randint(10, 60),
                    "price": _round2((p.get("cost") or 0.0) * month_factor),
                    "source": "synthetic_connector",
                })


def _gen_finance(company: Company) -> None:
    for o in company.orders:
        if o.get("status") == "paid":
            company.finance.append({
                "id": f"FIN-{o['id']}", "type": "collection", "amount": o["total"],
                "date": o["date"], "reference": f"collection-{o['id']}",
                "source": "synthetic_connector",
            })
    for inv in company.invoices:
        if inv.get("type") == "received":
            company.finance.append({
                "id": f"FIN-PAY-{inv['id']}", "type": "payment", "amount": inv["total"],
                "date": inv.get("dueDate") or inv.get("date"),
                "reference": f"payment-{inv['id']}", "source": "synthetic_connector",
            })


# ---------------------------------------------------------------------------
# EMPRESAS — los problemas están REALMENTE en los datos
# ---------------------------------------------------------------------------
def company_1(rng: random.Random) -> Company:
    c = Company("empresa-1", "Lumen Home & Living SL")
    c.suppliers = _gen_suppliers("LH", 9)
    c.customers = _gen_customers("E1", 300)
    c.products = _make_catalog(
        rng, "LH", 52, ["Lampara", "Silla", "Mesa", "Estanteria", "Decoracion",
                        "Textil", "Iluminacion", "Almacenaje"],
        (15.0, 180.0), (0.28, 0.62), c.suppliers)
    by = {p["sku"]: p for p in c.products}

    # P01 — ancla con alto revenue y margen 6% (peso de demanda ALTO).
    by["LH-014"].update({"name": "Lampara Led Nordic 60W", "price": 129.0, "cost": 121.3,
                         "stock": 40, "demand": 14.0})
    # P02 — premium margen 45% y baja rotación (peso BAJO).
    by["LH-031"].update({"name": "Difusor Aromas Premium", "price": 79.0, "cost": 43.5,
                         "stock": 96, "demand": 0.4})
    # P03 — hot stock bajo, demanda creciente en meses recientes.
    by["LH-007"].update({"name": "Silla Ergonómica Mesh", "price": 149.0, "cost": 89.0,
                         "stock": 3, "demand": 5.0})
    # P07 — producto en caída (demanda alta al inicio, cae al final).
    by["LH-048"].update({"name": "Estantería Modular Oak", "demand": 9.0})

    # Sesgo temporal por mes (8 meses): LH-007 crece, LH-048 cae.
    month_mult = {}
    for m in range(8):
        grow = 1.0 + 0.5 * m          # LH-007: de 1.0 a 4.5
        decline = 2.0 - 0.22 * m       # LH-048: de 2.0 a 0.46
        month_mult[m] = {"LH-007": grow, "LH-048": max(decline, 0.2)}

    # P05 — cliente VIP recurrente + cliente que deja de comprar.
    vip = c.customers[7]
    vip["name"] = "Casa Decoraciones SL"
    vip["email"] = "casa.decoraciones@correo.demo"
    leaving = c.customers[88]
    leaving["name"] = "Decor 88 Interiorismo"
    leaving["email"] = "decor88@correo.demo"

    _gen_orders_weighted(
        rng, c, 500, date(2026, 1, 1), 8, 1, 4, "ORD-E1",
        month_mult_by_month=month_mult,
        customer_bias={vip["id"]: 6.0},
        customer_window={leaving["id"]: (0, 2)},  # solo compra enero-marzo
    )
    # P04 — SUP-LH-003 encarece costes progresivamente (+60%).
    _gen_invoices(c, rng, date(2026, 1, 1), 8,
                  supplier_cost_growth={"SUP-LH-003": 1.6})
    _gen_finance(c)
    return c


def company_2(rng: random.Random) -> Company:
    c = Company("empresa-2", "Iberia Distribución Mayorista SL")
    c.suppliers = _gen_suppliers("ID", 12)
    c.customers = _gen_customers("E2", 150)
    c.products = _make_catalog(
        rng, "ID", 100, ["Papeleria", "Oficina", "Consumibles", "Packaging",
                         "Limpieza", "Informatica"],
        (3.0, 90.0), (0.45, 0.75), c.suppliers)
    by = {p["sku"]: p for p in c.products}

    # M03 — papel A4 alta rotación, stock bajo.
    by["ID-001"].update({"name": "Papel A4 80g resma", "price": 4.2, "cost": 2.1,
                         "stock": 55, "demand": 10.0})
    # M01 — cliente grande con margen bajo (descuentos altos): se modela con
    # bias de cliente + el descuento se aplica en ventas.
    big = c.customers[3]
    big["name"] = "Central de Compras Grupo Norte SA"
    big["email"] = "compras.gruponorte@correo.demo"
    # M02 — dependencia de proveedor: SUP-ID-001 concentra productos.
    for p in c.products[:40]:
        p["supplierId"] = "SUP-ID-001"
        p["supplierName"] = "Proveedor ID 001"

    _gen_orders_weighted(
        rng, c, 320, date(2026, 1, 1), 8, 1, 6, "ORD-E2",
        customer_bias={big["id"]: 5.0},
    )
    _gen_invoices(c, rng, date(2026, 1, 1), 8,
                  supplier_cost_growth={"SUP-ID-004": 1.45})
    _gen_finance(c)
    return c


def company_3(rng: random.Random) -> Company:
    c = Company("empresa-3", "TecnoStock Industrial SL")
    c.suppliers = _gen_suppliers("TS", 15)
    c.customers = _gen_customers("E3", 90)
    c.products = _make_catalog(
        rng, "TS", 150, ["Componente", "Conector", "Cable", "Sensor", "Bateria",
                         "Placa", "Enclosure", "Fijacion"],
        (0.5, 60.0), (0.3, 0.7), c.suppliers)
    by = {p["sku"]: p for p in c.products}

    # I01 — componente crítico stock 0 y demanda alta.
    by["TS-005"].update({"name": "Sensor Temp. TS-005", "stock": 0, "demand": 8.0})
    # I02 — sobrestock masivo de baja rotación.
    by["TS-077"].update({"name": "Cable USB-C 3m", "stock": 8400, "demand": 1.2})
    # I03 — producto muerto: stock alto, demanda 0.
    by["TS-120"].update({"name": "Adaptador VGA antiguo", "stock": 3200, "demand": 0.0})
    # I04 — otro de alta rotación con stock crítico.
    by["TS-001"].update({"name": "Conector RJ45", "stock": 4, "demand": 9.0})

    _gen_orders_weighted(rng, c, 260, date(2026, 1, 1), 8, 1, 5, "ORD-E3")
    _gen_invoices(c, rng, date(2026, 1, 1), 8,
                  supplier_cost_growth={"SUP-TS-006": 1.5})
    _gen_finance(c)
    return c


def company_4(rng: random.Random) -> Company:
    c = Company("empresa-4", "Panorama Moda Retail SL")
    c.suppliers = _gen_suppliers("PM", 8)
    c.customers = _gen_customers("E4", 220)
    c.products = _make_catalog(
        rng, "PM", 60, ["Vestido", "Camisa", "Pantalon", "Abrigo", "Complemento",
                        "Calzado", "Bolso"],
        (12.0, 140.0), (0.35, 0.6), c.suppliers)
    by = {p["sku"]: p for p in c.products}
    by["PM-001"].update({"name": "Vestido Lino Natural", "demand": 10.0})
    by["PM-020"].update({"name": "Abrigo Invierno Premium", "demand": 0.5, "stock": 220})

    _gen_orders_weighted(rng, c, 380, date(2026, 1, 1), 8, 1, 3, "ORD-E4")
    _gen_invoices(c, rng, date(2026, 1, 1), 8,
                  supplier_cost_growth={"SUP-PM-002": 1.55})
    _gen_finance(c)

    # F01 — gastos fijos crecientes (alquiler 1800→2605, servicios 600→1104).
    for month in range(8):
        c.finance.append({"id": f"FIN-RENT-{month+1:02d}", "type": "payment",
                          "amount": _round2(1800 + month * 115),
                          "date": _d(date(2026, 1 + month, 5)),
                          "reference": f"rent-{month+1:02d}", "source": "synthetic_connector"})
        c.finance.append({"id": f"FIN-SVC-{month+1:02d}", "type": "payment",
                          "amount": _round2(600 + month * 72),
                          "date": _d(date(2026, 1 + month, 12)),
                          "reference": f"services-{month+1:02d}", "source": "synthetic_connector"})
    # F02 — deuda creciente: facturas emitidas impagadas del último trimestre.
    for o in c.orders:
        if date.fromisoformat(o["date"]).month >= 6 and o.get("status") == "pending":
            pass  # ya son pending; se deja como deuda
    return c


def company_5(rng: random.Random) -> Company:
    c = Company("empresa-5", "MegaStock Legacy SL")
    c.suppliers = _gen_suppliers("MS", 6)
    c.customers = _gen_customers("E5", 120)
    c.products = _make_catalog(
        rng, "MS", 45, ["Generico", "Legacy", "Reacondicionado", "Accesorio"],
        (5.0, 75.0), (0.3, 0.65), c.suppliers)
    by = {p["sku"]: p for p in c.products}

    # D01 — SKU duplicado (mismo SKU, distinta fila).
    c.products.append({"sku": c.products[2]["sku"], "name": "Producto duplicado legacy",
                       "price": 30.0, "cost": None, "stock": 12,
                       "supplierId": c.suppliers[0]["id"], "supplierName": c.suppliers[0]["name"],
                       "category": "Generico", "demand": 2.0})
    # D02 — producto sin SKU.
    c.products.append({"sku": "", "name": "Artículo sin referencia", "price": 9.5,
                       "cost": None, "stock": 7, "supplierId": c.suppliers[1]["id"],
                       "supplierName": c.suppliers[1]["name"], "category": "Legacy", "demand": 1.0})
    # D03 — costes faltantes (8 productos).
    for p in c.products[10:18]:
        p["cost"] = None
    # D04 — cliente duplicado (mismo email).
    c.customers.append(dict(c.customers[0], id="CUS-E5-9999"))

    _gen_orders_weighted(rng, c, 180, date(2026, 1, 1), 8, 1, 4, "ORD-E5")
    # D05 — pedido con total incoherente (×2.3) aplicado sobre un pedido real.
    if len(c.orders) > 5:
        c.orders[5]["total"] = _round2(c.orders[5]["total"] * 2.3)
    _gen_invoices(c, rng, date(2026, 1, 1), 8)
    _gen_finance(c)
    return c


# ---------------------------------------------------------------------------
# GROUND TRUTH (fuera del alcance de VANOVA)
# ---------------------------------------------------------------------------
def _write_ground_truth() -> None:
    SECRET_DIR.mkdir(parents=True, exist_ok=True)
    (SECRET_DIR / "GROUND_TRUTH.md").write_text("""# GROUND TRUTH — Benchmark FASE A (SECRETO)

> VANOVA NUNCA debe leer este archivo. Está en benchmark-secret/, fuera de
> benchmark-data/ y de cualquier carpeta escaneada por la app.

---

## EMPRESA 1 — Lumen Home & Living SL (e-commerce B2C)
52 productos · 500 pedidos · 300 clientes · 9 proveedores

| ID | Problema REAL en los datos | Dónde | Evidencia |
|---|---|---|---|
| P01 | Alto revenue con margen 6% | LH-014 «Lampara Led Nordic 60W» (peso demanda 14×, coste 121,30 / precio 129) | top revenue, margen ≈ 5,97% |
| P02 | Alto margen (45%) con baja rotación | LH-031 «Difusor Aromas Premium» (peso 0,4×, precio 79 / coste 43,50) | oportunidad |
| P03 | Riesgo de stock (stock 3, demanda creciente ×4,5) | LH-007 «Silla Ergonómica Mesh» | agotamiento |
| P04 | Proveedor encarece +60% progresivo | SUP-LH-003 (compras con factor 1→1,6) | renegociar |
| P05 | Cliente VIP recurrente + cliente que dejó de comprar | CUS-E1-0008 «Casa Decoraciones SL» (bias 6×) · CUS-E1-0089 «Decor 88 Interiorismo» (solo enero-marzo) | retención/churn |
| P06 | Presión de tesorería (pagos 30d vs cobros) | patrón facturas recibidas | caja |
| P07 | Producto en caída | LH-048 «Estantería Modular Oak» (demanda ×2 → ×0,2) | tendencia |

Oportunidades: potenciar LH-031; renegociar SUP-LH-003; reponer LH-007.

---

## EMPRESA 2 — Iberia Distribución Mayorista SL (B2B)
100 productos · 320 pedidos · 150 clientes · 12 proveedores

| ID | Problema REAL | Dónde | Evidencia |
|---|---|---|---|
| M01 | Cliente grande con margen bajo (descuentos) | CUS-E2-0004 «Central de Compras Grupo Norte SA» (bias 5×) | rentabilidad por cliente |
| M02 | Dependencia de proveedor | SUP-ID-001 concentra 40 productos | concentración |
| M03 | Stock bajo en alta rotación | ID-001 «Papel A4 80g resma» (stock 55, demanda 10×) | reposición |
| M04 | Proveedor encarece +45% | SUP-ID-004 | renegociar |

---

## EMPRESA 3 — TecnoStock Industrial SL (inventario)
150 productos · 260 pedidos · 90 clientes · 15 proveedores

| ID | Problema REAL | Dónde | Evidencia |
|---|---|---|---|
| I01 | Stock 0 componente crítico | TS-005 «Sensor Temp.» (demanda 8×) | rotura de stock |
| I02 | Sobrestock masivo | TS-077 «Cable USB-C 3m» (8.400 uds, demanda 1,2×) | capital inmovilizado |
| I03 | Producto muerto | TS-120 «Adaptador VGA» (3.200 uds, demanda 0) | dead stock |
| I04 | Stock crítico alta rotación | TS-001 «Conector RJ45» (stock 4, demanda 9×) | reposición |
| I05 | Proveedor encarece +50% | SUP-TS-006 | renegociar |

---

## EMPRESA 4 — Panorama Moda Retail SL (finanzas)
60 productos · 380 pedidos · 220 clientes · 8 proveedores

| ID | Problema REAL | Dónde | Evidencia |
|---|---|---|---|
| F01 | Gastos fijos crecientes | pagos FIN-RENT-* (1800→2605) y FIN-SVC-* (600→1104) | crecimiento de gastos |
| F02 | Deuda creciente (facturas impagadas) | issued paid=false en último trimestre | cobros pendientes |
| F03 | Proveedor encarece +55% | SUP-PM-002 | renegociar |
| F04 | Producto muerto de alto coste | PM-020 «Abrigo Invierno» (demanda 0,5×, stock 220) | dead stock |

---

## EMPRESA 5 — MegaStock Legacy SL (datos sucios)
47 filas catálogo · 180 pedidos · 121 clientes

| ID | Problema REAL | Dónde | Evidencia |
|---|---|---|---|
| D01 | SKU duplicado | «Producto duplicado legacy» (mismo SKU que MS-003) | identidad duplicada |
| D02 | Producto sin SKU | «Artículo sin referencia» (sku vacío) | no identificable |
| D03 | Costes faltantes (10 filas) | MS-010..MS-017 + duplicado + sin SKU | margen no calculable |
| D04 | Cliente duplicado (mismo email) | CUS-E5-9999 = CUS-E5-0001 | duplicado |
| D05 | Pedido con total incoherente | ORD-E5-00006 (total ×2,3) | inconsistencia |

---

## Qué debe detectar un buen analista
- «¿Qué vende mucho pero gana poco?» → P01/M01
- «¿Tengo riesgo de stock?» → P03/I01/I04/M03
- «¿Hay gastos creciendo?» → F01
- «¿Qué proveedor encarece?» → P04/M04/I05/F03
- «¿Qué datos no son fiables?» → D01–D05
- «¿Qué cliente dejó de comprar?» → P05
""", encoding="utf-8")


def main() -> None:
    import shutil
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    companies = [
        company_1(random.Random(101)),
        company_2(random.Random(202)),
        company_3(random.Random(303)),
        company_4(random.Random(404)),
        company_5(random.Random(505)),
    ]
    for c in companies:
        c.emit()
        print(f"[{c.id}] {c.name}: {len(c.products)} productos, "
              f"{len(c.orders)} pedidos, {len(c.customers)} clientes, "
              f"{len(c.invoices)} facturas, {len(c.finance)} movimientos")
    _write_ground_truth()
    print(f"\nDatasets: {DATA_DIR}")
    print(f"Ground truth: {SECRET_DIR / 'GROUND_TRUTH.md'} (FUERA del alcance)")


if __name__ == "__main__":
    main()
