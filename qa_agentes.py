import json
p = 'C:/Users/Admin/AppData/Local/VANOVA/config/maios.json'
d = json.load(open(p, encoding='utf-8'))
agents = d.get('agents') or []
print("=== AGENTES en config ===")
print("total:", len(agents))
for a in agents:
    if isinstance(a, dict):
        print(f"  id={a.get('id')} | name={a.get('name')!r} | role={a.get('role')} | hermesBot={a.get('hermesBot')} | perms={a.get('permissions')}")
print("\n=== buscar 'ventas' o 'sales' ===")
for a in agents:
    if isinstance(a, dict):
        name = str(a.get('name') or '')
        if 'venta' in name.lower() or 'sales' in name.lower() or 'sale' in str(a.get('id') or '').lower():
            print("  ENCONTRADO:", a)
