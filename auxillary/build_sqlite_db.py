import os, time, sqlite3
import pandas as pd

CSV_PATH = "/Users/y_anaray/Downloads/Day_Dream_CAPSTONE/Investment product masterfile/Investment products_Masterfile_v69.csv"  # put file in project root or change path
DB_PATH = "/yuh_products.db"
TABLE = "products"

t0 = time.time()
print("Working dir:", os.getcwd(), flush=True)
print("CSV path:", os.path.abspath(CSV_PATH), flush=True)

print("1) Reading CSV...", flush=True)
df = pd.read_csv(CSV_PATH)
print(f"   Read CSV: {len(df):,} rows, {len(df.columns)} cols in {time.time()-t0:.1f}s", flush=True)

print("2) Cleaning headers...", flush=True)
df.columns = [c.strip() for c in df.columns]

print("3) Coercing numeric columns...", flush=True)
for col in ["TER"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

print("4) Connecting to SQLite...", flush=True)
conn = sqlite3.connect(DB_PATH)

# Speed settings for bulk load (fine for a local build step)
conn.execute("PRAGMA journal_mode = WAL;")
conn.execute("PRAGMA synchronous = NORMAL;")

print("5) Writing to SQLite (this is usually the slow part)...", flush=True)
df.to_sql(TABLE, conn, if_exists="replace", index=False, chunksize=5000, method="multi")
print(f"   Wrote table in {time.time()-t0:.1f}s", flush=True)

print("6) Creating indexes...", flush=True)
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_isin ON {TABLE}("product_ID")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_isin ON {TABLE}("Name")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_isin ON {TABLE}("ISIN")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_symbol ON {TABLE}("Symbol")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_type ON {TABLE}("Type")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_currency ON {TABLE}("Currency")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_exchange ON {TABLE}("stock_exchange")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_sector ON {TABLE}("Sector")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_country ON {TABLE}("Region")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_ter ON {TABLE}("TER")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_esg ON {TABLE}("ESG-rating_raw")')
conn.execute(f'CREATE INDEX IF NOT EXISTS idx_products_esg ON {TABLE}("ESG-score")')


conn.commit()
conn.close()

print(f"Built {DB_PATH} with table '{TABLE}' ({len(df)} rows).")