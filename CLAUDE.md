# CLAUDE.md

This file provides guidance to Claude Code when working in the larvis repo.

## What is Larvis

Larvis is a local MCP server + RAG pipeline. It serves a local LLM (Ollama), indexes an Obsidian vault into ChromaDB, and exposes tools to Claude Code and a terminal CLI. See README for architecture overview.

## Stack

- **Language:** Python 3.12+
- **MCP framework:** FastMCP
- **RAG:** LlamaIndex + ChromaDB
- **LLM serving:** Ollama (llama3.1:8b generation, nomic-embed-text embeddings)
- **Infra:** Docker Compose (dev on Mac, deploy to dedicated hardware later)
- **Package manager:** uv

## Key paths

| Path | Purpose |
|------|---------|
| `docker-compose.yml` | Service definitions — ollama, chromadb, larvis |
| `larvis/` | Python package — MCP server, RAG engine, indexer, CLI |
| `larvis/server.py` | FastMCP server entrypoint, tool definitions |
| `larvis/rag.py` | RAG engine — query, retrieve, generate |
| `larvis/indexer.py` | Vault indexer — walk, chunk, embed, upsert |
| `larvis/cli.py` | CLI entry point |
| `.env.example` | Config template |
| `docs/superpowers/specs/` | Design specs |

## Dev workflow

```bash
cp .env.example .env          # configure VAULT_PATH etc.
docker compose up -d          # start all services
docker compose logs -f larvis # tail logs
larvis status                 # health check
larvis reindex                # re-index vault
```

## MCP tools (Phase 1)

| Tool | Signature | Description |
|------|-----------|-------------|
| `larvis_ask` | `(query: str) -> str` | RAG + generation |
| `larvis_search` | `(query: str, top_k?: int) -> List[str]` | Raw vault search |
| `larvis_status` | `() -> dict` | Health check |

## Adding new agents (Phase 2+)

Each agent is a new module in `larvis/agents/`. An agent:
1. Defines its MCP tools in `tools.py`
2. Registers them in `server.py`
3. Has its own integration/config section in `.env.example`

Agents do not talk to each other directly — they go through the Larvis orchestrator.

## Conventions

- Fail fast and visibly — no silent fallbacks
- All config via env vars, never hardcoded paths
- Vault is always read-only — never write to it
- Keep Phase 1 stateless — no conversation history until Phase 2

## Linear

Project tracked in Linear: [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)
