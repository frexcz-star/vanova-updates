import re, subprocess, os
html = open('web/dashboard.html', encoding='utf-8').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
print('inline script blocks:', len(scripts))
tmp = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Temp')
ok = True
for i, s in enumerate(scripts):
    if not s.strip():
        continue
    p = os.path.join(tmp, 'dash_script_%d.js' % i)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)
    r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
    if r.returncode == 0:
        print('block %d: OK (%d chars)' % (i, len(s)))
    else:
        ok = False
        print('block %d: SYNTAX ERROR' % i)
        print(r.stderr[:3000])
print('ALL VALID' if ok else 'HAS ERRORS')
