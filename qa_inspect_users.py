import sqlite3, os, sys, json
db = os.path.join(os.environ.get('LOCALAPPDATA',''), 'VANOVA', 'config', 'maios_cloud.db')
print("DB:", db, "exists:", os.path.exists(db))
conn = sqlite3.connect(db)
cur = conn.cursor()
# list tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)
# find user-like tables
for t in tables:
    if any(k in t.lower() for k in ['user','account','credential','auth']):
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [c[1] for c in cur.fetchall()]
            print(f"--- {t} cols={cols}")
            cur.execute(f"SELECT * FROM {t} LIMIT 10")
            rows = cur.fetchall()
            for r in rows:
                # redact password hashes partially
                def redact(x):
                    if isinstance(x,str) and len(x)>20: return x[:12]+'...'
                    return x
                print("   ", [redact(c) for c in r])
        except Exception as e:
            print(f"   ERR {t}: {e}")
conn.close()
