import json, os, glob

# Buscar el config real
candidates = [
    os.environ.get('LOCALAPPDATA','') + '/VANOVA/config/maios.json',
    'C:/Users/Admin/AppData/Local/VANOVA/config/maios.json',
]
cfg = None
for c in candidates:
    if os.path.exists(c):
        cfg = c
        break
if not cfg:
    print("NO config encontrado"); raise SystemExit
d = json.load(open(cfg, encoding='utf-8'))
print("config:", cfg)
print("dataMode:", d.get('dataMode'))
print("scanFiles:", len(d.get('scanFiles') or []))
print("organizedProducts:", len(d.get('organizedProducts') or []))
print("organizedSales:", len(d.get('organizedSales') or []))
prods = d.get('organizedProducts') or []
verified = [p for p in prods if isinstance(p,dict) and p.get('costStatus')=='verified']
with_cost = [p for p in prods if isinstance(p,dict) and (p.get('costPrice') is not None or p.get('cost'))]
print("products verified cost:", len(verified))
print("products with cost field:", len(with_cost))
sales = d.get('organizedSales') or []
rev = sum(float(s.get('total') or 0) for s in sales if isinstance(s,dict))
print("sales revenue total:", round(rev,2), "EUR")
# config companyProfile
cp = d.get('companyProfile') or {}
print("companyProfile:", {k:cp.get(k) for k in ['name','grossMargin','defaultCost','sector'] if k in cp})

# muestra origen de productos
print("\n=== muestra productos ===")
for p in prods[:6]:
    if isinstance(p,dict):
        print({k:p.get(k) for k in ['name','sku','costStatus','costPrice','source','rrp','netPrice']})
# origenes unicos
sources = {}
for p in prods:
    if isinstance(p,dict):
        s = str(p.get('source') or '?')
        sources[s] = sources.get(s,0)+1
print("origenes productos:", sources)
