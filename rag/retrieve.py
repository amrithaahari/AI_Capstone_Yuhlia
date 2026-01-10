from chromadb import Client
from chromadb.config import Settings
from openai import OpenAI
import os
from chromadb.errors import NotFoundError


CHROMA_DIR = "data/chroma_products"
COLLECTION_NAME = "yuh_products"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed(text: str):
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    # record embedding usage for cost (input only)
    try:
        from agents import record_usage
        usage = getattr(resp, "usage", None)
        total = int(getattr(usage, "total_tokens", 0) or 0) if usage is not None else 0
        if total:
            record_usage("text-embedding-3-small", input_tokens=total, output_tokens=0, total_tokens=total)
    except Exception:
        pass

    return resp.data[0].embedding



def rag_candidates(query: str, top_n: int = 80) -> list[int]:
    chroma = Client(Settings(persist_directory=CHROMA_DIR))
    try:
        collection = chroma.get_collection(name=COLLECTION_NAME)
    except NotFoundError:
        return []  # index not built yet

    res = collection.query(query_texts=[query], n_results=top_n)
    ids = res.get("ids", [[]])[0]
    return [int(i) for i in ids]


def rag_web_snippets(query: str, top_n: int = 6) -> list[dict]:
    chroma = Client(Settings(persist_directory=CHROMA_DIR))
    try:
        collection = chroma.get_collection(name="yuh_website")
    except NotFoundError:
        return []  # website index not built yet

    q_emb = embed(query)
    res = collection.query(query_embeddings=[q_emb], n_results=top_n)

    out = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        out.append({"text": doc, "url": meta.get("url")})
    return out
