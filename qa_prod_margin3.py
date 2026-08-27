# QA PRODUCTO FLUJO 1 (verificado tras commit fe3e28d):
# el margen global declarado debe desbloquear el EUR en cross-sell.
# Debug completo: cuantos findings cross_sell emite el motor, y cuantos cuantifica el catalogo.
import sys, json, copy
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

# Quitar costes de los productos
prods_nc = []
for p in data.get('organizedProducts', []):
    if isinstance(p, dict):
        p2 = dict(p)
        for k in ('cost','costPrice','costStatus'):
            p2[k] = None
        prods_nc.append(p2)

data_nc = copy.deepcopy(data)
data_nc['organizedProducts'] = prods_nc

def analyze(d):
    res = detection_engine.run_detection(d, persist=False)
    findings = (res or {}).get('findings') or []
    cs = [f for f in findings if f.get('type') == 'cross_sell']
    cat = opportunity_catalog.build_catalog(findings, products=d.get('organizedProducts', []))
    quant = [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]
    est = [o for o in quant if o.get('impactKind')=='estimated']
    calc = [o for o in quant if o.get('impactKind')=='calculated']
    print(f"  findings cross_sell: {len(cs)} | catalogo total: {len(cat)} | con EUR: {len(quant)} (est={len(est)}, calc={len(calc)})")
    for o in quant[:3]:
        print(f"     + {o.get('title')} | {o.get('upsideEuro')} EUR | {o.get('impactKind')}")
    return len(quant)

print("=== A) sin coste, SIN margen global ===")
qA = analyze(data_nc)

print("\n=== B) sin coste, CON margen global 40% ===")
data_nc['companyProfile'] = {'preferences': {'globalMarginPct': 40}}
qB = analyze(data_nc)

print("\nRESULTADO:", "DESBLOQUEO OK" if qB > qA else "NO desbloquea aun")
