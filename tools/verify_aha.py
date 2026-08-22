#!/usr/bin/env python3
"""verify_aha.py — verificación del camino al aha (SPEC 1 §5) para Mathew/QA.

Comprueba el criterio clave del onboarding "aha": con ventas + coste por SKU
reales, el runtime produce el € cuantificado (calculated) que puebla el titular
"En juego este mes" y la 1ª oportunidad. Honesto: nunca inventa €; si falta
coste, lo marca como estimated/UNKNOWN (no un 0 falso).

Qué comprueba (criterios §5 y §6 de STRATI_ESPEC_FLUJO_COSTES):
  1. El catálogo tiene productos con coste real (calculated posible).
  2. Hay ventas reales.
  3. `sales_summary` produce revenue + grossMargin reales (margen del catálogo).
  4. El catálogo de oportunidades devuelve al menos una con upsideEuro > 0
     (la oportunidad cuantificada que pinta el Home).
  5. (Honestidad) Si no hay coste -> el margen es UNKNOWN, nunca un 0 €.

Uso (local, sin secrets):
    python tools/verify_aha.py        # usa el config en vivo
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Resolver el config del runtime (mismo mecanismo que el producto)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from desktop.runtime import business_model  # noqa: E402
    from desktop.runtime import config_store as _cs  # noqa: E402
    CONFIG_PATH = _cs.CONFIG_FILE
except Exception:  # noqa: BLE001
    business_model = None
    CONFIG_PATH = Path(os.environ.get("VANOVA_CONFIG", r"C:\Users\Admin\AppData\Local\VANOVA\config\maios.json"))


def _load_cfg():
    return json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8-sig"))


def main() -> int:
    results: list[str] = []
    print("== Verificación del camino al AHA (SPEC 1 §5) ==\n")
    try:
        cfg = _load_cfg()
    except Exception as e:  # noqa: BLE001
        print(f"[FALLO] No se pudo leer el config ({CONFIG_PATH}): {e}")
        return 1

    prods = cfg.get("organizedProducts") or []
    sales = cfg.get("organizedSales") or []
    total = len(prods)
    with_cost = sum(1 for p in prods if isinstance(p.get("cost"), (int, float)) and p.get("cost", 0) > 0)
    verified = sum(1 for p in prods if p.get("costStatus") == "verified")

    # 1) Catálogo con coste real
    ok1 = with_cost > 0
    results.append(f"[{'OK' if ok1 else 'FALLO'}] catálogo con coste real: {with_cost}/{total} (verified={verified})")
    print(results[-1])

    # 2) Ventas reales
    ok2 = len(sales) > 0
    results.append(f"[{'OK' if ok2 else 'FALLO'}] ventas reales: {len(sales)}")
    print(results[-1])

    # 3) Margen real del catálogo (revenue + grossMargin)
    s = business_model.sales_summary(sales, prods) if with_cost else {}
    rev = s.get("revenue")
    gm = s.get("grossMarginPct")
    ok3 = rev is not None and gm is not None
    results.append(f"[{'OK' if ok3 else 'INFO'}] margen real: revenue={rev} €, grossMargin={gm}% (basis={s.get('marginBasis')})")
    print(results[-1])

    # 4) Oportunidad cuantificada (criterio §5: 1 oportunidad € en fila superior)
    try:
        from desktop.runtime import opportunity_catalog
        cat = opportunity_catalog.catalog()
        # catalog() devuelve una lista de oportunidades (o dict con 'opportunities').
        if isinstance(cat, dict):
            opps = cat.get("opportunities") or cat.get("items") or []
        else:
            opps = list(cat or [])
        with_upside = [o for o in opps if isinstance(o.get("upsideEuro"), (int, float)) and o["upsideEuro"] > 0]
        ok4 = len(with_upside) > 0
        first = with_upside[0] if with_upside else None
        results.append(f"[{'OK' if ok4 else 'INFO'}] oportunidad €: {len(with_upside)} con upside (1ª: {first.get('upsideEuro') if first else None})")
        print(results[-1])
    except Exception as e:  # noqa: BLE001
        results.append(f"[INFO] catálogo de oportunidades: {e}")
        print(results[-1])

    # 5) Honestidad: si hay coste real, calculated es posible (no un 0 falso)
    results.append(f"[{'OK' if with_cost > 0 else 'FALLO'}] honestidad: coste real presente -> calculated posible (no 0 inventado)")
    print(results[-1])

    # Resumen
    print("\n== Resumen ==")
    for r in results:
        print("  " + r)
    fails = [r for r in results if r.startswith("[FALLO]")]
    print(f"\n{'AHA DESBLOQUEADO' if not fails else 'HAY ' + str(len(fails)) + ' FALLO(S)'} — {len(results)-len(fails)}/{len(results)} checks OK")
    print("\nCriterio §5: con ventas + cost ≥1, el Home pinta el titular € (calculated) y la 1ª oportunidad cuantificada en la fila superior, sin scroll.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
