# CLAUDE.md

This file provides guidance to Claude Code when working in the larvis repo.

## What is Larvis

Larvis is a local MCP server + RAG pipeline. It serves a local LLM (Ollama), indexes an Obsidian vault into ChromaDB, and exposes tools to Claude Code and a terminal CLI. See README for architecture overview.

## Stack

- **Language:** Python 3.12+
- **MCP framework:** FastMCP
- **RAG:** ollama Python client + ChromaDB + tiktoken (no LlamaIndex)
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
# 1. Start native Ollama (Mac app — uses Metal GPU)
#    Download from https://ollama.com if not installed
ollama serve &                 # or launch the menu bar app
ollama pull llama3.1:8b        # first time only (~4.7 GB)
ollama pull nomic-embed-text   # first time only (~274 MB)

# 2. Start Docker services (chromadb + larvis only — no ollama container)
colima start --memory 4        # 4 GB is enough without ollama in Docker
cp .env.example .env           # configure VAULT_PATH etc. (first time only)
docker compose up -d
docker compose logs -f larvis  # should show "Ollama ready."

# 3. Use the CLI
uv run larvis status           # health check
uv run larvis reindex          # index vault (fast with Metal GPU)
uv run larvis ask "..."        # query
```

## Starting larvis

```bash
colima start --memory 4   # start Docker runtime (if not running)
make start                 # launches Ollama app + docker compose up
# ChromaDB data persists across restarts — reindex only needed on first run or after vault changes
uv run larvis reindex      # first time only, or after significant vault updates
```

MCP reconnects automatically in Claude Code after restart. If larvis doesn't appear in `/mcp`, check `~/.claude.json` → top-level `mcpServers.larvis`.

## Known issues / architecture notes

| Issue | Fix |
|-------|-----|
| Ollama in Docker has no Metal GPU access | Ollama runs natively on Mac; only chromadb + larvis are in Docker |
| larvis container reaches Mac Ollama via | `http://host.docker.internal:11434` (set in docker-compose environment) |
| CLI reaches Ollama via | `http://localhost:11434` (set in .env) |
| ChromaDB data path | Volume mounts to `/data` (container's `config.yaml`); was wrong path before fix |
| lb auth inside Docker | `LINEAR_API_KEY` in `.env` — lb reads it via env var, no `~/.config/lb` needed |
| FastMCP transport | Must use `transport="streamable-http"` in `server.py` — Claude Code connects to `/mcp`, not `/sse` |
| YNAB cache empty on first run | Run `ynab_sync()` once to populate — persists across restarts |
| Skylight is an unofficial API | Reverse-engineered `app.ourskylight.com`; email/password in `.env`, token cached in `.skylight/`. Confirm payloads via HAR if calls break. |
| Gmail multi-account | One OAuth token per inbox in `.gmail/token-<email>.json`; run `larvis gmail-auth <account>` per account |

## MCP tools (Phase 1 + 2 + 3 + 4 + 5 + 6)

| Tool | Signature | Description |
|------|-----------|-------------|
| `larvis_ask` | `(query: str) -> str` | RAG + generation |
| `larvis_search` | `(query: str, top_k?: int) -> List[str]` | Raw vault search |
| `larvis_status` | `() -> dict` | Health check |
| `lifeos_briefing` | `(session_id: str) -> str` | Morning kickoff — projects, tasks, commitments |
| `lifeos_ask` | `(query: str, session_id: str) -> str` | Memory-aware vault query |
| `lifeos_commit` | `(text: str) -> str` | Store a persistent commitment |
| `lifeos_sync_tasks` | `() -> str` | Sync vault `#to-linear` tasks to Linear via lb |
| `ynab_sync` | `() -> str` | Refresh local YNAB cache from YNAB API |
| `ynab_status` | `() -> str` | Budget dashboard — TBB, age of money, over-budget |
| `ynab_ask` | `(query: str) -> str` | NL budget query — Python math, Ollama narrates |
| `ynab_upcoming` | `() -> str` | Scheduled transactions due in next 14 days |
| `calendar_agenda` | `(range?: str) -> str` | Calendar agenda — "today" or "week" |
| `calendar_find_time` | `(duration_minutes: int, within?: str) -> str` | Open slots in working hours |
| `calendar_ask` | `(query: str) -> str` | NL question about your calendar (next 7 days) |
| `calendar_status` | `() -> str` | Calendar auth check + configured calendars |
| `gmail_triage` | `(within?: str) -> str` | Prioritized unread-mail digest across accounts |
| `gmail_search` | `(query: str) -> str` | Search mail (Gmail operators) across accounts |
| `gmail_ask` | `(query: str) -> str` | NL question about your recent email (7 days) |
| `gmail_status` | `() -> str` | Per-account Gmail auth check + unread counts |
| `skylight_chores` | `(within?: str) -> str` | Chores grouped by member (+ Up for Grabs) |
| `skylight_add_chore` | `(member, summary, when?) -> str` | Add/assign a chore (or up-for-grabs) |
| `skylight_complete_chore` | `(chore_id: str) -> str` | Mark a chore complete |
| `skylight_status` | `() -> str` | Skylight auth check + frame + members |

## Session ID convention

Pass any stable string as `session_id` for lifeos tools. In Claude Code, use the conversation ID or any UUID. The same `session_id` groups conversation history together for multi-turn memory.

## Vault task sync convention

To sync a vault task to Linear, add `#to-linear` to any unchecked checkbox task:
```
- [ ] Fix the dishwasher gasket #to-linear
```
Then call `lifeos_sync_tasks` to push it to Linear via lb.

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
