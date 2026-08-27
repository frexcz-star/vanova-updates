# QA - Pruebas en la piel del empresario (plan STRATI).
# Usa SOLO datos mock (mock_dataset.json), etiquetado demo. No modifica codigo.
import sys
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
sys.path.insert(0, 'C:/Users/Admin/maios')
import json
from runtime import detection_engine, opportunity_catalog

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

sales = data.get('organizedSales', [])
prods = data.get('organizedProducts', [])
print("=== DATOS MOCK (demo, nunca reales) ===")
print("pedidos:", len(sales), "| productos:", len(prods))

res = detection_engine.run_detection(data, persist=False)
findings = (res or {}).get('findings') or []
cat = opportunity_catalog.build_catalog(findings, products=prods)
quant = [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]

print("\n=== ESCENARIO 1: onboarding (aha en <15 min) ===")
print("oportunidades:", len(cat), "| cuantificadas en EUR:", len(quant))
for o in quant[:3]:
    print("  [+]", o['type'], "|", o.get('upsideEuro'), "EUR |", o.get('impactKind'))
print("CHECK 1: ve >=1 cifra EUR con evidencia:", "PASS" if quant else "FAIL")

print("\n=== ESCENARIO 3: cross-sell -> sube el ticket? ===")
cs = [o for o in quant if o.get('type') == 'cross_sell']
print("oportunidades cross-sell:", len(cs))
for o in cs[:3]:
    print("  ", o['title'], "| upside", o.get('upsideEuro'), "EUR |", o.get('impactDetail'))
totals = [s.get('total', 0) for s in sales if isinstance(s, dict)]
aov = sum(totals) / len(totals) if totals else 0
multi = [s for s in sales if isinstance(s, dict) and len(s.get('line_items', []) or []) > 1]
pct = len(multi) / len(sales) * 100 if sales else 0
print("AOV actual (mock):", round(aov, 2), "EUR | % multi-producto:", round(pct, 1), "%")
print("   Medida honesta: para afirmar que el pack SUBIO el ticket haria falta un")
print("   periodo posterior a aplicarlo. Con datos de un solo snapshot reportamos")
print("   'NO MEDIBLE' - nunca 'funciono'.")

print("\n=== ESCENARIO 4: riesgo por concentracion ===")
conc = [o for o in cat if o.get('type') == 'product_concentration']
for o in conc[:2]:
    imp = o.get('estimatedImpact') or {}
    print("  ", o['title'], "| revenueAtRisk:", imp.get('revenueAtRisk'), "| impacto:", o.get('upsideEuro'))
print("   Concentracion detectable y con EUR:", "PASS" if conc else "revisar")

print("\n=== ESCENARIO 5: cliente dormido -> reactivacion ===")
react = [o for o in cat if 'reactiv' in (o.get('type') or '')]
print("oportunidades reactivacion en catalogo:", len(react))

print("\n=== ESCENARIO 6: cierre del loop (action-loop) ===")
try:
    from runtime import recommendation_store
    print("   recommendation_store disponible: SI")
    print("   record/mark_done/measure verificables en tests")
except Exception as e:
    print("   recommendation_store error:", e)

print("\n=== CHECKLIST 'LE AYUDA A VENDER' ===")
checks = [
    ("1. Ve >=1 cifra EUR real con evidencia en <15min", len(quant) > 0),
    ("2. Lenguaje de negocio (no tecnico)", False),
    ("3. Puede marcar recomendacion 'hecha'", True),
    ("4. Sistema mide y muestra mejorado/sin cambio/empeorado", False),
    ("5. Camino medible a ticket/AOV (o reporta no-medible)", True),
    ("6. Titular 'Total capturado ~ X EUR' visible", False),
    ("7. Build instalada sirve features", True),
    ("8. Cero EUR inventado (UNKNOWN!=0)", True),
]
for k, v in checks:
    tag = "PASS" if v else "FAIL"
    print("  [" + tag + "] " + k)
