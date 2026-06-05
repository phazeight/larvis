---
name: larvis-phase2-design
description: Phase 2 design spec for Larvis — LifeOS Agent with morning briefing, multi-turn memory, and vault→Linear task sync via lb
metadata:
  type: project
  status: approved
  date: 2026-06-05
---

# Larvis Phase 2 — LifeOS Agent Design Spec

**Status:** Approved  
**Date:** 2026-06-05  
**Linear:** [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)

---

## Vision

Phase 1 delivered a stable local AI platform (Ollama + ChromaDB + MCP server + vault RAG). Phase 2 adds the first domain agent: a LifeOS Agent that knows your projects, remembers what you said, and bridges your Obsidian vault with Linear.

Primary use case: morning kickoff briefing. Secondary: on-demand planning queries throughout the day.

---

## Phase 2 Scope

**In scope:**
- Agent module pattern (`larvis/agents/lifeos/`) — the template all future agents follow
- `lifeos_briefing` — morning kickoff: active projects + overdue tasks + open commitments
- `lifeos_ask` — memory-aware vault RAG (in-session conversation history injected into prompt)
- `lifeos_commit` — store a cross-session commitment/decision persistently
- `lifeos_sync_tasks` — scan vault for `#to-linear` checkbox tasks, create Linear issues via `lb`
- Multi-turn memory: in-session (SQLite turns table) + persistent (commitments table)
- `lb` (linear-beads) integration for agent task tracking and vault→Linear sync

**Out of scope for Phase 2:**
- Bidirectional Linear→vault sync
- Scheduled/proactive briefing push (no scheduler yet)
- Writing to vault files (read-only still)
- YNAB, Gmail, GCal (Phase 3+)

---

## Architecture

Phase 2 extends the existing platform without modifying Phase 1 internals. A new `larvis/agents/lifeos/` module plugs into `server.py` exactly as all future agents will.

```
larvis/
├── agents/
│   ├── __init__.py
│   └── lifeos/
│       ├── __init__.py
│       ├── tools.py        # four MCP tools
│       ├── memory.py       # SQLite — session turns + persistent commitments
│       └── linear_sync.py  # vault #to-linear scanner → lb create
├── server.py               # registers lifeos tools (small addition)
.memory/
└── lifeos.db               # SQLite — gitignored
.lb/
└── config.jsonc            # lb project config — committed
```

`lb` (linear-beads) is installed as a CLI. The LifeOS agent calls it via subprocess for all Linear operations. Issues sync to the Phazeight Linear workspace.

---

## Components

### MCP Tools (`larvis/agents/lifeos/tools.py`)

| Tool | Signature | Description |
|------|-----------|-------------|
| `lifeos_briefing` | `(session_id: str) -> str` | Morning kickoff: active projects + overdue tasks + open commitments. Vault RAG + Ollama generation. |
| `lifeos_ask` | `(query: str, session_id: str) -> str` | Memory-aware vault query. Injects last 10 turns into prompt. |
| `lifeos_commit` | `(text: str) -> str` | Store a commitment that persists across sessions. |
| `lifeos_sync_tasks` | `() -> str` | Scan vault for `#to-linear` tasks, create Linear issues via `lb`, deduplicate. |

### Memory (`larvis/agents/lifeos/memory.py`)

SQLite database at `.memory/lifeos.db` (gitignored, created on first use).

**Tables:**

`turns`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `session_id` | TEXT | Groups turns per session |
| `role` | TEXT | `user` or `assistant` |
| `content` | TEXT | Message content |
| `created_at` | TIMESTAMP | Auto-set |

`commitments`
| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `text` | TEXT | Commitment text |
| `created_at` | TIMESTAMP | When made |
| `resolved_at` | TIMESTAMP | NULL = open |

`synced_tasks`
| Column | Type | Description |
|--------|------|-------------|
| `vault_file` | TEXT | Relative vault path |
| `task_text` | TEXT | Task line content |
| `linear_id` | TEXT | Linear issue ID from `lb` |
| `synced_at` | TIMESTAMP | When synced |

**Public interface:**
- `get_session_context(session_id, last_n=10) -> list[dict]`
- `add_turn(session_id, role, content) -> None`
- `add_commitment(text) -> None`
- `get_open_commitments() -> list[dict]`
- `mark_task_synced(vault_file, task_text, linear_id) -> None`
- `is_task_synced(vault_file, task_text) -> bool`

### Linear Sync (`larvis/agents/lifeos/linear_sync.py`)

- `scan_vault_for_tagged_tasks(vault_path) -> list[dict]` — walks `.md` files, extracts unchecked checkbox tasks containing `#to-linear`
- `sync_tasks() -> int` — for each unsynced task: `subprocess.run(["lb", "create", task_text])`, marks synced in SQLite, returns count

### `lb` configuration (`.lb/config.jsonc`)

```jsonc
{
  "repo_scope": "project",
  "repo_binding_version": 2
}
```

Linear project scope: `larvis` project (PHA-52 parent).

---

## Data Flow

### Morning briefing

```
lifeos_briefing(session_id)
  → RAG search: "active projects" (top-5 vault chunks, type=project)
  → RAG search: "overdue tasks this week" (top-5 vault chunks)
  → get_open_commitments() from SQLite
  → Build prompt:
      "You are Larvis, a personal assistant. Today is {date}.
       Brief the user on their day using this context.
       Active projects: {chunks}
       Open commitments: {commitments}
       Be concise. List projects, surface anything overdue."
  → Ollama generate
  → add_turn(session_id, "assistant", response)
  → Return briefing text
```

### Memory-aware conversation

```
lifeos_ask(query, session_id)
  → add_turn(session_id, "user", query)
  → get_session_context(session_id, last_n=10)
  → RAG search for vault context (top-5 chunks)
  → Build prompt:
      system: "You are Larvis..."
      history: [{role, content}, ...last 10 turns]
      context: "Vault context:\n{chunks}"
      user: query
  → Ollama generate (chat-style prompt)
  → add_turn(session_id, "assistant", response)
  → Return response
```

### Vault → Linear sync

```
lifeos_sync_tasks()
  → scan_vault_for_tagged_tasks(vault_path)
      walks .md files
      extracts: "- [ ] task text #to-linear"
  → for each task:
      if is_task_synced(file, task): skip
      else: subprocess lb create "task text"
            mark_task_synced(file, task, linear_id)
  → return "N tasks synced to Linear"
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `lb` not installed | `lifeos_sync_tasks` returns install instructions, no crash |
| No `#to-linear` tasks | Returns `"No tasks pending sync."` |
| SQLite missing | Created automatically on first use |
| Ollama down | Returns same clear error as `larvis_ask` |
| Empty vault index | `lifeos_briefing` skips RAG, returns commitments-only briefing |

---

## Testing

**Unit tests (no Docker required):**
- `tests/test_lifeos_memory.py` — add/get turns, add/get commitments, sync deduplication (pure SQLite)
- `tests/test_lifeos_sync.py` — `scan_vault_for_tagged_tasks()` with a fixture markdown file

**Smoke tests (manual, stack running):**
1. `lifeos_commit "I said I'd finish learn_go this week"` → verify persists after `make stop && make start`
2. `lifeos_briefing` → returns coherent briefing citing real vault projects
3. Add `- [ ] Test task #to-linear` to any vault note → `lifeos_sync_tasks` creates a Linear issue
4. `lifeos_ask "what did we discuss earlier?"` in same session → references prior turns

---

## Session ID

`session_id` is a UUID passed by the caller (Claude Code or CLI). For CLI use, a new UUID is generated per process. This groups conversation turns per session without requiring server-side session management.

---

## `lb` Onboarding

First-time setup:
```bash
bun install -g github:nikvdp/linear-beads
cd ~/repos/larvis
lb onboard   # authenticates with Linear, creates .lb/ config, updates CLAUDE.md
```

After onboarding, `lb` is the agent's task CLI. `lb create`, `lb list`, `lb done` map to Linear issues in the `larvis` project scope.

---

## Future Phases

| Phase | Scope |
|-------|-------|
| 3 — Financial Agent | YNAB integration, budget queries |
| 4 — Communication | Gmail triage, GCal read/write |
| 5 — Family + Creativity | Skylight (kids' chores), inspiration agent |
