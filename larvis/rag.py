from urllib.parse import urlparse

import chromadb
import ollama

from larvis.config import settings


def _chroma() -> chromadb.HttpClient:
    parsed = urlparse(settings.chroma_host)
    return chromadb.HttpClient(host=parsed.hostname, port=parsed.port or 8000)


def search(query: str, top_k: int | None = None) -> list[str]:
    k = top_k if top_k is not None else settings.rag_top_k
    ollama_client = ollama.Client(host=settings.ollama_host)
    collection = _chroma().get_collection(settings.chroma_collection)
    resp = ollama_client.embeddings(model=settings.ollama_embed_model, prompt=query)
    results = collection.query(query_embeddings=[resp.embedding], n_results=k)
    return results["documents"][0]


def ask(query: str) -> str:
    chunks = search(query)
    context = "\n\n---\n\n".join(chunks)
    prompt = (
        "You are Larvis, a personal assistant. Use the following context from "
        "the user's LifeOS vault to answer their question. If the context does "
        "not contain enough information to answer, say so clearly.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query}"
    )
    resp = ollama.Client(host=settings.ollama_host).generate(
        model=settings.ollama_model, prompt=prompt
    )
    return resp.response
