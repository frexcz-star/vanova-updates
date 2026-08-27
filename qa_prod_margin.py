# QA PRODUCTO FLUJO 1: validar que el margen global declarado DESBLOQUEA el EUR.
# Usa datos mock honestos (etiquetado demo) + companyProfile con preferences.globalMarginPct.
# Si el margen global declarado produce upsideEuro > 0 -> el desbloqueo FUNCIONA.
import sys, json, copy
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

prods = data.get('organizedProducts', [])
print("=== datos mock: productos con coste ===", sum(1 for p in prods if p.get('cost') is not None), "de", len(prods))

# A) SIN margen global (estado previo): oportunidades cuantificadas?
res = detection_engine.run_detection(data, persist=False)
findings = (res or {}).get('findings') or []
cat_no = opportunity_catalog.build_catalog(findings, products=prods)
quant_no = [o for o in cat_no if o.get('upsideEuro') and o['upsideEuro'] > 0]
print("\nA) SIN margen global:", len(quant_no), "oportunidades cuantificadas")

# B) CON margen global declarado (companyProfile.preferences.globalMarginPct=40)
data2 = copy.deepcopy(data)
data2['companyProfile'] = {'preferences': {'globalMarginPct': 40}}
res2 = detection_engine.run_detection(data2, persist=False)
findings2 = (res2 or {}).get('findings') or []
cat2 = opportunity_catalog.build_catalog(findings2, products=data2.get('organizedProducts', prods))
quant2 = [o for o in cat2 if o.get('upsideEuro') and o['upsideEuro'] > 0]
print("B) CON margen global 40%:", len(quant2), "oportunidades cuantificadas")
for o in quant2[:4]:
    print("   +", o.get('title'), "|", o.get('upsideEuro'), "EUR |", o.get('impactKind'))

print("\nRESULTADO desbloqueo:", "FUNCIONA (margen desbloquea EUR)" if len(quant2) > len(quant_no) else "revisar")
