# QA PRODUCTO FLUJO 1: margen global desbloquea EUR cuando NO hay coste por SKU.
# Caso clave: productos SIN coste (solo rrp/netPrice) + margen global declarado.
import sys, json, copy
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

# Quitar todos los costes de los productos (simula catalogo sin coste SKU a SKU)
prods_nc = []
for p in data.get('organizedProducts', []):
    if isinstance(p, dict):
        p2 = dict(p)
        p2['cost'] = None
        p2['costPrice'] = None
        p2['costStatus'] = None
        prods_nc.append(p2)
data_nc = copy.deepcopy(data)
data_nc['organizedProducts'] = prods_nc

def count_quant(data):
    res = detection_engine.run_detection(data, persist=False)
    findings = (res or {}).get('findings') or []
    cat = opportunity_catalog.build_catalog(findings, products=data.get('organizedProducts', []))
    return [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]

# A) Sin coste, SIN margen global
qA = count_quant(data_nc)
print("A) sin coste, SIN margen:", len(qA), "oportunidades con EUR")
for o in qA[:3]:
    print("   +", o.get('title'), "|", o.get('upsideEuro'), "|", o.get('impactKind'))

# B) Sin coste, CON margen global 40%
data_nc['companyProfile'] = {'preferences': {'globalMarginPct': 40}}
qB = count_quant(data_nc)
print("B) sin coste CON margen 40%:", len(qB), "oportunidades con EUR")
for o in qB[:3]:
    print("   +", o.get('title'), "|", o.get('upsideEuro'), "|", o.get('impactKind'))

print("\nRESULTADO:", "DESBLOQUEO FUNCIONA (margen genera EUR sin coste SKU)" if len(qB) > len(qA) else "no desbloquea en este caso")
