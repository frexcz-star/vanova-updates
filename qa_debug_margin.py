# Debug: por que el cross-sell con margen global no cuantifica en EUR.
import sys, json, copy
sys.path.insert(0, 'C:/Users/Admin/maios/desktop')
from runtime import detection_engine, opportunity_catalog, product_identity

with open('C:/Users/Admin/maios/mock_dataset.json', encoding='utf-8') as f:
    data = json.load(f)

# quitar costes explicitos pero dejar netPrice (simular catalogo sin coste SKU)
prods_nc = []
for p in data.get('organizedProducts', []):
    if isinstance(p, dict):
        p2 = dict(p)
        for k in ('cost','costPrice','costStatus'):
            p2.pop(k, None)
        prods_nc.append(p2)

data_nc = copy.deepcopy(data)
data_nc['organizedProducts'] = prods_nc
data_nc['companyProfile'] = {'preferences': {'globalMarginPct': 40}}

res = detection_engine.run_detection(data_nc, persist=False)
findings = (res or {}).get('findings') or []
cs = [f for f in findings if f.get('type') == 'cross_sell']
print("findings cross_sell:", len(cs))

# probar _upside_for_cross_sell directamente
for f in cs[:3]:
    m = f.get('metrics') or {}
    pair = m.get('pair')
    orders = m.get('ordersTogether')
    print(f"\npair={pair} orders={orders}")
    up, kind, det = opportunity_catalog._upside_for_cross_sell(f, prods_nc, global_margin_pct=40)
    print(f"  con margen 40: upside={up} kind={kind} det={det}")
    up0, kind0, det0 = opportunity_catalog._upside_for_cross_sell(f, prods_nc, global_margin_pct=None)
    print(f"  sin margen:    upside={up0} kind={kind0} det={det0}")

# verificar resolve_cost de un producto del par
print("\nresolve_cost muestra:")
for p in prods_nc[:2]:
    r = product_identity.resolve_cost(p, 40)
    print(" ", p.get('sku'), "rrp=", p.get('rrp'), "netPrice=", p.get('netPrice'), "->", {k:r.get(k) for k in ('cost','costStatus','costSource')})
