# products.py
import sqlite3
from typing import List, Dict, Any

def get_table_name(con: sqlite3.Connection) -> str:
    # v1 assumption: there's only one main products table or you hardcode it after inspecting once
    rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    # choose the first table by default; replace with explicit name once known
    return rows[0][0]

def retrieve_products(db_path: str, query: str, k: int = 8) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    like = f"%{q}%"

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    table = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0]

    search_cols = [
        "name", "isin", "description", "sector", "region", "type",
        "ter", "currency", "stock_exchange", "esg_score"
    ]

    where = " OR ".join([f'"{c}" LIKE ?' for c in search_cols])

    sql = f'''
    SELECT *
    FROM "{table}"
    WHERE {where}
    LIMIT ?
    '''

    params = [like] * len(search_cols) + [k]

    # Debug once, then remove
    # print("?", sql.count("?"), "params", len(params), "cols", len(search_cols))

    rows = con.execute(sql, params).fetchall()
    con.close()
    return [dict(r) for r in rows]


def products_to_markdown(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "_No matching products found in the Yuh catalog._"

    # pick safe, useful columns if present
    preferred = ["name", "isin", "currency", "stock_exchange", "type", "sector", "region", "esg_score","ter"]
    cols = [c for c in preferred if c in rows[0]]

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    body = "\n".join(
        "| " + " | ".join(str(r.get(c, "") or "") for c in cols) + " |"
        for r in rows
    )
    return "\n".join([header, sep, body])
