# QA PRODUCTO FLUJO 1 (flujo real de la app): build_catalog lee el margen del data/config.
# La app pasa 'data' a build_catalog? Verificar ambos caminos.
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

def build(data_in, prods):
    res = detection_engine.run_detection(data_in, persist=False)
    findings = (res or {}).get('findings') or []
    # Camino 1: pasar data a build_catalog (lee margen del data)
    cat = opportunity_catalog.build_catalog(findings, products=prods, data=data_in)
    quant = [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]
    est = sum(1 for o in quant if o.get('impactKind')=='estimated')
    print(f"  con data pasado: {len(quant)} EUR (est={est})")
    for o in quant[:3]:
        print(f"     + {o.get('title')} | {o.get('upsideEuro')} EUR | {o.get('impactKind')}")
    return len(quant)

# A) sin margen
data_nc = copy.deepcopy(data); data_nc['organizedProducts'] = prods_nc
qA = build(data_nc, prods_nc)

# B) con margen global 40 (en data)
data_m = copy.deepcopy(data_nc); data_m['companyProfile'] = {'preferences': {'globalMarginPct': 40}}
qB = build(data_m, prods_nc)

print("\nVERDICT:", "DESBLOQUEO OK (margen->EUR)" if qB>qA else "no desbloquea")
