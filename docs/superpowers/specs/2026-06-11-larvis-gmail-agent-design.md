# Larvis Phase 5 — Gmail Agent Design Spec

**Date:** 2026-06-11
**Status:** Approved (design)
**Tracking:** [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)

## Summary

A **read-only** Gmail agent for Larvis. It gives a prioritized triage digest of unread
mail, supports targeted search, and answers natural-language questions about recent
email. It follows the established agent pattern (a module under `larvis/agents/`, tools
registered in `server.py`, config via env vars) and the YNAB/Calendar division of labour
— **Python does all the fetch/parse logic; the local LLM (Ollama) only prioritizes and
narrates**. Like the Calendar agent, it **fetches live per query** rather than caching.

The one structurally new element versus Calendar: Gmail authorizes **per account**, so the
agent manages **one OAuth token per inbox** and merges results across accounts. v1 covers
two personal accounts: `coltsnramzfan88@gmail.com` and `lucasryanthompson@gmail.com`.

## Goals (v1)

- Read-only access to Gmail — Larvis never mutates mail (no send/archive/label/delete).
- Cover **multiple accounts**, each with its own token, results merged and labeled by account.
- Triage scans **all unread categories** (Primary, Updates, Social, Promotions, Forums),
  with volume guarded by a fetch cap and Ollama prioritization that surfaces real people
  and collapses low-value mail into an aggregate.
- Four capabilities, exposed as MCP tools:
  - **Triage digest** — "what needs my attention?" across all accounts.
  - **Search** — find messages matching a query (Gmail operators supported).
  - **Natural-language Q&A / summarize** — "what did Megan say about the trip?",
    "summarize the thread with my accountant."
  - **Status** — per-account auth check + unread counts.

## Non-goals (v1) — explicitly deferred

- **No writes** — no send, reply, archive, label, or delete. (Future phase, with
  confirm-before-write guardrails.)
- **No caching / sync** — triage is a single time-bounded query per account; live fetch
  keeps data always-fresh.
- **No direct task creation.** Per the Larvis convention that *agents do not talk to each
  other directly*, the Gmail agent only **surfaces** detected action items as text. Offering
  to turn them into Linear/vault tasks is an **orchestrator-level** action (handled in the
  Claude Code chat layer), never inside this agent.
- **No work/Google-Workspace accounts in v1** (e.g. `lthompson@twenty.co`) — personal
  accounts only. Adding more accounts later is just another token + an entry in
  `GMAIL_ACCOUNTS`.

## Architecture

### Package layout — `larvis/agents/gmail/`

```
larvis/agents/gmail/
  __init__.py
  auth.py      # multi-account OAuth; one token per account; service builder
  client.py    # Gmail API wrapper: list / fetch / parse messages across accounts
  tools.py     # triage, search, ask, status
```

### MCP tools (registered in `server.py`)

| Tool | Signature | Description |
|------|-----------|-------------|
| `gmail_triage` | `(within?: str) -> str` | Prioritized digest of unread mail across all accounts (default last 48h; `within` overrides, e.g. "24h"/"week"). Grouped by account; per message: sender, subject, 1-line gist, detected action item. Ollama ranks by importance and aggregates low-value mail. Degrades to a raw ranked list if Ollama is down. |
| `gmail_search` | `(query: str) -> str` | Find messages matching a query across all accounts. Supports Gmail operators (`from:`, `subject:`, `newer_than:`, etc.). Returns a ranked list: account / sender / subject / snippet. |
| `gmail_ask` | `(query: str) -> str` | NL question / summarization over recent mail, Ollama-narrated. Degrades to raw matches if Ollama is down. |
| `gmail_status` | `() -> str` | Per-account auth state, configured accounts, and unread counts. |

**Action items stay read-only:** `gmail_triage`/`gmail_ask` emit action items as text only.
The "offer to create a task" is handled by the orchestrator (Claude Code), which can call
the existing `lifeos_sync_tasks`/Linear flow on user confirmation. Gmail never calls Linear.

### Configuration (`config.py` + `.env.example`)

```
GMAIL_ACCOUNTS=coltsnramzfan88@gmail.com,lucasryanthompson@gmail.com
GMAIL_CREDENTIALS_PATH=.gmail/credentials.json
GMAIL_TOKEN_DIR=.gmail
GMAIL_TRIAGE_QUERY=is:unread newer_than:2d   # all categories; override to scope
GMAIL_MAX_MESSAGES=40                          # per-account fetch cap (volume guard)
GMAIL_BODY_CHARS=2000                          # body truncation per message
```

`config.py` fields: `gmail_accounts`, `gmail_credentials_path`, `gmail_token_dir`,
`gmail_triage_query`, `gmail_max_messages`, `gmail_body_chars`. Docker: `GMAIL_*` env +
`./.gmail:/app/.gmail` bind mount (mirrors `.gcal`). `.gmail/` is gitignored.

### Authentication flow

- **Scope:** `https://www.googleapis.com/auth/gmail.readonly` (read-only).
- **Reuses the existing OAuth client** — same `lifeos-agents` GCP project and desktop client
  secret as Calendar, copied to `.gmail/credentials.json`. Setup adds: enable the **Gmail API**
  in that project, and consent to the Gmail scope once per account.
- **One token per account:** `.gmail/token-<account>.json`, where `<account>` is the full
  email address sanitized to a filesystem-safe slug (e.g. `coltsnramzfan88@gmail.com` →
  `token-coltsnramzfan88_gmail_com.json`) — avoids collisions between accounts that share a
  local part on different domains.
- **CLI:** `larvis gmail-auth <account-email>` — run once per account; opens a browser, the
  user signs in as that account and approves. Re-runnable per account to refresh a single token.
- `auth.get_credentials(account)` loads/refreshes that account's token (refresh if a refresh
  token exists; otherwise raise "run `larvis gmail-auth <account>`"). `auth.get_service(account)`
  builds the Gmail v1 client.

### Data flow (per query)

**Triage:**
1. For each account in `GMAIL_ACCOUNTS`: `client.list_messages(account, query=GMAIL_TRIAGE_QUERY,
   max_results=GMAIL_MAX_MESSAGES)` → message IDs (no category filter — all buckets).
2. Batch-fetch each message; `parse_message` extracts From / Subject / Date and a plain-text
   body (walks MIME parts, prefers `text/plain`, strips HTML from `text/html` when that's all
   there is, truncates to `GMAIL_BODY_CHARS`).
3. Assemble a normalized, account-labeled list. Build an Ollama prompt: rank by likely
   importance (real person > automated > promotional), extract action items, and **collapse
   low-value mail into an aggregate line** instead of listing each.
4. Return a digest grouped by account.

**Search / ask** follow the same fetch→parse path, using the user query instead of the unread
filter; `gmail_ask` adds an Ollama narration/summary step over the parsed results.

### Volume management

All-category unread across two accounts can be large. Guards: `GMAIL_MAX_MESSAGES` caps the
per-account fetch; `GMAIL_BODY_CHARS` caps per-message body sent to Ollama; the triage prompt
instructs the model to aggregate promotional/low-signal mail rather than enumerate it.

## Error handling

- Fail fast and visibly (CLAUDE.md). No silent fallbacks except the explicit Ollama degrade.
- **No/invalid token for an account** → surface
  `Gmail not authorized for <account> — run \`larvis gmail-auth <account>\``
  (after attempting a refresh when a refresh token exists).
- **Per-account isolation:** if one account errors, still return the other account's results
  with an inline note — a single broken token never blanks the whole digest.
- **Gmail API error** → `Gmail error: <detail>`.
- **Ollama down** in `gmail_triage`/`gmail_ask` → degrade to raw structured output (mirrors
  `ynab_ask`); the tool still returns useful data.

## Testing strategy (mirrors YNAB/Calendar)

- **Unit (TDD, no network):** `parse_message` / body extraction + HTML stripping, Gmail query
  construction, body truncation, digest assembly from fake message dicts, action-item
  formatting, per-account merge/label logic. Target ~10–12 tests.
- **Smoke (live):** `auth.py` and `client` get import/smoke checks; exercised end-to-end
  against both real accounts in the final live task (like Calendar's Task 8).

## Dependencies

No new Python dependencies — `google-api-python-client`, `google-auth`, and
`google-auth-oauthlib` were added for the Calendar agent and cover Gmail too.

## Wiring checklist (for the plan)

- `larvis/agents/gmail/{__init__,auth,client,tools}.py`
- `tests/test_gmail_*.py` (parsing, query/format logic, digest assembly)
- `larvis/config.py` — `gmail_*` fields
- `larvis/server.py` — 4 `@mcp.tool()` wrappers
- `larvis/cli.py` — `gmail-auth <account>` command
- `docker-compose.yml` — `GMAIL_*` env + `./.gmail` mount
- `.env.example`, `.gitignore` (`.gmail/`), `CLAUDE.md` (tools table + Phase 5 notes)
- Live smoke test + Linear sub-issues under PHA-52
