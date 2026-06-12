# Larvis Phase 7 — Orchestrator Layer Design Spec

**Date:** 2026-06-11
**Status:** Approved (design)
**Tracking:** [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)

## Summary

A **general intent router** — the "Larvis front door." One natural-language request is routed
across the six existing agents (vault, LifeOS, YNAB, Calendar, Gmail, Skylight), their read
results are synthesized into a single answer, and write requests are handled through a safe
propose→confirm protocol. It realizes the long-standing architecture rule in `CLAUDE.md`
("agents do not talk to each other directly — they go through the Larvis orchestrator") and
the PHA-52 vision of Larvis as the high-level orchestrator of scoped agents.

**Routing brain = hybrid:** Python does the deterministic routing (keyword/pattern rules decide
which agents to consult and whether the intent is a write); the local LLM (Ollama 8B) is used
only to **narrate/synthesize** read results and to **extract structured parameters** for a
proposed write. This keeps the system private and CLI-capable while avoiding the 8B's weak
spot — open-ended multi-agent reasoning is never trusted; humans confirm every mutation.

## Goals (v1)

- A single entry point, `larvis_orchestrate(query)`, that:
  - routes the query to the relevant agent(s) via deterministic rules,
  - gathers each agent's read result,
  - synthesizes one concise answer with the 8B (degrading to a labeled concatenation).
- **Read + confirmed actions:** for a write request, return a structured **proposal**; execute
  only on an explicit `larvis_confirm(token)`.
- Reuse every agent's existing read/write functions — **no new agent code**.

## Non-goals (v1) — explicitly deferred

- **No open-ended LLM routing** — the 8B never decides which agents to call (rules do).
- **No auto-writes** — the orchestrator never mutates state on the first call; always propose→confirm.
- **Write set limited to two clean actions:** `skylight_add_chore` and `lifeos_commit`. Deferred:
  `skylight_complete_chore` (needs an NL→chore-id lookup), and any Calendar/YNAB/Gmail writes
  (those agents are read-only).
- **No mixed read+write in one turn** (e.g. "add a chore for whoever has the lightest week").
- **No persistence of pending actions across processes** — tokens live in the server process
  (fine for the persistent MCP server; the CLI proposes + confirms within one session).
- **No multi-turn planning / scheduling / proactive nudges** — on-demand only.

## Architecture

### Package layout — `larvis/orchestrator/`

```
larvis/orchestrator/
  __init__.py
  router.py       # route(query) -> agents; is_write_intent; detect_action
  adapters.py     # per-agent read adapters + write-action registry + param extraction
  synthesize.py   # 8B narration of gathered read results; degrade to labeled concat
  pending.py      # propose -> token store -> execute (single-use, in-process)
  tools.py        # orchestrate(query, session_id) + confirm(token)
```

### MCP tools (registered in `server.py`)

| Tool | Signature | Description |
|------|-----------|-------------|
| `larvis_orchestrate` | `(query: str) -> str` | Front door. Routes → gathers reads → synthesizes one answer. For a write request, returns a confirmable proposal. |
| `larvis_confirm` | `(token: str) -> str` | Executes the previously proposed write action and clears the token. |

> `larvis_ask` already exists (vault RAG) and is kept; the orchestrator supersets it (vault is
> just one routable agent). The front-door name is `larvis_orchestrate`.

### Router (`router.py`) — deterministic, pure

- `route(query) -> list[str]`: a keyword/pattern map selects relevant agents. Indicative keywords:
  - `calendar`: calendar, schedule, meeting, agenda, free, busy, appointment, when am I
  - `ynab`: budget, spend, afford, money, cost, bill, paycheck, category, "$"
  - `gmail`: email, inbox, mail, message, unread, reply
  - `skylight`: chore, chores, kids, "up for grabs", member names
  - `lifeos`: task, project, todo, commitment, overdue, plan
  - `vault`: note, journal, vault, wrote, document
  - Falls back to `["lifeos"]` when nothing matches.
- `is_write_intent(query) -> bool`: write verbs (add, create, schedule, mark, complete, assign,
  remind, remember).
- `detect_action(query) -> dict | None`: for write intent, selects the target from the known
  write set (`{"tool": "skylight_add_chore", "schema": [...]}` or `{"tool": "lifeos_commit", ...}`);
  returns `None` if no known action matches (orchestrator then asks the user to be explicit).

### Read adapters (`adapters.py`)

Each adapter maps the NL query to a text block using the agent's existing function. No new agent
code:

| Agent | Adapter calls |
|-------|---------------|
| calendar | `gcal_tools.ask(query)` |
| ynab | `ynab_tools.ask(query)` |
| gmail | `gmail_tools.ask(query)` |
| lifeos | `lifeos_tools.ask(query, session_id)` |
| vault | `rag.ask(query)` |
| skylight | `skylight_tools.chores("week")` (no NL ask; hand over the chore board) |

A `WRITE_TOOLS` registry maps the known write tool names to their callables
(`skylight_tools.add_chore`, `lifeos_tools.commit`). `extract_params(schema, query) -> dict`
asks the 8B for structured JSON params and parses them; malformed/empty output raises so the
orchestrator can ask the user to restate.

### Synthesizer (`synthesize.py`)

`synthesize(query, blocks: dict[str, str]) -> str` builds a prompt from the labeled agent blocks
and asks the 8B to answer the user's request using only those results, concisely. On any Ollama
error it returns the labeled concatenation of blocks (mirrors `ynab_ask`).

### Pending actions (`pending.py`)

In-process single-use token store:
- `propose(action: dict) -> str` — stores `{tool, params, describe}` under a short uuid, returns the token.
- `get(token) -> dict | None`
- `execute(token) -> str` — pops the action, dispatches to `WRITE_TOOLS[tool](**params)`, returns
  the agent tool's confirmation echo; unknown/expired token returns a friendly message.

### Data flow

**Read:** `larvis_orchestrate("time and budget for a date night Friday?")` → `route` → `{calendar, ynab}`
→ `adapters` run `gcal.ask` + `ynab.ask` → `synthesize` → *"Friday 6–9pm is open; you have $120 left in dining."*

**Write:** `larvis_orchestrate("add take out trash to Cal tomorrow")` → `is_write_intent` true →
`detect_action` → `skylight_add_chore` → `extract_params` (8B) → `{member: "Cal", summary: "take out
trash", when: "tomorrow"}` → `pending.propose` → returns *"Proposed: add chore 'take out trash' to
Cal for tomorrow. Confirm with `larvis_confirm("a1b2c3")`."* → `larvis_confirm("a1b2c3")` →
`skylight_tools.add_chore(...)` → *"✓ Added …"*.

## Write safety

- The orchestrator **never writes on the first call** — write intent always yields a proposal.
- The proposal echoes the **8B-extracted params** so the user catches a mis-parse before confirming.
- Execution calls the **real agent tools**, which run their own validation (unknown member, bad date).
- Tokens are **single-use** and cleared on execute.
- Known write set is small and explicit (no general "do anything" mutation surface).

## Error handling

- No agent keyword match → fall back to `lifeos` (always returns something useful).
- **8B down during synthesis** → labeled concatenation of agent blocks (no failure).
- **8B down / unparseable during param extraction** → no write; return "Looks like you want to
  <action> but I couldn't parse the details — specify <schema fields>."
- A read adapter that errors returns its agent's `"... error: ..."` string into its block — one
  failing agent never blanks the synthesis.
- Unknown/expired confirm token → friendly message. Write execution errors surface from the agent tool.

## Testing strategy (mirrors the agents)

- **Unit (TDD, no network):** `route` mapping (single/multi/fallback), `is_write_intent`,
  `detect_action`; `pending.propose/get/execute` roundtrip (fake `WRITE_TOOLS`); `synthesize`
  degrade-to-concat (monkeypatched Ollama); read-adapter dispatch (monkeypatched agent tools);
  `extract_params` JSON wrapper (valid → dict, malformed → raises); `orchestrate` read path and
  write-proposal path; `confirm` executes. ~14–16 tests.
- **Live smoke:** a couple real cross-agent read queries + one write propose→confirm against the
  real agents.

## Dependencies

No new Python dependencies. Depends on **all six agents being present** — including Phase 6
(Skylight). This branch is stacked on `phase6-skylight-agent`; it rebases onto `main` once Phase 6
merges.

## Wiring checklist (for the plan)

- `larvis/orchestrator/{__init__,router,adapters,synthesize,pending,tools}.py`
- `tests/test_orchestrator_{router,pending,synthesize,adapters,tools}.py`
- `larvis/server.py` — 2 `@mcp.tool()` wrappers (`larvis_orchestrate`, `larvis_confirm`)
- `larvis/cli.py` — optional `larvis orchestrate "<query>"` command
- `CLAUDE.md` — tools table + orchestrator notes
- Live smoke test + Linear sub-issues under PHA-52
