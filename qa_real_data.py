# QA PRODUCTO - validar flujo con DATOS REALES (no mock)
# Busca en el config real de MOOVING/VANOVA si hay ventas reales, y encuentra el
# benchmark de datos reales si existe.
import json, os, glob, sys

# 1) config real actual
cfg_paths = [
    os.environ.get('LOCALAPPDATA','') + '/VANOVA/config/maios.json',
    'C:/Users/Admin/AppData/Local/VANOVA/config/maios.json',
]
for c in cfg_paths:
    if os.path.exists(c):
        d = json.load(open(c, encoding='utf-8'))
        print("CONFIG REAL:", c)
        print("  organizedSales:", len(d.get('organizedSales') or []))
        print("  organizedProducts:", len(d.get('organizedProducts') or []))
        print("  scanFiles:", len(d.get('scanFiles') or []))
        print("  companyProfile:", d.get('companyProfile'))
        break

# 2) buscar benchmarks con ventas reales
import os
candidates = []
for root in ['C:/Users/Admin/maios', os.environ.get('LOCALAPPDATA','')+'/VANOVA']:
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if 'benchmark' in f.lower() or 'real' in f.lower():
                candidates.append(os.path.join(dp, f))
print("\nbenchmark/real files:", candidates[:10])

# 3) buscar datasets json con organizedSales con filas
hits = 0
for root in ['C:/Users/Admin/maios']:
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.endswith('.json') and ('mock' in f.lower() or 'sales' in f.lower() or 'data' in f.lower()):
                p = os.path.join(dp, f)
                try:
                    d = json.load(open(p, encoding='utf-8'))
                    s = d.get('organizedSales') or []
                    if s and len(s) > 0 and hits < 5:
                        print("  dataset con ventas:", p, "=", len(s), "ventas")
                        hits += 1
                except Exception:
                    pass
