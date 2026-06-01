from pathlib import Path
from urllib.parse import urlparse

import chromadb
import frontmatter
import ollama
import tiktoken

from larvis.config import settings


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    if len(tokens) <= size:
        return [text]
    chunks = []
    i = 0
    while i < len(tokens):
        chunk_tokens = tokens[i : i + size]
        chunks.append(enc.decode(chunk_tokens))
        if i + size >= len(tokens):
            break
        i += size - overlap
    return chunks


def _chroma() -> chromadb.HttpClient:
    parsed = urlparse(settings.chroma_host)
    return chromadb.HttpClient(host=parsed.hostname, port=parsed.port or 8000)


def index_vault() -> int:
    vault = Path(settings.vault_path)
    if not vault.exists():
        raise RuntimeError(f"Vault path not found: {vault}")

    ollama_client = ollama.Client(host=settings.ollama_host)
    collection = _chroma().get_or_create_collection(settings.chroma_collection)

    doc_count = 0
    for md_file in vault.rglob("*.md"):
        try:
            post = frontmatter.load(md_file)
        except Exception:
            continue
        content = post.content.strip()
        if not content:
            continue
        metadata = {
            "file": str(md_file.relative_to(vault)),
            "type": str(post.get("type", "")),
            "tags": ",".join(str(t) for t in post.get("tags", [])),
            "date": str(post.get("date", "")),
        }
        chunks = chunk_text(content, settings.chunk_size, settings.chunk_overlap)
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            resp = ollama_client.embeddings(
                model=settings.ollama_embed_model, prompt=chunk
            )
            collection.upsert(
                ids=[f"{md_file.relative_to(vault)}:{i}"],
                embeddings=[resp.embedding],
                documents=[chunk],
                metadatas=[metadata],
            )
            doc_count += 1

    return doc_count
