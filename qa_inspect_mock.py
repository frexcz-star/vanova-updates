import json, os
p = 'C:/Users/Admin/maios/mock_dataset.json'
print('existe:', os.path.exists(p))
if os.path.exists(p):
    print('size:', os.path.getsize(p))
    d = json.load(open(p, encoding='utf-8'))
    print('keys:', list(d.keys())[:20])
    for k in ('organizedSales','sales','organizedProducts','products','organizedCustomers','customers'):
        v = d.get(k)
        if isinstance(v, list):
            print(f'{k}: {len(v)} items')
            if v:
                print('  sample keys:', list(v[0].keys())[:12] if isinstance(v[0], dict) else v[0])
            break
