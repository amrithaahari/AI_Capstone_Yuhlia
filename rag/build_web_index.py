# rag/build_web_index.py
import os
import re
import hashlib
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

from chromadb import Client
from chromadb.config import Settings
from openai import OpenAI

CHROMA_DIR = "data/chroma_products"
COLLECTION_NAME = "yuh_website"
EMBED_MODEL = "text-embedding-3-small"

URLS = [
    "https://www.yuh.com/en/app/invest/",
    "https://www.yuh.com/en/app/invest/etfs/",
    "https://www.yuh.com/en/app/invest/stocks/",
    "https://www.yuh.com/en/app/invest/crypto/",
    "https://www.yuh.com/en/app/invest/themes/",
    "https://www.yuh.com/en/app/3apillar/",
    "https://www.yuh.com/en/app/3apillar/why-choose-yuh-3a/",
    "https://www.yuh.com/en/yuhlearn/experience-the-eighth-wonder-of-the-world-with-compound-interest-on-your-pillar-3a/",
    "https://www.yuh.com/en/app/invest/etf-savings-plan/",
    "https://www.yuh.com/en/app/invest/etf-partner-invesco/",
    "https://www.yuh.com/en/app/invest/etf-partner-vanguard/",
    "https://www.yuh.com/en/app/invest/etf-partner-ishares/",
    "https://www.yuh.com/en/app/invest/etf-partner-invesco/",
    "https://www.yuh.com/en/app/invest/etf-partner-vanguard/",
    "https://www.yuh.com/en/app/invest/etf-partner-ishares/",
    "https://www.yuh.com/en/app/invest/etf-partner-vanguard/",
    "https://www.yuh.com/en/app/invest/etf-partner-wisdomtree/",
    "https://www.yuh.com/en/app/invest/etf-partner-invesco/",
    "https://www.yuh.com/en/app/invest/etf-partner-vanguard/",
    "https://www.yuh.com/en/app/invest/etf-partner-swisscanto/",
    "https://www.yuh.com/en/app/invest/etf-partner-swisscanto/",
    "https://www.yuh.com/en/app/invest/etf-partner-vanguard/",
    "https://www.yuh.com/en/app/invest/etf-partner-vanguard/",
    "https://www.yuh.com/en/app/invest/etf-partner-swisscanto/",
    "https://www.yuh.com/en/app/invest/etf-partner-wisdomtree/",
    "https://www.yuh.com/en/app/invest/etf-partner-wisdomtree/",
    "https://www.yuh.com/en/app/invest/etf-partner-xtrackers/",
    "https://www.yuh.com/en/app/invest/etf-partner-xtrackers/",
    "https://www.yuh.com/en/app/invest/etf-partner-xtrackers/",
    "https://www.yuh.com/en/app/invest/etf-partner-xtrackers/",
    "https://www.moneyland.ch/en/savings-plan-etf-mutual-fund-guide",
]

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _clean_text(t: str) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    # Remove cookie/legal/footer-ish repetition (keep simple; iterate later)
    t = re.sub(r"Download the Yuh app now.*$", "", t, flags=re.IGNORECASE)
    return t.strip()

def _extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Remove obvious non-content
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    # Prefer main/article content if present, else body
    main = soup.find("main") or soup.find("article") or soup.body
    text = main.get_text(separator=" ", strip=True) if main else soup.get_text(" ", strip=True)
    return _clean_text(text)

def _chunk_text(text: str, max_chars: int = 1100, overlap: int = 150) -> List[str]:
    if not text:
        return []
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i : i + max_chars]
        chunks.append(chunk)
        i += max_chars - overlap
    return chunks

def _embed(texts: List[str]) -> List[List[float]]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def main():
    chroma = Client(Settings(persist_directory=CHROMA_DIR))
    collection = chroma.get_or_create_collection(name=COLLECTION_NAME)
    total_chunks = 0
    ids = []
    docs = []
    metas = []

    for url in URLS:
        r = requests.get(url, timeout=30)
        r.raise_for_status()


        text = _extract_main_text(r.text)
        chunks = _chunk_text(text, max_chars=1100, overlap=150)
        total_chunks += len(chunks)
        print(f"[{url}] extracted_chars={len(text)} chunks={len(chunks)}")
        print(f"TOTAL chunks indexed: {total_chunks}")

        for idx, ch in enumerate(chunks):
            h = hashlib.md5((url + "|" + str(idx) + "|" + ch[:200]).encode("utf-8")).hexdigest()
            ids.append(f"{url}#{idx}#{h}")
            docs.append(ch)
            metas.append({"source": "yuh.com", "url": url, "chunk_index": idx})

    # Upsert behavior: delete existing and re-add (simple)
    try:
        collection.delete(ids=ids)
    except Exception:
        pass

    embeddings = _embed(docs)
    collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)

    chroma.persist()
    print(f"Indexed {len(ids)} website chunks into {COLLECTION_NAME}")

if __name__ == "__main__":
    main()
