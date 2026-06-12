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


_NO_INFO = "I couldn't find anything about that in your vault."


def _build_prompt(query: str, context: str) -> str:
    return (
        "You are Larvis, a personal assistant. Answer the question using ONLY the "
        "context below from the user's LifeOS vault. Do NOT use outside knowledge and "
        "do NOT pull in unrelated notes. If the context does not directly address the "
        f"question, reply EXACTLY with: {_NO_INFO}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query}"
    )


def ask(query: str) -> str:
    chunks = [c for c in search(query) if c and c.strip()]
    if not chunks:
        return _NO_INFO
    context = "\n\n---\n\n".join(chunks)
    resp = ollama.Client(host=settings.ollama_host).generate(
        model=settings.ollama_model, prompt=_build_prompt(query, context)
    )
    return resp.response
