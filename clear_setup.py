import sqlite3
conn = sqlite3.connect('C:/Users/Admin/maios/maios_cloud.db')
conn.execute('DELETE FROM kv WHERE key="configured"')
conn.commit()
conn.close()
print('Setup state cleared')