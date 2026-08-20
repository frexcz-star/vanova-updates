"""FASE VALIDACIÓN REAL — importa los archivos fuente con el mecanismo normal
(organize_files) tal como lo haría un cliente, y verifica el resultado."""
import json
import sys
import os

sys.path.insert(0, ".")

from desktop.runtime import config_store  # noqa: E402
from desktop.runtime import file_organizer  # noqa: E402

SRC = os.path.abspath("benchmark-sandbox/real-company/source")

files = []
for name in sorted(os.listdir(SRC)):
    p = os.path.join(SRC, name)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    files.append({"name": name, "path": p, "ext": ext, "size": os.path.getsize(p), "mtime": os.path.getmtime(p)})

print(f"scan files: {[f['name'] for f in files]}")

result = file_organizer.organize_files(files, trigger_hermes=False)

print("organize result status:", result.get("status"))
print("message:", result.get("message"))

data = config_store.load()
products = data.get("organizedProducts") or []
sales = data.get("organizedSales") or []
customers = data.get("organizedCustomers") or []

n_cost = sum(1 for p in products if p.get("costStatus") in ("verified", "imported"))
print(f"PRODUCTOS: {len(products)} (con coste: {n_cost})")
print(f"VENTAS: {len(sales)}")
print(f"CLIENTES: {len(customers)}")

# sanity: uniqueness of product ids
ids = [p.get("id") for p in products]
print("product ids unicos:", len(set(ids)), "/", len(ids))
sku_nonempty = [p for p in products if p.get("sku")]
print("productos con SKU:", len(sku_nonempty), "/", len(products))
