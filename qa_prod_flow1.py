# QA de PRODUCTO: flujo coste -> EUR real.
# Con datos mock ricos (665 pedidos + 30 productos con coste), verificar que el
# detector calcula EUR cuando hay ventas + coste (el caso que el usuario real
# alcanzaria tras cargar ventas y costes).
import sys, json
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

sales = data.get('organizedSales', [])
prods = data.get('organizedProducts', [])
print("=== datos mock (honesto, etiquetado demo) ===")
print("ventas:", len(sales), "| productos:", len(prods))
withcost = [p for p in prods if isinstance(p,dict) and p.get('cost') is not None]
print("productos con coste:", len(withcost))

# Detectar oportunidades -> se cuantifican en EUR cuando hay ventas+coste
res = detection_engine.run_detection(data, persist=False)
findings = (res or {}).get('findings') or []
cat = opportunity_catalog.build_catalog(findings, products=prods)
quant = [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]
print("\n=== RESULTADO ===")
print("oportunidades:", len(cat), "| cuantificadas en EUR:", len(quant))
for o in quant[:3]:
    print("  +", o.get('title'), "|", o.get('upsideEuro'), "EUR |", o.get('impactKind'))
print("\nCONCLUSION: con ventas+coste, el EUR REAL se calcula:", "SI" if quant else "NO")
