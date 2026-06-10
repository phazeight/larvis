---
name: larvis-phase3-design
description: Phase 3 design spec for Larvis — YNAB Financial Agent with budget status, spending analysis, account balances, and upcoming bills
metadata:
  type: project
  status: approved
  date: 2026-06-10
---

# Larvis Phase 3 — YNAB Financial Agent Design Spec

**Status:** Approved
**Date:** 2026-06-10
**Linear:** [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)

---

## Vision

Phase 2 delivered a LifeOS agent that knows your projects and tasks. Phase 3 adds a YNAB Financial Agent that knows your money — budget status, spending patterns, account balances, and upcoming bills — all queryable in natural language from Claude Code.

Primary use case: quick budget check during the day. Secondary: end-of-month spending analysis.

---

## Phase 3 Scope

**In scope:**
- Agent module `larvis/agents/ynab/` following the Phase 2 agent pattern
- Local SQLite cache of YNAB data (accounts, categories, transactions, scheduled transactions)
- Delta sync via YNAB API `last_knowledge_of_server` — only changed data per sync
- Four MCP tools: `ynab_sync`, `ynab_status`, `ynab_ask`, `ynab_upcoming`
- Read-only — no transaction creation in this phase
- Python handles all math; Ollama used only for NL narration

**Out of scope for Phase 3:**
- Creating or updating transactions
- Multi-budget support (uses `last-used` budget or a single configured ID)
- Scheduled auto-sync (manual sync only — `ynab_sync()`)
- YNAB→vault write-back
- Gmail, GCal (Phase 4)

---

## Architecture

Phase 3 extends the existing platform without modifying Phase 1/2 internals.

```
larvis/
└── agents/
    └── ynab/
        ├── __init__.py
        ├── tools.py        # 4 MCP tools registered in server.py
        ├── cache.py        # SQLite schema + read/write helpers
        └── client.py       # YNAB API client (thin wrapper over ynab-py)

.ynab/
└── cache.db               # SQLite — gitignored, bind-mounted from host
```

**Data flow:**
```
YNAB API
   │  (ynab-py, delta sync, Personal Access Token)
   ▼
client.py  ──►  cache.py (SQLite)
                    │
                    ▼
              tools.py  ──►  Python math/aggregation
                                    │
                                    ▼
                              Ollama (narration only — never touches numbers)
                                    │
                                    ▼
                              MCP response → Claude Code
```

---

## Components

### `client.py` — YNAB API client

Single public function: `sync_budget(budget_id: str) -> SyncResult`

- Reads `last_knowledge_of_server` from `sync_meta` table (0 on first run)
- Fetches via `ynab-py`: accounts, categories, months (last 3), transactions (last 90 days), scheduled transactions
- Returns counts for each resource synced
- Uses `ynab-py` (dynacylabs) — 100% API coverage, built-in rate limiting and caching

### `cache.py` — SQLite schema and helpers

Five tables. All monetary values stored as milliunits (integers), converted to dollars only at display time (`milliunits / 1000`).

```sql
accounts (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    balance INTEGER,           -- milliunits
    cleared_balance INTEGER,   -- milliunits
    on_budget BOOLEAN,
    deleted BOOLEAN
)

categories (
    id TEXT,
    month TEXT,                -- YYYY-MM-01
    group_name TEXT,
    name TEXT,
    budgeted INTEGER,          -- milliunits
    activity INTEGER,          -- milliunits
    balance INTEGER,           -- milliunits
    deleted BOOLEAN,
    PRIMARY KEY (id, month)
)

transactions (
    id TEXT PRIMARY KEY,
    date TEXT,                 -- YYYY-MM-DD
    amount INTEGER,            -- milliunits
    payee_name TEXT,
    category_name TEXT,
    memo TEXT,
    cleared TEXT,
    deleted BOOLEAN
)

scheduled (
    id TEXT PRIMARY KEY,
    frequency TEXT,
    next_date TEXT,            -- YYYY-MM-DD
    amount INTEGER,            -- milliunits
    payee_name TEXT,
    category_name TEXT,
    memo TEXT
)

sync_meta (
    budget_id TEXT PRIMARY KEY,
    last_knowledge_of_server INTEGER,
    synced_at TEXT             -- ISO-8601
)
```

Read helpers exposed by `cache.py`:
- `get_accounts() -> list[dict]`
- `get_categories(month: str) -> list[dict]`
- `get_transactions(since_date: str) -> list[dict]`
- `get_scheduled(within_days: int) -> list[dict]`
- `get_month_summary(month: str) -> dict`
- `is_synced() -> bool`

### `tools.py` — MCP tools

| Tool | Signature | Description |
|------|-----------|-------------|
| `ynab_sync` | `() -> str` | Refresh SQLite cache from YNAB API via delta sync |
| `ynab_status` | `() -> str` | Quick dashboard — TBB, age of money, over-budget categories, on-budget total |
| `ynab_ask` | `(query: str) -> str` | NL query — Python assembles relevant data, Ollama narrates |
| `ynab_upcoming` | `() -> str` | Scheduled transactions due within 14 days |

**`ynab_sync()`**
Calls `client.sync_budget(settings.ynab_budget_id)`, upserts all rows into cache, updates `sync_meta`.
Returns: `"Synced: 3 accounts, 42 categories, 187 transactions, 8 scheduled. Last sync: 2026-06-10 08:15."`

**`ynab_status()`**
Pure Python — no Ollama. Queries cache directly:
- Ready to assign (`to_be_budgeted`) and age of money — via `get_month_summary(current_month)`
- On-budget account total — via `get_accounts()`, sum `balance` where `on_budget=True`
- Over-budget categories (balance < 0), sorted by worst first — via `get_categories(current_month)`
Returns formatted text. Fast, accurate, no LLM risk.

**`ynab_ask(query: str)`**
1. Select relevant data from cache based on query (keyword matching: "grocery" → filter categories, "transactions" → recent txns, etc.)
2. Format as structured context block (pre-computed dollar amounts — Python does all math)
3. Send to Ollama with query for NL synthesis
4. If Ollama unavailable, return the raw structured data directly

**`ynab_upcoming()`**
Queries `scheduled` table for `next_date <= today + 14 days`, sorted by date.
Returns formatted list with payee, amount, date, frequency.

### `server.py` changes

Minimal: import and register the 4 ynab tools, identical pattern to lifeos tools registration.

---

## Configuration

New env vars added to `.env.example` and `docker-compose.yml`:

```
YNAB_API_KEY=...           # Personal Access Token from YNAB → Account Settings → Developer Settings
YNAB_BUDGET_ID=last-used   # or specific budget UUID
```

New `Settings` fields in `config.py`:
```python
ynab_api_key: str = ""
ynab_budget_id: str = "last-used"
```

New Docker bind mount in `docker-compose.yml`:
```yaml
- ./.ynab:/app/.ynab
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `YNAB_API_KEY` not set | `ynab_sync()` raises `RuntimeError("YNAB_API_KEY not configured")` |
| Cache empty (never synced) | All query tools return `"YNAB not synced — call ynab_sync() first."` |
| YNAB API 429 (rate limit) | `ynab-py` handles automatically; surface message if sync fails |
| YNAB API unreachable | Sync fails loudly with error; cached data still queryable |
| Ollama down | `ynab_ask()` returns raw structured data without narration |

All errors are loud and visible — no silent fallbacks.

---

## Testing

- `tests/test_ynab_cache.py` — unit tests for SQLite schema: insert/upsert/read for all five tables, delta cursor update, milliunit→dollar conversion
- `tests/test_ynab_tools.py` — unit tests with fixture data: `ynab_status()` math (TBB, over-budget detection), `ynab_upcoming()` date filtering (within 14 days, exclude past)
- No live YNAB API calls in tests — fixture data only
- Integration smoke test: `ynab_sync()` → `ynab_status()` with real API key

---

## Dependencies

- `ynab-py` (dynacylabs) added to `pyproject.toml`
- No other new dependencies — reuses existing SQLite, ollama, FastMCP stack

---

## Linear

Phase 3 tasks will be created under [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator).
