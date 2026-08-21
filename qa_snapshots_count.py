import sqlite3
conn = sqlite3.connect('C:/Users/Admin/maios/maios_cloud.db')
tables = []
for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    tables.append(row[0])
print('Tablas:', sorted(tables))
for t in sorted(tables):
    try:
        n = conn.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        print('  %s: %d filas' % (t, n))
    except Exception as e:
        print('  %s: ERR %s' % (t, e))
conn.close()
