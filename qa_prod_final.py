# QA PRODUCTO FLUJO 1 (validacion completa tras fe3e28d):
# - calculated: coste real por SKU
# - estimated: margen global declarado
# - nunca 0 EUR inventado (UNKNOWN honesto)
import sys, json, copy
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

def analyze(d, prods, label):
    res = detection_engine.run_detection(d, persist=False)
    findings = (res or {}).get('findings') or []
    cat = opportunity_catalog.build_catalog(findings, products=prods, data=d)
    quant = [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]
    est = sum(1 for o in quant if o.get('impactKind')=='estimated')
    calc = sum(1 for o in quant if o.get('impactKind')=='calculated')
    nq = sum(1 for o in cat if o.get('upsideEuro') is None or o.get('upsideEuro')==0)
    print(f"{label}: {len(quant)} con EUR (est={est}, calc={calc}) | no-cuantif={nq}")
    for o in quant[:3]:
        print(f"   + {o.get('title')} | {o.get('upsideEuro')} EUR | {o.get('impactKind')}")
    return len(quant)

# CASO 1: catalogo completo con coste real por SKU (mock original)
q1 = analyze(data, data.get('organizedProducts', []), "A) coste SKU real")

# CASO 2: sin coste explicito + margen global 40
prods_nc = []
for p in data.get('organizedProducts', []):
    if isinstance(p, dict):
        p2 = dict(p)
        for k in ('cost','costPrice','costStatus'):
            p2.pop(k, None)
        prods_nc.append(p2)
data_m = copy.deepcopy(data); data_m['organizedProducts'] = prods_nc
data_m['companyProfile'] = {'preferences': {'globalMarginPct': 40}}
q2 = analyze(data_m, prods_nc, "B) sin coste + margen global 40%")

print("\nRESUMEN:", "calculated OK" if q1>0 else "calc falla", "| estimated OK" if q2>0 else "est falla")
