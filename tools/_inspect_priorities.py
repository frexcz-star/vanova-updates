import sqlite3, json, os

cands = [
    r'C:\Users\Admin\AppData\Local\VANOVA\config\maios_cloud.db',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'maios_cloud.db'),
]
for db in cands:
    if os.path.exists(db):
        print('USING DB:', db)
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                "SELECT workspace_id, data FROM snapshots WHERE kind='dashboard' ORDER BY rowid DESC LIMIT 3"
            ).fetchall()
            for wid, data in rows:
                d = json.loads(data)
                pri = d.get('priorities') or []
                print('workspace', wid, 'n_priorities', len(pri))
                for p in pri[:20]:
                    print('  type=%r id=%r title=%r status=%r' % (
                        p.get('type'), p.get('id'), str(p.get('title'))[:45], p.get('status')))
        except Exception as e:
            print('ERR', repr(e))
        conn.close()
