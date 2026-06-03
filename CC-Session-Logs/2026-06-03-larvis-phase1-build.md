---
type: session
date: 2026-06-03
topics: [larvis, mcp, ollama, chromadb, rag, fastmcp, docker, phase1]
projects: [larvis]
outcome: Built Larvis Phase 1 end-to-end — local MCP server with Ollama, ChromaDB, vault RAG, CLI. All 9 Linear tasks (PHA-53–PHA-61) complete. Smoke tests passing. make start/stop working.
---

# Session: 2026-06-03 — Larvis Phase 1 Full Build

## Quick Reference
**Topics:** Larvis, MCP server, Ollama, ChromaDB, vault RAG, FastMCP, Docker Compose  
**Projects:** larvis (https://github.com/phazeight/larvis)  
**Linear:** PHA-52 parent, PHA-53–PHA-61 sub-tasks  
**Outcome:** Phase 1 complete. `make start` → `larvis ask "what are my active projects?"` returns real vault content. 959 chunks indexed in <2 min with Metal GPU.

---

## Decisions Made

- **MCP-first architecture** — Larvis is a FastMCP SSE server (port 8765), not a standalone chat UI. Claude Code and CLI call the same tools. Obsidian will join as another MCP consumer in a future phase.
- **Ollama native on Mac, not in Docker** — Docker/Colima has no Metal GPU access; each embedding call took 30s–3min on CPU. Switched to `brew install --cask ollama` (native app). llama3.1:8b + nomic-embed-text now embed a 959-chunk vault in <2 min.
- **No LlamaIndex** — used ollama Python client + chromadb Python client + tiktoken directly. Leaner, more explicit, no heavy abstractions.
- **docker-compose has only chromadb + larvis** — ollama removed from compose entirely. larvis container reaches Mac Ollama via `host.docker.internal:11434`.
- **Makefile on/off switch** — `make start/stop/status` from repo root. `stop` kills both the Ollama app AND the `llama-server` subprocess (which lingers after quit).

---

## Solutions & Fixes

1. **Ollama in Docker = no Metal GPU** — embedding calls took 30s–3min each. 58-minute reindex attempt failed mid-run with `httpx.RemoteProtocolError: Server disconnected`. Fix: move Ollama to native Mac app.
2. **Homebrew formula broken** — `brew install ollama` installs from source, missing `llama-server` binary. Error: `llama-server binary not found (checked: ...)`. Fix: `brew install --cask ollama` installs the pre-built Mac app.
3. **llama-server subprocess lingers** — `osascript -e 'quit app "Ollama"'` quits the menu bar app but leaves `llama-server` running at 4.82 GB RAM. Fix: added `pkill -f llama-server` to `make stop`.
4. **tiktoken test fixture wrong** — plan said "400 words ≈ 799 tokens" but `" word"` in cl100k_base is a single token (not two). 400 words = 400 tokens, under the 500 chunk threshold, so tests passed as 1 chunk. Fixed to 600 words.
5. **Dockerfile layer order** — original had `COPY larvis/` before `uv sync`, breaking dep caching. Fixed to `uv sync --no-install-project` first, then copy source, then `uv sync`.
6. **VAULT_PATH in container** — docker-compose needs `VAULT_PATH: /vault` in the larvis container environment, otherwise it inherits the Mac path `/Users/phazeight/Documents/LifeOs` which doesn't exist inside the container.
7. **Ollama:latest crashes** — `ollama/ollama:latest` (v0.24.0) had a fatal Go `synctest` panic. Was pinned to `0.6.2` for Docker; now irrelevant since Ollama is native.
8. **Colima needs 10 GB RAM** — default 6 GB OOMs with llama3.1:8b (4.9 GB) if running in Docker. Now irrelevant since Ollama is native; only chromadb + larvis in Docker, 4 GB is fine.
9. **uv deprecation warning** — `[tool.uv.dev-dependencies]` deprecated. Fixed to `[dependency-groups]` in pyproject.toml.

---

## Files Created/Modified

**New repo: `/Users/phazeight/repos/larvis/`**

| File | Purpose |
|------|---------|
| `README.md` | Project overview, architecture, quick start, phase roadmap |
| `CLAUDE.md` | Dev workflow, known issues, MCP tools, agent conventions |
| `.env.example` | Config template with all env vars |
| `Makefile` | `make start/stop/status` on/off switch |
| `Dockerfile` | Python 3.12-slim, uv, runs `python -m larvis` |
| `docker-compose.yml` | chromadb + larvis only (ollama is native) |
| `pyproject.toml` | Dependencies, CLI entry point, build config |
| `.gitignore` | Ignores .env, .venv, __pycache__ |
| `larvis/__init__.py` | Package marker |
| `larvis/config.py` | Settings via pydantic-settings |
| `larvis/indexer.py` | chunk_text + index_vault |
| `larvis/rag.py` | search + ask |
| `larvis/health.py` | get_status |
| `larvis/server.py` | FastMCP server, 3 tools |
| `larvis/__main__.py` | Container entrypoint with startup checks |
| `larvis/cli.py` | Click CLI: ask, search, reindex, status |
| `tests/__init__.py` | Test package marker |
| `tests/test_indexer.py` | 3 unit tests for chunk_text (no Docker needed) |
| `.claude/settings.json` | Claude Code MCP config → http://localhost:8765/sse |
| `docs/superpowers/specs/2026-06-01-larvis-phase1-design.md` | Approved design spec |
| `docs/superpowers/specs/2026-06-01-larvis-phase1-plan.md` | 9-task implementation plan |
| `docs/runbook.md` | Human-friendly test/operation guide |
| `CC-Session-Logs/2026-06-03-larvis-phase1-build.md` | This file |

---

## Setup & Config

- **Ollama installed:** `brew install --cask ollama` → `/Applications/Ollama.app`
- **Ollama service:** starts on login; `open -a Ollama` to start manually
- **Models pulled:** `llama3.1:8b` (4.9 GB) + `nomic-embed-text` (274 MB)
- **Docker volumes:** `larvis_chroma` (persistent vault index — survives restarts)
- **Vault indexed:** 959 chunks from `/Users/phazeight/Documents/LifeOs`
- **Claude Code MCP:** larvis tools available when containers are up and `.claude/settings.json` is loaded
- **Old Docker images cleaned:** `ollama/ollama:0.6.2` and `ollama/ollama:latest` removed (~16 GB freed)

---

## Pending Tasks

- [ ] Mark PHA-53–PHA-60 as Done in Linear (PHA-61 already marked Done)
- [ ] Mark PHA-52 (parent) as In Progress or Done
- [ ] Begin Phase 2 planning — LifeOS agent (daily planning, todos, project tracking, multi-turn memory)
- [ ] Fix `uv run` on Python 3.14 — venv is being recreated each session (version mismatch between system Python and .venv)

---

## Key Learnings

- Ollama must run natively on Mac for Metal GPU — Docker containers in Colima/Lima run in a Linux VM with no GPU passthrough
- `brew install --cask ollama` not `brew install ollama` — the formula is broken, the cask ships pre-built binaries
- `llama-server` is a child process of Ollama that must be explicitly killed on shutdown
- FastMCP SSE transport: `mcp.run(transport="sse", host="0.0.0.0", port=8765)` — Claude Code connects via `http://localhost:8765/sse`
- cl100k_base tokenization: `" word"` = 1 token (with preceding space), not 2
- ChromaDB `get_or_create_collection` is safe to call on every reindex — upserts don't duplicate
- Docker compose `environment:` overrides `env_file:` — use this to inject container-specific hosts while keeping Mac CLI config in `.env`
