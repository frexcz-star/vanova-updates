"""MAIOS — ingest MOOVING catalog from the real Excel into the Cloud.
Reads the real MOOVING price list (NET_PRICE_LECLERC_ENGLISH_FORMATTED.xlsx)
and stores it as a 'products' snapshot so the dashboard shows REAL catalog data.
"""
import os, sys, json, sqlite3, datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cloud", "maios_cloud.db")
XLSX = r"C:\Users\Admin\Downloads\NET_PRICE_LECLERC_ENGLISH_FORMATTED.xlsx"

def main():
    import openpyxl
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["CARREFOUR PRICE LIST"]
    rows = list(ws.iter_rows(values_only=True))
    products = []
    for r in rows[4:]:
        sku = r[0]
        if not sku or not str(sku).strip():
            continue
        name = str(r[2] or "").strip()
        net = r[4]
        rrp = r[5]
        products.append({
            "sku": str(sku).strip(),
            "ean": str(r[1] or "").strip(),
            "name": name,
            "netPrice": round(float(net), 2) if isinstance(net, (int, float)) else None,
            "rrp": round(float(rrp), 2) if isinstance(rrp, (int, float)) else None,
        })
    print(f"Extraídos {len(products)} productos reales de MOOVING")

    # Store as a products snapshot for the workspace
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS snapshots (workspace_id TEXT, kind TEXT, data TEXT, ts TEXT)""")
    ws_id = conn.execute("SELECT id FROM workspaces LIMIT 1").fetchone()
    if not ws_id:
        print("ERROR: no workspace found")
        return 1
    ws_id = ws_id[0]
    payload = {
        "dataMode": "real",
        "source": "MOOVING catalog (Excel)",
        "products": products,
        "count": len(products),
        "fetchedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    conn.execute(
        "INSERT INTO snapshots (workspace_id, kind, data, ts) VALUES (?,?,?,?)",
        (ws_id, "products", json.dumps(payload, ensure_ascii=False), datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    print(f"Catálogo guardado en Cloud (workspace {ws_id})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
