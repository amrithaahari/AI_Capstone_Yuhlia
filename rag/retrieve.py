from chromadb import Client
from chromadb.config import Settings
from openai import OpenAI
import os

CHROMA_DIR = "data/chroma_products"
COLLECTION_NAME = "yuh_products"

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def embed(text: str):
    return client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    ).data[0].embedding

def rag_candidates(query: str, top_n: int = 80) -> list[int]:
    chroma = Client(Settings(persist_directory=CHROMA_DIR))
    collection = chroma.get_collection(
        name=COLLECTION_NAME,
        embedding_function=lambda texts: [embed(t) for t in texts],
    )

    res = collection.query(
        query_texts=[query],
        n_results=top_n,
    )

    ids = res.get("ids", [[]])[0]
    return [int(i) for i in ids]
