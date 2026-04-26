import sqlite3

conn = sqlite3.connect("electropulse.db")

rows = conn.execute("""
SELECT id, market_id, raw_model_name
FROM source_products
WHERE raw_model_name LIKE '%SparkWatch%'
LIMIT 10
""").fetchall()

print(rows)