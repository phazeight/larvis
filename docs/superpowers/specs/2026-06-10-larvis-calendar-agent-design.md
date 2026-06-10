# Larvis Phase 4 — Calendar Agent Design Spec

**Date:** 2026-06-10
**Status:** Approved (design)
**Tracking:** [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)

## Summary

A **read-only** Google Calendar agent for Larvis. It answers questions about the
user's calendar (agenda, targeted lookups), finds open time slots for scheduling,
and supports natural-language Q&A. It follows the established agent pattern (a module
under `larvis/agents/`, tools registered in `server.py`, config via env vars) and the
YNAB agent's division of labour — **Python does all the logic; the local LLM (Ollama)
only narrates**. Unlike YNAB, it **fetches live per query** rather than caching.

## Goals (v1)

- Read-only access to Google Calendar — Larvis never mutates the calendar.
- Cover the user's **primary calendar plus a named set of others** (work, shared family, etc.), merged.
- Four capabilities, exposed as MCP tools:
  - **Agenda** — "what's on today / this week?"
  - **Targeted lookups** — "when's my next meeting?", "anything Friday afternoon?"
  - **Free/busy scheduling help** — "when am I free for 2 hours this week?"
  - **Natural-language Q&A** — freeform questions narrated by Ollama.

## Non-goals (v1) — explicitly deferred

- **No writes** — no create/move/cancel. (Future phase, with confirm-before-write guardrails.)
- **No caching / sync** — queries are small and time-bounded; live fetch keeps data always-fresh.
- **No LifeOS-aware scheduling.** Per the Larvis convention that *agents do not talk to each
  other directly* (they go through the orchestrator), `find_time` reasons over **calendar
  free/busy + configured working hours only**. Combining calendar availability with LifeOS
  tasks is a later orchestrator-level feature, not part of this agent.

## Architecture

### Package layout — `larvis/agents/gcal/`

> Named `gcal`, **not** `calendar`, to avoid shadowing Python's stdlib `calendar` module.

| File | Responsibility |
|------|----------------|
| `auth.py` | Build an authorized Google Calendar API service from a stored OAuth token; refresh automatically. Reads `GCAL_CREDENTIALS_PATH` and `GCAL_TOKEN_PATH`. Raises a clear, actionable error if unauthorized. |
| `client.py` | Thin Google Calendar API wrapper. `list_events(time_min, time_max)` — fetch events across all configured calendars, normalize to simple dicts (`start`, `end`, `summary`, `calendar`, `location`, `all_day`), merge + sort chronologically. `free_busy(time_min, time_max)` — call Google's `freebusy().query()` across configured calendars, return busy blocks. |
| `scheduling.py` | **Pure logic, no I/O.** `open_slots(busy_blocks, window_start, window_end, work_start, work_end, duration_minutes)` → list of free slots ≥ duration within working hours. Fully unit-testable. |
| `tools.py` | The four MCP tool functions (below). Python formats deterministic output; Ollama narrates only in `ask`. |

### MCP tools (registered in `server.py`)

| Tool | Signature | Behaviour |
|------|-----------|-----------|
| `calendar_agenda` | `(range: str = "today") -> str` | Structured chronological agenda for `"today"` or `"week"`. Deterministic formatting — analogous to `ynab_status`. |
| `calendar_find_time` | `(duration_minutes: int, within: str = "week") -> str` | Open slots ≥ `duration_minutes` within the window, using `client.free_busy` + `scheduling.open_slots`. |
| `calendar_ask` | `(query: str) -> str` | Ollama-narrated answer. Pulls the relevant event window into context and narrates; covers targeted lookups and freeform questions. Degrades to returning the raw structured context if Ollama errors — mirrors `ynab_ask`. |
| `calendar_status` | `() -> str` | Auth/health check: confirms the token is valid and lists the configured calendars. |

**Range semantics (unambiguous):** `"today"` = the current calendar day, `00:00`–`24:00` local time (includes earlier events for context). `"week"` = the next 7 days starting now. `calendar_find_time`'s `within` uses the same vocabulary.

### Configuration (`config.py` + `.env.example`)

| Env var | Default | Purpose |
|---------|---------|---------|
| `GCAL_CREDENTIALS_PATH` | `.gcal/credentials.json` | OAuth client secret (Desktop app) downloaded from Google Cloud. |
| `GCAL_TOKEN_PATH` | `.gcal/token.json` | Stored OAuth token (refresh token) written by the auth flow. |
| `GCAL_CALENDAR_IDS` | `primary` | Comma-separated calendar IDs — `primary` plus any others the user names. |
| `GCAL_WORK_START` | `09:00` | Start of the working-hours window used by `calendar_find_time`. |
| `GCAL_WORK_END` | `17:00` | End of the working-hours window used by `calendar_find_time`. |

### Authentication flow

1. **One-time setup (user, ~10 min):** create a free Google Cloud project, enable the
   Google Calendar API, create an OAuth client of type **Desktop app**, download the
   client secret to `.gcal/credentials.json`.
2. **One-time consent:** a new CLI command `larvis gcal-auth` runs on the Mac, opens a
   browser for consent on the **read-only** scope (`https://www.googleapis.com/auth/calendar.readonly`),
   and writes the resulting token to `.gcal/token.json`.
3. **Thereafter:** `auth.py` loads the token and auto-refreshes it via `google-auth`.
4. **Docker:** `.gcal/` is gitignored; `docker-compose.yml` bind-mounts `./.gcal:/app/.gcal`
   so the container reuses the host-authorized token (same pattern as the YNAB key in `.env`).
   `GCAL_*` env vars are added to the larvis service.

### Data flow (per query)

```
tool() → auth.get_service() → client.list_events / client.free_busy   (live Google API)
       → Python normalizes / sorts / computes open slots
       → agenda & find_time: deterministic string
       → ask: build context → Ollama narrates (fallback: raw context)
       → return str
```

## Error handling

Per Larvis conventions (fail fast and visibly, no silent fallbacks):

- **Missing/invalid credentials or token** → `"Calendar not authorized — run `larvis gcal-auth`."`
- **Google API errors** (network, 401, quota) → surfaced plainly in the tool's return string; no silent fallback to stale/empty data.
- **Ollama errors** (in `calendar_ask` only) → degrade to returning the raw structured context, mirroring `ynab_ask`.
- **Read-only by construction** — no mutation code paths exist, so there is no risk of altering the calendar.

## Testing strategy (mirrors YNAB)

- **TDD on pure logic:**
  - `scheduling.open_slots` — edge cases: no events (whole window free), all-day events (block the day), overlapping/adjacent busy blocks, a slot exactly at a window/working-hours boundary, duration larger than any gap (no slots).
  - `calendar_agenda` formatting — empty day, single event, multi-day week grouping, all-day vs timed events.
  - `calendar_ask` context building — keyword gating selects the right event window.
- **Live tier (no unit tests):** `auth.py` and `client.py` get an import/smoke check only; validated end-to-end by a final **live smoke test** against the real account (analogous to YNAB Task 8).

## Dependencies

Add to `pyproject.toml`: `google-api-python-client`, `google-auth`, `google-auth-oauthlib`.

## Wiring checklist (for the plan)

- Register the 4 tools in `larvis/server.py`.
- Add `GCAL_*` config fields to `larvis/config.py` and `.env.example`.
- Add the `.gcal` bind mount + `GCAL_*` env to `docker-compose.yml`.
- Add `.gcal/` to `.gitignore`.
- Add the `gcal-auth` subcommand to `larvis/cli.py`.
- Update `CLAUDE.md` (MCP tools table, known-issues if any).
- `.claude/settings.json` — existing `mcp__larvis__*` wildcard already covers new tools (no change expected).
