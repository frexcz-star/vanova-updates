import re
src = open('web/dashboard.html', encoding='utf-8').read()

# Ver que acciones reales usa el dispatcher (inicia con prefijo dinámico o startsWith)
print("=== Dispatcher: casos con startsWith / prefijos / else if con split ===")
# encontrar en el dispatcher patrones de inicio
for m in re.finditer(r"(?:else\s+)?if\s*\(\s*a\s*\.startsWith\s*\(\s*['\"]([^'\"]+)['\"]", src):
    print("  startsWith:", m.group(1))
for m in re.finditer(r"if\s*\(\s*a\s*===|a\.indexOf\(['\"]([^'\"]+)", src):
    pass

# Buscar las acciones literales dudosas y ver si hay handler con prefijo split
candidates = ['add-agent','cand-approve-all','data-rearm','data-reimport',
              'data-review-later','data-review-now','edit-margin','import-costs',
              'import-guide','investigate','new-agent','new-task','recon-export-json',
              'recon-unlink','run-agent','set-margin-quick','sw-go']
for c in candidates:
    # buscar si hay algun handler que lo referencie (por substring)
    hits = [l for l in src.splitlines() if f"'{c}'" in l or f'"{c}"' in l]
    if not hits:
        print(f"  {c}: NO references found in any string")
PY = '''
import re
src = open('web/dashboard.html', encoding='utf-8').read()
for m in re.finditer(r"a\s*\.\s*startsWith\s*\(\s*['\"]([^'\"]+)", src):
    print("startsWith:", m.group(1))
for m in re.finditer(r"a\s*\.\s*indexOf\s*\(\s*['\"]([^'\"]+)", src):
    print("indexOf:", m.group(1))
for m in re.finditer(r"a\s*\.\s*split\s*\(\s*['\"]([^'\"]+)", src):
    print("split:", m.group(1))
'''
open('tools/_tmp_dispatch.py','w').write(PY)
