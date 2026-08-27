import re, sys

def analyze(path):
    src = open(path, encoding='utf-8').read()
    acts_html = set(re.findall(r'data-act\s*=\s*["\']([^"\']+)["\']', src))
    handled = set(re.findall(r"(?:else\s+)?if\s*\(\s*a\s*===\s*['\"]([^'\"]+)['\"]", src))
    missing = acts_html - handled
    print(f"== {path} ==")
    print(f"  data-act total: {len(acts_html)} | handlers: {len(handled)}")
    if missing:
        print("  SIN HANDLER:")
        for a in sorted(missing):
            print("    ", a)
    else:
        print("  OK: todos los data-act tienen handler")
    print()

analyze('web/dashboard.html')
analyze('web/index.html')
