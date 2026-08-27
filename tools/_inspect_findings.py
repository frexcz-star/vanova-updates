import os, json, sys

# Find the runtime config
candidates = [
    r'C:\Users\Admin\AppData\Local\VANOVA\config\maios.json',
    r'C:\Users\Admin\AppData\Local\VANOVA\maios.json',
]
for c in candidates:
    if os.path.exists(c):
        print('USING:', c)
        with open(c, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        findings = cfg.get('businessFindings') or []
        print('businessFindings count:', len(findings))
        for f in findings[:15]:
            print('  id=%r type=%r status=%r title=%r' % (
                f.get('id'), f.get('type'), f.get('status'), str(f.get('title'))[:45]))
        # Now compute build_priorities output to check type field
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'desktop', 'runtime'))
        try:
            from prioritization import build_priorities
            pri = build_priorities(findings, top=20)
            print('--- build_priorities output ---')
            for p in pri:
                print('  has_type=%r type=%r findingType=%r id=%r' % (
                    'type' in p, p.get('type'), p.get('findingType'), p.get('id')))
        except Exception as e:
            print('build_priorities ERR', repr(e))
        break
