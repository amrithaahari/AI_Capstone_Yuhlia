# database.py
import sqlite3
from typing import List, Optional, Tuple

from config import DATABASE_NAME, TOP_K_PRODUCTS
from models import Product


def init_database() -> None:
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    if cur.fetchone() is None:
        conn.close()
        raise RuntimeError("products table not found in database")
    conn.close()


def _score_row(row: Tuple, terms: List[str]) -> int:
    # Row is: (product_ID, Name, Description, Sector, Currency, Region, ESG_score, TER, Type)
    _, name, desc, sector, currency, region, esg, _, ptype = row
    blob = {
        "name": (name or "").lower(),
        "type": (ptype or "").lower(),
        "sector": (sector or "").lower(),
        "desc": (desc or "").lower(),
        "region": (region or "").lower(),
        "currency": (currency or "").lower(),
        "esg": (esg or "").lower(),
    }

    score = 0
    for t in terms:
        tl = t.lower().strip()
        if not tl:
            continue
        if tl in blob["name"]:
            score += 6
        if tl in blob["type"]:
            score += 5
        if tl in blob["sector"]:
            score += 3
        if tl in blob["region"]:
            score += 2
        if tl in blob["currency"]:
            score += 2
        if tl in blob["esg"]:
            score += 2
        if tl in blob["desc"]:
            score += 1
    return score


def search_products(
    query_terms: List[str],
    top_k: int = TOP_K_PRODUCTS,
    type_whitelist: Optional[List[str]] = None,
) -> List[Product]:
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cur = conn.cursor()

    search_columns = ["Name", "Description", "Sector", "Currency", "Region", "Type", "ESG_score"]
    conditions = []
    params: List[str] = []

    for term in query_terms:
        term_conditions = [f"{col} LIKE ?" for col in search_columns]
        conditions.append(f"({' OR '.join(term_conditions)})")
        params.extend([f"%{term}%" for _ in search_columns])

    where_clause = " OR ".join(conditions) if conditions else "1=1"
    type_clause = ""
    if type_whitelist:
        placeholders = ",".join(["?"] * len(type_whitelist))
        type_clause = f" AND Type IN ({placeholders})"
        params.extend(type_whitelist)

    sql = f"""
        SELECT product_ID, Name, Description, Sector, Currency, Region, ESG_score, TER, Type
        FROM products
        WHERE ({where_clause}) {type_clause}
        LIMIT 200
    """

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    ranked = sorted(rows, key=lambda r: _score_row(r, query_terms), reverse=True)[:int(top_k)]

    products: List[Product] = []
    for r in ranked:
        products.append(Product(
            id=r[0],
            name=r[1],
            type=r[8],
            description=r[2],
            sector=r[3],
            currency=r[4],
            region=r[5],
            esg=r[6],
            ter=r[7],
        ))
    return products


def search_products_filtered(
    *,
    type_contains_all: Optional[List[str]] = None,
    region: Optional[str] = None,
    max_ter: Optional[float] = None,
    esg_scores_in: Optional[List[str]] = None,
    top_k: int = TOP_K_PRODUCTS,
    order_by_esg: bool = False,
) -> List[Product]:
    """Structured product search using parameterized SQL.

    Supports:
    - Type contains ALL substrings (case-insensitive)
    - Region exact match
    - TER upper bound
    - ESG_score in list
    - Optional ESG ordering AAA -> AA -> A
    """
    type_contains_all = [t.strip() for t in (type_contains_all or []) if (t or "").strip()]
    esg_scores_in = [s.strip().upper() for s in (esg_scores_in or []) if (s or "").strip()]

    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cur = conn.cursor()

    where = []
    params: List[object] = []

    for sub in type_contains_all:
        where.append("LOWER(Type) LIKE LOWER(?)")
        params.append(f"%{sub}%")

    if region:
        where.append("Region = ?")
        params.append(region)

    if max_ter is not None:
        where.append("TER IS NOT NULL AND TER <= ?")
        params.append(float(max_ter))

    if esg_scores_in:
        placeholders = ",".join(["?"] * len(esg_scores_in))
        where.append(f"ESG_score IN ({placeholders})")
        params.extend(esg_scores_in)

    where_clause = " AND ".join(where) if where else "1=1"

    if order_by_esg:
        order_clause = """
        ORDER BY
          CASE ESG_score
            WHEN 'AAA' THEN 1
            WHEN 'AA'  THEN 2
            WHEN 'A'   THEN 3
            ELSE 99
          END ASC,
          CASE WHEN TER IS NULL THEN 1 ELSE 0 END,
          TER ASC,
          Name ASC
        """.strip()
    else:
        order_clause = """
        ORDER BY CASE WHEN TER IS NULL THEN 1 ELSE 0 END, TER ASC, Name ASC
        """.strip()

    sql = f"""
        SELECT product_ID, Name, Description, Sector, Currency, Region, ESG_score, TER, Type
        FROM products
        WHERE {where_clause}
        {order_clause}
        LIMIT ?
    """.strip()

    params.append(int(top_k))

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    products: List[Product] = []
    for r in rows:
        products.append(Product(
            id=r[0],
            name=r[1],
            type=r[8],
            description=r[2],
            sector=r[3],
            currency=r[4],
            region=r[5],
            esg=r[6],
            ter=r[7],
        ))
    return products


def get_type_overview(limit_types: int = 20) -> List[Tuple[str, int]]:
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT Type, COUNT(*) as n
        FROM products
        WHERE Type IS NOT NULL AND TRIM(Type) != ''
        GROUP BY Type
        ORDER BY n DESC
        LIMIT ?
        """,
        (int(limit_types),),
    )
    rows = cur.fetchall()
    conn.close()
    return [(r[0], int(r[1])) for r in rows]


def get_sample_products_for_types(types: List[str], per_type: int = 2) -> List[Product]:
    """Fetch a small sample of products for each Type, round-robin across types."""
    if not types:
        return []

    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cur = conn.cursor()

    per_type = max(1, min(int(per_type), 5))

    sql = """
        SELECT product_ID, Name, Description, Sector, Currency, Region, ESG_score, TER, Type
        FROM products
        WHERE Type = ?
        ORDER BY CASE WHEN TER IS NULL THEN 1 ELSE 0 END, TER ASC, Name ASC
        LIMIT ?
    """.strip()

    buckets: List[List[Product]] = []
    for t in types:
        cur.execute(sql, (t, per_type))
        rows = cur.fetchall()
        bucket: List[Product] = []
        for r in rows:
            bucket.append(Product(
                id=r[0],
                name=r[1],
                type=r[8],
                description=r[2],
                sector=r[3],
                currency=r[4],
                region=r[5],
                esg=r[6],
                ter=r[7],
            ))
        if bucket:
            buckets.append(bucket)

    conn.close()

    out: List[Product] = []
    for i in range(per_type):
        for b in buckets:
            if i < len(b):
                out.append(b[i])

    return out
