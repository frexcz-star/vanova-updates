"""Helper de inspección (FASE B): dump de señales y findings de una empresa.

Uso:
  LOCALAPPDATA=benchmark-sandbox/empresa-1 .venv/Scripts/python.exe \
      scripts/benchmark/inspect.py [skus...]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from desktop.runtime import business_signals, detection_engine  # noqa: E402


def main() -> None:
    sig = business_signals.compute_signals()
    interesting = set(a.lower() for a in sys.argv[1:])

    rows = []
    for p in sig["products"]:
        if interesting and p["sku"].lower() not in interesting:
            continue
        rows.append({
            "sku": p["sku"],
            "revenue": p["revenue"],
            "share": p["revenueShare"],
            "margin": p["marginPct"],
            "u30": p["units30d"],
            "uprev": p["unitsPrev30d"],
            "rev30": p["revenue30d"],
            "revprev": p["revenuePrev30d"],
            "stock": p["stock"],
            "vel": p["velocityPerDay"],
            "days": p["daysOfStock"],
            "inventoryValue": p["inventoryValue"],
        })
    print("=== SIGNALS (productos) ===")
    print(json.dumps(rows, ensure_ascii=False, indent=1))

    res = detection_engine.list_findings()
    active = [f for f in res["findings"] if f.get("status") not in ("resolved", "archived")]
    print("=== FINDINGS ===")
    for f in active:
        print(f"- [{f.get('type')}] {f.get('category')}/{f.get('severity')} {f.get('title')} :: {f.get('observation')[:120]}")

    if interesting:
        print("=== SUPPLIERS ===")
        print(json.dumps(sig.get("suppliers"), ensure_ascii=False, indent=1))
        print("=== SUPPLIER PRICES ===")
        print(json.dumps(sig.get("supplierPrices"), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
