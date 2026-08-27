import json, os
p = os.environ.get('LOCALAPPDATA','') + '/VANOVA/config/maios.json'
d = json.load(open(p, encoding='utf-8'))
print("dataMode:", d.get('dataMode'))
print("sales:", len(d.get('organizedSales') or []))
print("products:", len(d.get('organizedProducts') or []))
prods = d.get('organizedProducts') or []
print("cost verified:", sum(1 for x in prods if x.get('costStatus')=='verified'))
print("cost estimated:", sum(1 for x in prods if x.get('costStatus')=='estimated'))
sales = d.get('organizedSales') or []
tot = 0
for s in sales:
    tot += float(s.get('total') or s.get('gross') or s.get('amount') or 0)
print("revenue total:", round(tot,2))
