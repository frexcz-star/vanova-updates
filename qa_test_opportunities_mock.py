"""QA: probar el Detector de Oportunidades con el dataset MOCK rico.
Etiquetado claro como datos ficticios/demo, nunca reales.
Verifica que las oportunidades con upsideEuro en EUR se generan correctamente.
"""
import sys, os, json
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
sys.path.insert(0, 'C:/Users/Admin/maios')

from unittest.mock import patch
from runtime import detection_engine, opportunity_catalog

# Cargar dataset MOCK (ficticio, demo)
with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

print("=== DATASET MOCK (FICTICIO, etiquetado demo) ===")
print("sales:", len(data.get('organizedSales', [])))
print("products:", len(data.get('organizedProducts', [])))

# Run detection on mock data
res = detection_engine.run_detection(data, persist=False)
findings = (res or {}).get('findings') or []
print("\n=== DETECCION (mock) ===")
print("findings totales:", len(findings))
opps = [f for f in findings if f.get('category') == 'opportunity']
print("findings oportunidad:", len(opps))

# Build catalog
cat = opportunity_catalog.build_catalog(findings, products=data.get('organizedProducts', []))
print("\n=== CATALOGO OPORTUNIDADES (mock) ===")
print("oportunidades:", len(cat))
for o in cat:
    print(f"  [{o.get('type')}] {o.get('title','')[:50]} | upside={o.get('upsideEuro')} | kind={o.get('impactKind')}")

quant = [o for o in cat if o.get('upsideEuro') is not None and o.get('upsideEuro') > 0]
print("\n=== RESULTADO QA ===")
print("oportunidades cuantificadas en EUR:", len(quant))
print("  -> OK" if len(quant) >= 1 else "  -> PROBLEMA: ninguna cuantificada")
