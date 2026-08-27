# QA contra DATOS REALES de MOOVING (config en vivo)
import sys, json, os
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog

p = os.environ.get('LOCALAPPDATA','') + '/VANOVA/config/maios.json'
data = json.load(open(p, encoding='utf-8'))
print("dataMode:", data.get('dataMode'), "| sales:", len(data.get('organizedSales') or []), "| products:", len(data.get('organizedProducts') or []))

res = detection_engine.run_detection(data, persist=False)
findings = (res or {}).get('findings') or []
print("findings:", len(findings))
cat = opportunity_catalog.build_catalog(findings, products=data.get('organizedProducts', []), data=data)
quant = [o for o in cat if o.get('upsideEuro') and o['upsideEuro'] > 0]
est = sum(1 for o in quant if o.get('impactKind')=='estimated')
calc = sum(1 for o in quant if o.get('impactKind')=='calculated')
print("oportunidades con EUR:", len(quant), "(est=%d, calc=%d)" % (est, calc))
for o in quant[:4]:
    print("  +", o.get('title'), "|", o.get('upsideEuro'), "EUR |", o.get('impactKind'))
