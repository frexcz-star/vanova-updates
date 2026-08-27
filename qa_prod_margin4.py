# QA PRODUCTO FLUJO 1 (corregido tras fe3e28d): margen global -> EUR.
# Se quita SOLO el cost explicito; se conserva netPrice (es lo que hay en un
# catalogo real sin coste por SKU cargado).
import sys, json, copy
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

prods_nc = []
for p in data.get('organizedProducts', []):
    if isinstance(p, dict):
        p2 = dict(p)
        for k in ('cost','costPrice','costStatus'):
            p2.pop(k, None)
        prods_nc.append(p2)

def analyze(d, label):
    res = detection_engine.run_detection(d, persist=False)
    findings = (res or {}).get('findings') or []
    cat = opportunity_catalog.build_catalog(findings, products=d.get('organizedProducts', []))
    quant = [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]
    est = sum(1 for o in quant if o.get('impactKind')=='estimated')
    calc = sum(1 for o in quant if o.get('impactKind')=='calculated')
    print(f"{label}: {len(quant)} con EUR (est={est}, calc={calc})")
    for o in quant[:3]:
        print(f"   + {o.get('title')} | {o.get('upsideEuro')} EUR | {o.get('impactKind')}")
    return len(quant)

data_nc = copy.deepcopy(data); data_nc['organizedProducts'] = prods_nc
qA = analyze(data_nc, "A) sin coste, SIN margen")

data_m = copy.deepcopy(data_nc); data_m['companyProfile'] = {'preferences': {'globalMarginPct': 40}}
qB = analyze(data_m, "B) sin coste CON margen 40%")

print("\nVERDICT:", "DESBLOQUEO OK (margen -> EUR estimated)" if qB>0 and qB>qA else "no desbloquea")
