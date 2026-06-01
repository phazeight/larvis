# Larvis Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stable, queryable local AI platform — three Docker containers (Ollama + ChromaDB + Larvis MCP server) with vault RAG and a terminal CLI — that passes all Phase 1 exit criteria.

**Architecture:** `larvis` Python service runs as a FastMCP SSE server inside Docker, indexing the Obsidian vault into ChromaDB using Ollama embeddings, then answering RAG queries. The CLI runs natively on Mac and talks to the same exposed Docker ports. Claude Code connects to the MCP server via SSE at `http://localhost:8765/sse`.

**Tech Stack:** Python 3.12, uv, FastMCP, ollama (Python client), chromadb (Python client), click, python-frontmatter, tiktoken, pydantic-settings, httpx, Docker Compose

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `pyproject.toml` | Create | Dependencies, package config, `larvis` CLI entry point |
| `.gitignore` | Create | Ignore `.env`, `.venv/`, `__pycache__/`, chroma data |
| `Dockerfile` | Create | Build larvis container from Python 3.12 slim |
| `docker-compose.yml` | Create | Orchestrate ollama, chromadb, larvis; mount vault read-only |
| `.env.example` | Modify | Add `OLLAMA_HOST`, `CHROMA_HOST` fields |
| `larvis/__init__.py` | Create | Package marker |
| `larvis/config.py` | Create | `Settings` via pydantic-settings — all env vars with defaults |
| `larvis/health.py` | Create | `get_status()` — probe Ollama + ChromaDB; shared by server and CLI |
| `larvis/indexer.py` | Create | `chunk_text()` + `index_vault()` — walk vault, chunk, embed, upsert |
| `larvis/rag.py` | Create | `search()` + `ask()` — embed query, retrieve chunks, generate |
| `larvis/server.py` | Create | FastMCP server; three tool definitions; `main()` starts SSE on port 8765 |
| `larvis/__main__.py` | Create | Container entrypoint — checks vault path, waits for Ollama, calls `main()` |
| `larvis/cli.py` | Create | Click CLI: `ask`, `search`, `reindex`, `status` |
| `.claude/settings.json` | Create | Claude Code MCP config pointing at `http://localhost:8765/sse` |
| `tests/__init__.py` | Create | Package marker |
| `tests/test_indexer.py` | Create | Unit tests for `chunk_text` (no Docker required) |

---

## Task 1: Project scaffold

**Files:** `pyproject.toml`, `.gitignore`, `larvis/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "larvis"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "ollama>=0.4",
    "chromadb>=0.5",
    "fastmcp>=2.0",
    "click>=8.0",
    "python-frontmatter>=1.0",
    "tiktoken>=0.7",
    "pydantic-settings>=2.0",
    "httpx>=0.27",
]

[project.scripts]
larvis = "larvis.cli:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
]
```

- [ ] **Step 2: Create .gitignore**

```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
dist/
*.egg-info/
```

- [ ] **Step 3: Create package and test markers**

```bash
mkdir -p larvis tests
touch larvis/__init__.py tests/__init__.py
```

- [ ] **Step 4: Install dependencies**

```bash
cd /Users/phazeight/repos/larvis
uv sync
```

Expected: `.venv/` created, all packages installed without errors. No red text.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore larvis/__init__.py tests/__init__.py
git commit -m "chore: project scaffold and dependencies"
```

---

## Task 2: Config module

**Files:** `larvis/config.py`, `.env.example` (modify)

- [ ] **Step 1: Create larvis/config.py**

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    vault_path: Path
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    chroma_host: str = "http://localhost:8000"
    chroma_collection: str = "vault"
    rag_top_k: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 50


settings = Settings()
```

- [ ] **Step 2: Replace .env.example with updated version**

```
# Required
VAULT_PATH=/Users/yourname/Documents/LifeOs

# Service hosts (CLI on Mac uses localhost; docker-compose overrides these for containers)
OLLAMA_HOST=http://localhost:11434
CHROMA_HOST=http://localhost:8000

# Models — must be pulled before first use: `docker compose exec ollama ollama pull <model>`
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBED_MODEL=nomic-embed-text

# RAG settings
RAG_TOP_K=5
CHUNK_SIZE=500
CHUNK_OVERLAP=50
```

- [ ] **Step 3: Create your .env and verify config loads**

```bash
cp .env.example .env
# Open .env and set VAULT_PATH to your real vault path, e.g.:
# VAULT_PATH=/Users/phazeight/Documents/LifeOs
uv run python -c "from larvis.config import settings; print(settings.vault_path)"
```

Expected: prints your vault path with no errors.

- [ ] **Step 4: Commit**

```bash
git add larvis/config.py .env.example
git commit -m "feat: config module with pydantic-settings"
```

---

## Task 3: Docker Compose + Dockerfile

**Files:** `Dockerfile`, `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv sync --no-dev
COPY larvis/ larvis/
EXPOSE 8765
CMD ["uv", "run", "python", "-m", "larvis"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
services:
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
    volumes:
      - larvis_chroma:/chroma/.chroma

  larvis:
    build: .
    ports:
      - "8765:8765"
    env_file: .env
    environment:
      OLLAMA_HOST: http://ollama:11434
      CHROMA_HOST: http://chromadb:8000
    volumes:
      - ${VAULT_PATH}:/vault:ro
    depends_on:
      - ollama
      - chromadb

volumes:
  ollama_data:
  larvis_chroma:
```

Note: `environment:` in the larvis service overrides the `env_file:` values for `OLLAMA_HOST` and `CHROMA_HOST`, so the container uses internal service names while your Mac CLI uses localhost from `.env`.

- [ ] **Step 3: Start ollama and chromadb (larvis can't start yet — server not written)**

```bash
docker compose up -d ollama chromadb
docker compose ps
```

Expected: ollama and chromadb show `running`. No error lines in `docker compose logs`.

- [ ] **Step 4: Pull required Ollama models**

```bash
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
```

Expected: both models download without errors.
- `llama3.1:8b` is ~4.7 GB — takes 5–15 min on a typical connection.
- `nomic-embed-text` is ~274 MB — fast.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: Docker Compose with ollama, chromadb, larvis services"
```

---

## Task 4: Indexer + unit tests

**Files:** `larvis/indexer.py`, `tests/test_indexer.py`

- [ ] **Step 1: Write failing unit tests**

```python
# tests/test_indexer.py
from larvis.indexer import chunk_text


def test_chunk_text_returns_single_chunk_for_short_text():
    chunks = chunk_text("hello world this is a short note", size=500, overlap=50)
    assert len(chunks) == 1
    assert "hello world" in chunks[0]


def test_chunk_text_splits_text_larger_than_chunk_size():
    # "word" = 1 token in cl100k_base; space = 1 token → 400 words ≈ 799 tokens
    text = " ".join(["word"] * 400)
    chunks = chunk_text(text, size=500, overlap=50)
    assert len(chunks) == 2


def test_chunk_text_overlap_produces_shorter_second_chunk():
    text = " ".join(["word"] * 400)
    chunks = chunk_text(text, size=500, overlap=50)
    # First chunk is full (500 tokens); second chunk is the remainder
    assert len(chunks[0]) > len(chunks[1])
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
uv run pytest tests/test_indexer.py -v
```

Expected: `ImportError: cannot import name 'chunk_text' from 'larvis.indexer'`

- [ ] **Step 3: Implement larvis/indexer.py**

```python
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
uv run pytest tests/test_indexer.py -v
```

Expected:
```
PASSED tests/test_indexer.py::test_chunk_text_returns_single_chunk_for_short_text
PASSED tests/test_indexer.py::test_chunk_text_splits_text_larger_than_chunk_size
PASSED tests/test_indexer.py::test_chunk_text_overlap_produces_shorter_second_chunk
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add larvis/indexer.py tests/test_indexer.py
git commit -m "feat: vault indexer with chunk_text and ChromaDB upsert"
```

---

## Task 5: RAG engine

**Files:** `larvis/rag.py`

(No unit tests — requires live Ollama + ChromaDB; covered by smoke tests in Task 9.)

- [ ] **Step 1: Implement larvis/rag.py**

```python
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
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from larvis.rag import ask, search; print('ok')"
```

Expected: prints `ok` with no errors.

- [ ] **Step 3: Commit**

```bash
git add larvis/rag.py
git commit -m "feat: RAG engine — embed query, retrieve chunks, generate"
```

---

## Task 6: Health module + MCP server

**Files:** `larvis/health.py`, `larvis/server.py`, `larvis/__main__.py`

- [ ] **Step 1: Implement larvis/health.py**

```python
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
```

- [ ] **Step 2: Implement larvis/server.py**

```python
from fastmcp import FastMCP

from larvis import rag
from larvis.health import get_status

mcp = FastMCP("Larvis")


@mcp.tool()
def larvis_ask(query: str) -> str:
    """Ask a question answered using your LifeOS vault as context."""
    if get_status()["index_docs"] == 0:
        return "Vault not indexed — run `larvis reindex` first."
    return rag.ask(query)


@mcp.tool()
def larvis_search(query: str, top_k: int = 5) -> list[str]:
    """Semantic search over your LifeOS vault. Returns raw matching chunks."""
    return rag.search(query, top_k)


@mcp.tool()
def larvis_status() -> dict:
    """Health check — Ollama status, ChromaDB doc count, model config."""
    return get_status()


def main() -> None:
    mcp.run(transport="sse", host="0.0.0.0", port=8765)
```

- [ ] **Step 3: Implement larvis/__main__.py (container entrypoint)**

```python
import sys
import time

import httpx

from larvis.config import settings
from larvis.server import main


def _check_vault() -> None:
    from pathlib import Path
    vault = Path(settings.vault_path)
    if not vault.exists():
        print(f"ERROR: Vault path not found: {vault}", flush=True)
        sys.exit(1)


def _wait_for_ollama() -> None:
    print("Waiting for Ollama...", flush=True)
    for i in range(5):
        try:
            r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=5)
            if r.status_code == 200:
                print("Ollama ready.", flush=True)
                return
        except Exception:
            pass
        if i < 4:
            print(f"  retry {i + 1}/5...", flush=True)
            time.sleep(3)
    print("ERROR: Ollama not ready after 5 retries.", flush=True)
    sys.exit(1)


if __name__ == "__main__":
    _check_vault()
    _wait_for_ollama()
    main()
```

- [ ] **Step 4: Build and start the full stack**

```bash
docker compose build larvis
docker compose up -d
docker compose ps
```

Expected: all three services (`ollama`, `chromadb`, `larvis`) show `running`.

- [ ] **Step 5: Check larvis startup logs**

```bash
docker compose logs larvis
```

Expected output includes:
```
Ollama ready.
```
followed by FastMCP startup messages. No `ERROR` lines.

- [ ] **Step 6: Commit**

```bash
git add larvis/health.py larvis/server.py larvis/__main__.py
git commit -m "feat: health module, FastMCP server, container entrypoint"
```

---

## Task 7: CLI

**Files:** `larvis/cli.py`

- [ ] **Step 1: Implement larvis/cli.py**

```python
import json

import click

from larvis import rag
from larvis.health import get_status
from larvis.indexer import index_vault


@click.group()
def cli() -> None:
    """Larvis — personal AI productivity assistant."""


@cli.command()
@click.argument("query")
def ask(query: str) -> None:
    """Ask a question using your vault as context."""
    if get_status()["index_docs"] == 0:
        click.echo("Vault not indexed — run `larvis reindex` first.")
        return
    click.echo(rag.ask(query))


@cli.command()
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of chunks to return")
def search(query: str, top_k: int) -> None:
    """Semantic search over your vault. Returns raw matching chunks."""
    chunks = rag.search(query, top_k)
    for i, chunk in enumerate(chunks, 1):
        click.echo(f"\n--- Result {i} ---")
        click.echo(chunk)


@cli.command()
def reindex() -> None:
    """Re-index the vault into ChromaDB."""
    click.echo("Indexing vault...")
    count = index_vault()
    click.echo(f"Done — {count} chunks indexed.")


@cli.command()
def status() -> None:
    """Health check — Ollama, ChromaDB, index state."""
    click.echo(json.dumps(get_status(), indent=2))
```

- [ ] **Step 2: Verify CLI help text**

```bash
uv run larvis --help
```

Expected:
```
Usage: larvis [OPTIONS] COMMAND [ARGS]...

  Larvis — personal AI productivity assistant.

Options:
  --help  Show this message and exit.

Commands:
  ask      Ask a question using your vault as context.
  reindex  Re-index the vault into ChromaDB.
  search   Semantic search over your vault. Returns raw matching chunks.
  status   Health check — Ollama, ChromaDB, index state.
```

- [ ] **Step 3: Commit**

```bash
git add larvis/cli.py
git commit -m "feat: CLI with ask, search, reindex, status commands"
```

---

## Task 8: Claude Code MCP config

**Files:** `.claude/settings.json`

- [ ] **Step 1: Create .claude/settings.json**

```bash
mkdir -p .claude
```

```json
{
  "mcpServers": {
    "larvis": {
      "url": "http://localhost:8765/sse"
    }
  }
}
```

Save to `/Users/phazeight/repos/larvis/.claude/settings.json`.

- [ ] **Step 2: Verify FastMCP SSE path**

```bash
curl -s http://localhost:8765/sse
```

Expected: an SSE stream opens (you'll see the connection hang waiting for events — that's correct). Press Ctrl+C to cancel. If you get `connection refused`, check `docker compose logs larvis`.

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "chore: Claude Code MCP config for larvis SSE server"
```

---

## Task 9: Smoke test checklist

Run in order after all code is written and all containers are running.

- [ ] **Step 1: Confirm all containers running**

```bash
docker compose ps
```

Expected: `ollama`, `chromadb`, `larvis` all show `running`. No restarts.

- [ ] **Step 2: Status check — pre-index**

```bash
uv run larvis status
```

Expected:
```json
{
  "ollama": true,
  "chromadb": true,
  "index_docs": 0,
  "model": "llama3.1:8b",
  "embed_model": "nomic-embed-text"
}
```

`index_docs: 0` is correct here — vault not yet indexed.

- [ ] **Step 3: Index the vault**

```bash
uv run larvis reindex
```

Expected: `Done — NNNN chunks indexed.` where NNNN > 0. Takes 2–10 min depending on vault size. If it hangs past 15 min, check `docker compose logs larvis` for embedding errors.

- [ ] **Step 4: Status check — post-index**

```bash
uv run larvis status
```

Expected: `index_docs` is now > 0.

- [ ] **Step 5: RAG smoke test**

```bash
uv run larvis ask "what are my active projects?"
```

Expected: a coherent answer that references at least one real project from your vault. If the response hallucinates or says "I don't have information," check that `index_docs > 0` and `ollama: true` in `larvis status`.

- [ ] **Step 6: Search smoke test**

```bash
uv run larvis search "budget" --top-k 3
```

Expected: 3 vault chunks returned that contain content related to "budget" (if such notes exist in vault). Each result is prefixed with `--- Result N ---`.

- [ ] **Step 7: Idle stability check**

Leave all containers running for 30 minutes, then:

```bash
docker compose ps
```

Expected: all containers still `running` with 0 restarts.

---

## Phase 1 exit criteria

- [ ] `docker compose up -d` completes without errors
- [ ] `larvis status` returns `ollama: true`, `chromadb: true`, `index_docs > 0`
- [ ] `larvis reindex` completes in <10 min
- [ ] `larvis ask "what are my active projects?"` returns a coherent vault-grounded answer
- [ ] No container crashes after 30 minutes idle
