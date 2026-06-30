import sqlite3
conn = sqlite3.connect(r'D:/Faceless Video Generator/database/faceless.db')
tables = conn.execute('SELECT name FROM sqlite_master WHERE type="table"').fetchall()
print('Tables:', tables)
for row in conn.execute('SELECT key, value FROM settings WHERE key like "video.narrator%"'):
    print(row)
conn.close()
