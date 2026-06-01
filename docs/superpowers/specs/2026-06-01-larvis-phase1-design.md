---
name: larvis-phase1-design
description: Phase 1 design spec for Larvis — local MCP server with Ollama, ChromaDB, and vault RAG
metadata:
  type: project
  status: approved
  date: 2026-06-01
---

# Larvis Phase 1 — Design Spec

**Status:** Approved  
**Date:** 2026-06-01  
**Linear:** [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)

---

## Vision

Larvis is a personal AI productivity orchestrator. Long-term it manages budgets, calendar, email, and LifeOS planning via tightly scoped local agents. Phase 1 is intentionally minimal: a stable, queryable local platform with no domain agents. The goal is infrastructure that doesn't crash, with a working vault RAG pipeline and MCP interface.

---

## Phase 1 Scope

**In scope:**
- Docker Compose stack (ollama, chromadb, larvis) running on Mac
- Ollama serving llama3.1:8b (generation) and nomic-embed-text (embeddings)
- Vault RAG pipeline: index LifeOS Obsidian vault → ChromaDB → answer queries
- MCP server exposing three tools: `larvis_ask`, `larvis_search`, `larvis_status`
- Terminal CLI: `larvis ask`, `larvis search`, `larvis reindex`, `larvis status`

**Out of scope for Phase 1:**
- Domain agents (LifeOS, YNAB, Gmail, GCal, Skylight, inspiration)
- Multi-turn conversation history
- Fine-tuning or model training
- Web UI
- Scheduled indexing (manual reindex only)
- Authentication

---

## Architecture

```
Docker Compose (Mac dev):
┌─────────────────────────────────────────────────────┐
│  ┌──────────┐   ┌──────────┐   ┌─────────────────┐ │
│  │  ollama  │   │ chromadb │   │  larvis          │ │
│  │ llama3.1 │◄──│ vec store│◄──│  MCP + RAG       │ │
│  └──────────┘   └──────────┘   └─────────────────┘ │
└─────────────────────────────────────────────────────┘
                                         ▲
                               [Claude Code MCP]
                               [Terminal CLI]
```

Three containers, one compose file. Vault bind-mounted read-only into larvis at `/vault`.

---

## Components

### `ollama` container
- Serves two models: `llama3.1:8b` (generation) and `nomic-embed-text` (embeddings)
- Uses Mac Metal GPU via official Ollama Docker image
- Models configured via `OLLAMA_MODEL` and `OLLAMA_EMBED_MODEL` env vars

### `chromadb` container
- Stores vault embeddings
- Persisted to named Docker volume `larvis_chroma`
- Re-index only required when vault changes

### `larvis` container
Three internal sub-components:

**Indexer** (`larvis/indexer.py`)
- Walks `/vault`, reads all `.md` files
- Chunks into ~500-token segments with 50-token overlap
- Stores frontmatter metadata (type, tags, date, project) with each chunk
- Embeds via Ollama, upserts into ChromaDB

**RAG engine** (`larvis/rag.py`)
- Embeds incoming query via Ollama
- Retrieves top-k chunks from ChromaDB (default k=5)
- Builds context-augmented prompt
- Streams response from Ollama generation model

**MCP server** (`larvis/server.py`)
- FastMCP-based
- Exposes: `larvis_ask`, `larvis_search`, `larvis_status`

### CLI (`larvis/cli.py`)
Thin wrapper calling Python functions directly (no HTTP overhead).

---

## Data Flow

### Indexing
```
Vault .md files
  → Read + split (~500 tokens, 50 overlap)
  → Embed via nomic-embed-text (Ollama)
  → Upsert into ChromaDB with metadata (file, type, tags, date)
```

### Query
```
User query
  → Embed via nomic-embed-text
  → Cosine similarity search → top-5 chunks from ChromaDB
  → Prompt assembly:
      "You are Larvis, a personal assistant. Use the following context
       from the user's LifeOS vault to answer their question.
       Context: [chunks]
       Question: [query]"
  → Stream to Ollama (llama3.1:8b)
  → Return response
```

Each query is stateless. No conversation history in Phase 1.

---

## MCP Tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `larvis_ask` | `(query: str) -> str` | Full RAG + generation |
| `larvis_search` | `(query: str, top_k: int = 5) -> List[str]` | Raw semantic search, returns source chunks |
| `larvis_status` | `() -> dict` | Health: Ollama up, index doc count, last reindex time |

---

## Error Handling

- **Ollama not ready:** `larvis_status` probes `/api/tags`. On startup, retry 5× with 3s delay before fatal exit.
- **ChromaDB empty:** `larvis_ask` returns `"Vault not indexed — run larvis reindex"` rather than hallucinating.
- **Vault path missing:** Container exits with a clear error at startup.
- **All other failures:** Surface as plain error strings to caller. No retries, no silent fallbacks.

---

## Testing

| Test | Method |
|------|--------|
| Smoke test | `docker compose up` → `larvis status` returns green |
| Index test | `larvis reindex` completes, ChromaDB reports >0 documents |
| RAG test | `larvis ask "what are my active projects?"` returns response citing a real vault project (manual eyeball) |

No unit tests in Phase 1. Integration testing against the real stack is more valuable at this scale.

---

## Configuration

All config via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `VAULT_PATH` | — | Absolute path to Obsidian vault (required) |
| `OLLAMA_MODEL` | `llama3.1:8b` | Generation model |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `RAG_TOP_K` | `5` | Chunks retrieved per query |
| `CHUNK_SIZE` | `500` | Token chunk size |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |

---

## Phase 1 Exit Criteria

1. `docker compose up -d` completes without errors
2. `larvis status` returns all-green (Ollama up, ChromaDB reachable, index non-empty)
3. `larvis reindex` completes in <10 min on a ~500-file vault
4. `larvis ask "what are my active projects?"` returns a coherent answer referencing actual vault content
5. No container crashes after 30 minutes idle

---

## Future Phases

| Phase | Scope |
|-------|-------|
| 2 — LifeOS Agent | Daily planning, todos, project tracking. Multi-turn memory. |
| 3 — Financial Agent | YNAB integration, budget queries. |
| 4 — Communication | Gmail triage, GCal read/write. |
| 5 — Family + Creativity | Skylight (kids' chores), inspiration agent. |
