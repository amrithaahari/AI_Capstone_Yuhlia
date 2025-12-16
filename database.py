"""
Database operations for Yulia Assistant
Connects to existing yuh_products.db with real product data
"""

import sqlite3
from typing import List
from config import DATABASE_NAME, TOP_K_PRODUCTS
from models import Product

def init_database():
    """
    Initialize connection to existing SQLite database.
    Note: This assumes yuh_products.db already exists with the products table.

    Table structure:
    - product_ID (INTEGER PRIMARY KEY)
    - Name (TEXT)
    - Symbol (TEXT)
    - ISIN (TEXT)
    - Currency (TEXT)
    - stock_exchange (TEXT)
    - Description (TEXT)
    - Type (TEXT)
    - Sector (TEXT)
    - Region (TEXT)
    - ESG-rating_raw (INTEGER)
    - TER (REAL)
    - ESG_score (TEXT)
    """
    try:
        conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        cursor = conn.cursor()

        # Verify table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='products'
        """)

        if cursor.fetchone() is None:
            raise Exception("products table not found in database")

        # Verify we have data
        cursor.execute('SELECT COUNT(*) FROM products')
        count = cursor.fetchone()[0]
        print(f"Database initialized. Found {count} products.")

        conn.close()

    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

def search_products(query_terms: List[str], top_k: int = TOP_K_PRODUCTS) -> List[Product]:
    """
    Search products using SQL LIKE matching across multiple columns.

    Searches across: Name, Description, Sector, Currency, Region, Type, ESG_score
    """
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()

    # Build query with OR conditions for multiple columns
    # Note: Using actual column names from the existing table
    search_columns = ['Name', 'Description', 'Sector', 'Currency', 'Region', 'Type', 'ESG_score']
    conditions = []
    params = []

    for term in query_terms:
        term_conditions = [f"{col} LIKE ?" for col in search_columns]
        conditions.append(f"({' OR '.join(term_conditions)})")
        params.extend([f"%{term}%" for _ in search_columns])

    # Query using actual column names from your table
    query = f'''
        SELECT product_ID, Name, Description, Sector, Currency, Region, ESG_score, TER
        FROM products
        WHERE {' OR '.join(conditions)}
        LIMIT ?
    '''
    params.append(top_k)

    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()

    products = []
    for row in results:
        products.append(Product(
            product_id=row[0],
            name=row[1],
            description=row[2],
            sector=row[3],
            currency=row[4],
            region=row[5],
            esg_score=row[6],
            ter=row[7]
        ))

    return products

def get_all_products() -> List[Product]:
    """Retrieve all products from the database"""
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT product_ID, Name, Description, Sector, Currency, Region, ESG_score, TER
        FROM products
    ''')

    results = cursor.fetchall()
    conn.close()

    products = []
    for row in results:
        products.append(Product(
            product_id=row[0],
            name=row[1],
            description=row[2],
            sector=row[3],
            currency=row[4],
            region=row[5],
            esg_score=row[6],
            ter=row[7]
        ))

    return products