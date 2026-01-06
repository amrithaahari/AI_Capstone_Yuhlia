import sqlite3
from chromadb import Client
from chromadb.config import Settings
from openai import OpenAI
import os

DB_PATH = "yuh_products.db"
CHROMA_DIR = "data/chroma_products"
COLLECTION_NAME = "yuh_products"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def product_to_text(row: dict) -> str:
    return f"""
Name: {row['Name']}
Type: {row['Type']}
Region: {row['Region']}
Sector: {row['Sector']}
Currency: {row['Currency']}
ESG score: {row['ESG_score']}
TER: {row['TER']}
Description: {row['Description']}
""".strip()

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    rows = cur.fetchall()
    conn.close()

    chroma = Client(Settings(persist_directory=CHROMA_DIR))
    collection = chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=lambda texts: [
            client.embeddings.create(
                model="text-embedding-3-small",
                input=t
            ).data[0].embedding
            for t in texts
        ],
    )

    ids = []
    docs = []
    metas = []

    for r in rows:
        ids.append(str(r["product_ID"]))
        docs.append(product_to_text(r))
        metas.append({
            "product_id": r["product_ID"],
            "type": r["Type"],
            "region": r["Region"],
            "ter": r["TER"],
            "esg_score": r["ESG_score"],
        })

    collection.add(
        ids=ids,
        documents=docs,
        metadatas=metas,
    )

    chroma.persist()
    print(f"Indexed {len(ids)} products")

if __name__ == "__main__":
    main()
