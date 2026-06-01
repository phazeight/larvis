# Larvis

Personal AI productivity orchestrator. Local-first, privacy-preserving, LifeOS-aware.

Larvis is a local MCP server that sits on top of your Obsidian vault, a local LLM (via Ollama), and a vector store (ChromaDB). It answers questions about your life, projects, and tasks using your own notes as context — running entirely on your machine.

## What it does (Phase 1)

- Serves a local LLM (llama3.1:8b) via Ollama with Mac Metal GPU acceleration
- Indexes your LifeOS Obsidian vault into a vector store for RAG
- Exposes three MCP tools usable from Claude Code or a terminal CLI:
  - `larvis_ask` — ask anything, answered with vault context
  - `larvis_search` — raw semantic search over vault chunks
  - `larvis_status` — health check

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

Vault is bind-mounted read-only. Larvis never writes to it.

## Quick start

```bash
cp .env.example .env
# Set VAULT_PATH to your Obsidian vault in .env

docker compose up -d
larvis reindex      # index vault into ChromaDB (~2-5 min first run)
larvis status       # verify everything is green
larvis ask "what are my active projects?"
```

## CLI

```bash
larvis ask "..."        # RAG query → Ollama generation
larvis search "..."     # semantic search, returns raw chunks
larvis reindex          # re-index vault into ChromaDB
larvis status           # health check
```

## Configuration

All config via `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `VAULT_PATH` | — | Absolute path to your Obsidian vault (required) |
| `OLLAMA_MODEL` | `llama3.1:8b` | Generation model |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `RAG_TOP_K` | `5` | Number of chunks to retrieve per query |
| `CHUNK_SIZE` | `500` | Token chunk size for indexing |
| `CHUNK_OVERLAP` | `50` | Overlap between chunks |

## Phase roadmap

| Phase | Scope |
|-------|-------|
| **1 — Platform** | Ollama + ChromaDB + MCP server + vault RAG + CLI. Stable, queryable. |
| 2 — LifeOS Agent | Daily planning, todos, project tracking using vault context. Multi-turn memory. |
| 3 — Financial Agent | YNAB integration, budget queries. |
| 4 — Communication | Gmail triage, GCal read/write. |
| 5 — Family + Creativity | Skylight (kids' chores), inspiration agent. |

## Stack

- [Ollama](https://ollama.com) — local LLM serving
- [ChromaDB](https://trychroma.com) — vector store
- [FastMCP](https://github.com/jlowin/fastmcp) — MCP server framework
- [LlamaIndex](https://llamaindex.ai) — RAG pipeline
- Docker Compose — local orchestration

## Docs

- [Phase 1 Design Spec](docs/superpowers/specs/2026-06-01-larvis-phase1-design.md)
