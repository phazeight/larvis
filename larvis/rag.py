import re
from urllib.parse import urlparse

import chromadb
import ollama

from larvis.config import settings

# Question/filler words that carry little retrieval signal — dropped so exact
# content terms (names, amounts, nouns) drive the lexical half of hybrid search.
_STOPWORDS = {
    "how", "much", "many", "did", "do", "does", "i", "say", "said", "to", "the", "a",
    "an", "what", "whats", "when", "where", "why", "who", "my", "is", "are", "was",
    "were", "of", "in", "on", "for", "and", "or", "about", "you", "me", "with", "that",
    "this", "it", "will", "can", "should", "would", "there", "here", "any", "some",
    "get", "got", "have", "has", "had", "tell", "show",
}


def _chroma() -> chromadb.HttpClient:
    parsed = urlparse(settings.chroma_host)
    return chromadb.HttpClient(host=parsed.hostname, port=parsed.port or 8000)


def _salient_terms(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9$]+", query.lower())
    return [w for w in words if len(w) >= 2 and w not in _STOPWORDS]


def _merge(lexical: list[str], vector: list[str], k: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for doc in [*lexical, *vector]:
        if doc not in seen:
            seen.add(doc)
            out.append(doc)
        if len(out) >= k:
            break
    return out


def search(query: str, top_k: int | None = None) -> list[str]:
    k = top_k if top_k is not None else settings.rag_top_k
    ollama_client = ollama.Client(host=settings.ollama_host)
    collection = _chroma().get_collection(settings.chroma_collection)
    embedding = ollama_client.embeddings(
        model=settings.ollama_embed_model, prompt=query
    ).embedding

    # Semantic half: nearest chunks by embedding.
    vector = collection.query(query_embeddings=[embedding], n_results=k)["documents"][0]

    # Lexical half: nearest chunks *that contain* the query's salient terms, so an
    # exact name/amount always pulls its chunk into contention even when the question
    # phrasing embeds far from the answering statement.
    lexical: list[str] = []
    terms = _salient_terms(query)
    if terms:
        clause = (
            {"$or": [{"$contains": t} for t in terms]}
            if len(terms) > 1
            else {"$contains": terms[0]}
        )
        try:
            lexical = collection.query(
                query_embeddings=[embedding], where_document=clause, n_results=k
            )["documents"][0]
        except Exception:
            lexical = []

    return _merge(lexical, vector, k)


_NO_INFO = "I couldn't find anything about that in your vault."


def _build_prompt(query: str, context: str) -> str:
    return (
        "You are Larvis, a personal assistant. Answer the question using ONLY the context "
        "below from the user's LifeOS vault; do not use outside knowledge. If the answer "
        "appears anywhere in the context, state it directly and concisely. Only when the "
        f"context is unrelated to the question, reply exactly: {_NO_INFO}\n\n"
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
