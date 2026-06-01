from urllib.parse import urlparse

import chromadb
import ollama

from larvis.config import settings


def get_status() -> dict:
    status: dict = {
        "ollama": False,
        "chromadb": False,
        "index_docs": 0,
        "model": settings.ollama_model,
        "embed_model": settings.ollama_embed_model,
    }
    try:
        ollama.Client(host=settings.ollama_host).list()
        status["ollama"] = True
    except Exception:
        pass
    try:
        parsed = urlparse(settings.chroma_host)
        collection = chromadb.HttpClient(
            host=parsed.hostname, port=parsed.port or 8000
        ).get_collection(settings.chroma_collection)
        status["chromadb"] = True
        status["index_docs"] = collection.count()
    except Exception:
        pass
    return status
