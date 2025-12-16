import sqlite3

conn = sqlite3.connect("../yuh_products.db")

q = """
SELECT
  *
FROM products
ORDER BY TER ASC
LIMIT 10
"""

rows = conn.execute(q).fetchall()
for r in rows:
    print(r)

conn.close()
