"""FASE VALIDACIÓN REAL — exporta los datos canónicos reales a archivos fuente
con el esquema que el organizador normal espera (productos.xlsx, ventas.csv),
para probar el import como lo haría un cliente real."""
import csv
import sys

sys.path.insert(0, ".")

from desktop.runtime import config_store  # noqa: E402

OUT = "benchmark-sandbox/real-company/source/"
os_import = __import__("os")

data = config_store.load()
products = data.get("organizedProducts") or []
sales = data.get("organizedSales") or []

os_import.makedirs(OUT, exist_ok=True)

# ---- productos.xlsx (openpyxl) ----
try:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Productos"
    ws.append(["product_name", "sku", "cost_price", "sale_price", "stock"])
    n_cost = 0
    for p in products:
        cost = p.get("cost") if p.get("costStatus") in ("verified", "imported") else None
        if cost is not None:
            n_cost += 1
        ws.append([
            p.get("name") or "",
            p.get("sku") or "",
            cost if cost is not None else "",
            p.get("rrp") if p.get("rrp") is not None else (p.get("netPrice") if p.get("netPrice") is not None else ""),
            p.get("stock") if p.get("stock") is not None else "",
        ])
    wb.save(OUT + "productos.xlsx")
    print(f"productos.xlsx: {len(products)} filas ({n_cost} con coste)")
except ImportError:
    print("openpyxl no disponible; se usará CSV para productos")
    with open(OUT + "productos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["product_name", "sku", "cost_price", "sale_price", "stock"])
        for p in products:
            cost = p.get("cost") if p.get("costStatus") in ("verified", "imported") else ""
            w.writerow([
                p.get("name") or "",
                p.get("sku") or "",
                cost if cost is not None else "",
                p.get("rrp") if p.get("rrp") is not None else "",
                p.get("stock") if p.get("stock") is not None else "",
            ])
    print(f"productos.csv: {len(products)} filas")

# ---- ventas.csv (una fila por pedido con total) ----
with open(OUT + "ventas.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["order_id", "customer_name", "customer_email", "total", "date", "status"])
    n = 0
    for s in sales:
        w.writerow([
            s.get("id") or s.get("order_id") or "",
            s.get("customer") or "",
            s.get("customerEmail") or "",
            s.get("total") if s.get("total") is not None else "",
            s.get("date") or "",
            s.get("status") or "paid",
        ])
        n += 1
    print(f"ventas.csv: {n} filas")

print("export OK ->", OUT)
