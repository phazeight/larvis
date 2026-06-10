---
type: session
date: 2026-06-10
topics: [phase2, lifeos-agent, mcp, docker, linear]
projects: [larvis]
outcome: Implemented all 8 Phase 2 tasks, fixed MCP connection, lb-in-Docker, .memory/ persistence
---

# Session: 2026-06-10 — Phase 2 LifeOS Agent Implementation

## Quick Reference
**Topics:** Phase 2 implementation, MCP debugging, Docker config, lb integration
**Projects:** larvis (PHA-52)
**Outcome:** All Phase 2 code complete and reviewed; smoke tests mostly passing; two infrastructure fixes applied during testing

---

## Decisions Made

- **MCP transport: streamable-http over SSE** — Claude Code expects `/mcp` endpoint (streamable HTTP), not `/sse`. FastMCP 3.x `transport="streamable-http"` is the correct choice.
- **lb runs inside the Docker container** — The `lifeos_sync_tasks` MCP tool calls `lb create` via subprocess. lb must be installed in the container (not just on the host). Uses `LINEAR_API_KEY` env var for auth.
- **SQLite persisted via host bind mount** — `.memory/lifeos.db` lives on the host at `repos/larvis/.memory/` and is bind-mounted into the container at `/app/.memory`. Survives `make stop && make start`.
- **Linear tickets PHA-62–69 created** for all Phase 2 tasks; PHA-53–60 retroactively marked Done.

---

## Solutions & Fixes

- **MCP not appearing in `/mcp`** — The correct config file is `~/.claude.json` (not `~/.claude/settings.json`). User MCPs live under `mcpServers` at the top level of `.claude.json` with `"type": "http"`.
- **MCP config format** — Use `"type": "http"` (not `"type": "sse"`) with URL pointing to `/mcp`. The `type: "sse"` format is not recognized by Claude Code.
- **`.memory/` permission error on Docker** — Had to `mkdir -p .memory` on the host before Docker could create the bind mount.
- **lb not found in container** — Added bun + lb installation to Dockerfile; lb reads `LINEAR_API_KEY` env var (not `~/.config/lb/config.jsonc`).
- **ChromaDB `false` on restart** — ChromaDB takes a few seconds to start; health check hits it before it's ready. Workaround: `uv run larvis reindex` after restart. Root cause: named volume is `larvis_larvis_chroma` but may not be persisting — needs investigation.
- **mcp__larvis__* permissions** — Added to both `~/.claude/settings.json` allow list and `.claude/settings.json` in project to suppress all tool prompts.

---

## Files Modified

- `larvis/server.py` — Added 4 lifeos MCP tools; switched transport to `streamable-http`
- `larvis/agents/__init__.py` — Created (package marker)
- `larvis/agents/lifeos/__init__.py` — Created (package marker)
- `larvis/agents/lifeos/memory.py` — Created (SQLite turns/commitments/synced_tasks)
- `larvis/agents/lifeos/linear_sync.py` — Created (vault scanner + lb subprocess)
- `larvis/agents/lifeos/tools.py` — Created (briefing, ask, commit, sync_tasks)
- `tests/test_lifeos_memory.py` — Created (7 tests)
- `tests/test_lifeos_sync.py` — Created (5 tests)
- `docker-compose.yml` — Added `.memory/` bind mount, `LINEAR_API_KEY` env var
- `Dockerfile` — Added bun + lb install, `.lb/` copy
- `.gitignore` — Added `.memory/`, `.lb/cache*`, `.lb/issues.jsonl`, `.lb/backups/`
- `.lb/config.jsonc` — Created (lb project config, committed)
- `CLAUDE.md` — Updated with Phase 2 tools, session_id + #to-linear conventions
- `~/.claude.json` — Added `larvis` to top-level `mcpServers`
- `~/.claude/settings.json` — Added `mcp__larvis__*` to permissions allow list
- `.claude/settings.json` — Added `mcp__larvis__*` permissions (project-level)
- `.env` — Added `LINEAR_API_KEY`
- `.env.example` — Added `LINEAR_API_KEY` placeholder

---

## Pending Tasks

- [ ] **Confirm `lifeos_sync_tasks` works end-to-end** — lb is now in the container but the smoke test call was interrupted by a container restart. Needs one clean test: add `#to-linear` task to vault → call `lifeos_sync_tasks()` → verify Linear issue created → call again → verify "No tasks pending sync."
- [ ] **Fix ChromaDB persistence across restarts** — Named volume `larvis_larvis_chroma` may not be persisting. Currently requires `uv run larvis reindex` after every `make stop && make start`. Investigate volume mount path in chromadb container vs where chroma stores data.
- [ ] **Commit docker-compose.yml + Dockerfile changes** — Changes made during smoke test debugging not yet committed.
- [ ] **Mark PHA-69 (smoke test) as Done** in Linear once all exit criteria confirmed.

---

## Key Learnings

- Claude Code user MCP config lives in `~/.claude.json` under top-level `mcpServers`, not in `~/.claude/settings.json`. The `settings.json` file is for permissions/hooks only.
- FastMCP SSE transport (`/sse`) is not compatible with Claude Code's URL-based MCP config. Always use `streamable-http` (`/mcp`) for Claude Code integration.
- Docker named volumes created by `docker compose down` (without `-v`) persist, but the volume name includes the project prefix (`larvis_larvis_chroma` not `larvis_chroma`). Worth verifying volume data actually survives restart.
- lb uses `LINEAR_API_KEY` env var for auth when `~/.config/lb/config.jsonc` isn't available (e.g., inside Docker).
