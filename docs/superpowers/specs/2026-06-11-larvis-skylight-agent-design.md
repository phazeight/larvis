# Larvis Phase 6 — Skylight Chores Agent Design Spec

**Date:** 2026-06-11
**Status:** Approved (design)
**Tracking:** [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator)

## Summary

A **read + write** chores agent for Larvis that talks to the family's Skylight Calendar
device. It lists chores (grouped by family member, including the **Up for Grabs**
column), creates and assigns chores, and marks them complete. It follows the established
agent pattern (a module under `larvis/agents/`, tools registered in `server.py`, config
via env vars) and the YNAB agent's HTTP approach (`httpx`). Like Calendar, it **fetches
live per query** — no cache. Chore data is small and structured, so **no Ollama** is used;
output is formatted deterministically in Python.

This is Larvis's **first write-capable agent**, so write safety is a first-class concern.

## API foundation (important context)

Skylight (the family calendar/chore device, `skylight.io`) has **no official public API**.
The `api.skylight.earth` / `support.skylight.global` "GraphQL API" found online belongs to a
**different, unrelated Skylight** (a maritime vessel-monitoring org) and does not apply.

This agent therefore uses the **community-reverse-engineered REST API** at
`https://app.ourskylight.com/api`, the same backend the Skylight app uses. References:
[ha-skylight-tasks](https://github.com/riyadchowdhury/ha-skylight-tasks),
[TheEagleByte/skylight-api OpenAPI spec](https://github.com/TheEagleByte/skylight-api),
[rjhalvorson/skylight-mcp](https://github.com/rjhalvorson/skylight-mcp).

**Caveat:** unofficial → could break if Skylight changes their app API. It accesses the
user's own family account/data, so access is legitimate, but it is more fragile than the
Google APIs. Exact endpoint paths, the auth header format, and the Up-for-Grabs create
payload are pinned during implementation from the community spec and a one-time HAR capture.

## Goals (v1)

- Read chores for today / this week, **grouped by family member** plus an **Up for Grabs**
  bucket, each with completion status (✓/☐) and its chore-id.
- **Create + assign** a chore to a member, or create an **Up for Grabs** (unassigned) chore.
- **Mark a chore complete** by id.
- Four capabilities, exposed as MCP tools:
  - **List chores** — `skylight_chores`
  - **Add/assign chore** — `skylight_add_chore` (incl. up-for-grabs)
  - **Complete chore** — `skylight_complete_chore`
  - **Status** — `skylight_status` (auth + frame + members)

## Non-goals (v1) — explicitly deferred

- **No recurring chores** — one-off chores only (the API supports `recurring`; deferred).
- **No delete, no bulk operations.**
- **No editing** existing chores beyond completion (no rename/reassign/reschedule).
- **No routines, rewards, lists, meals, calendar, or photos** — the broader Skylight
  surface is out of scope; this agent is chores-only.
- **No caching** — live fetch per query.

## Architecture

### Package layout — `larvis/agents/skylight/`

```
larvis/agents/skylight/
  __init__.py
  auth.py      # email/password -> token, cached to disk; re-auth on 401
  client.py    # httpx REST calls against app.ourskylight.com/api
  tools.py     # chores, add_chore, complete_chore, status
```

### MCP tools (registered in `server.py`)

| Tool | Signature | Description |
|------|-----------|-------------|
| `skylight_chores` | `(within?: str) -> str` | Chores for "today" (default) or "week", grouped by member with an Up for Grabs bucket first; each line shows ✓/☐, the summary, and the chore-id. |
| `skylight_add_chore` | `(member: str, summary: str, when?: str) -> str` | Create + assign a chore. `member` is a family member name, or a sentinel (`up-for-grabs` / `anyone` / `unassigned`) for an Up for Grabs chore. `when` = "today" (default) / "tomorrow" / `YYYY-MM-DD`. Returns an explicit confirmation echo. |
| `skylight_complete_chore` | `(chore_id: str) -> str` | Mark a specific chore complete. Returns a confirmation echo. |
| `skylight_status` | `() -> str` | Auth check + configured frame + list of members (categories). |

> **Members = Skylight "categories."** `add_chore` resolves member **name → category_id**
> (case-insensitive). The Up-for-Grabs sentinels map to the unassigned-chore payload.

### Configuration (`config.py` + `.env.example`)

```
SKYLIGHT_EMAIL=
SKYLIGHT_PASSWORD=
SKYLIGHT_FRAME_ID=
SKYLIGHT_TOKEN_PATH=.skylight/token.json
SKYLIGHT_BASE_URL=https://app.ourskylight.com/api
```

`config.py` fields: `skylight_email`, `skylight_password`, `skylight_frame_id`,
`skylight_token_path`, `skylight_base_url`. Docker: `SKYLIGHT_*` env + `./.skylight:/app/.skylight`
bind mount (mirrors `.ynab`/`.gcal`). `.skylight/` is gitignored. No new Python deps —
`httpx` is already used by the YNAB agent.

### Authentication flow

- `auth.get_token()` signs in with `SKYLIGHT_EMAIL` / `SKYLIGHT_PASSWORD`, obtains the
  token, and caches it to `SKYLIGHT_TOKEN_PATH`. The exact sign-in endpoint and
  `Authorization` header format are pinned from the community spec during implementation.
- On a `401` from any call, the client re-authenticates once (refreshing the cached token)
  and retries; a second failure surfaces as an error.

### Data flow (per query)

**Read** (`chores`, `status`):
1. `client.get_categories()` → members (id, name).
2. `client.list_chores(after, before)` → chores for the window.
3. Group chores by `category_id`; chores with no member land in the **Up for Grabs** bucket.
4. Format deterministically: Up for Grabs first, then one bucket per member, each chore as
   `✓/☐ <summary>  [<chore_id>]`.

**Write** (`add_chore`, `complete_chore`):
1. Validate up front (fail fast) — member exists or is a sentinel; date parses;
   chore_id non-empty.
2. `client.create_chore(summary, when, category_id|unassigned)` or
   `client.complete_chore(chore_id)`.
3. Return an explicit confirmation echo of exactly what was written.

### Write safety

- **Orchestrator confirms first.** Larvis (the Claude Code chat layer) must echo any write
  and get explicit user confirmation before calling `skylight_add_chore` /
  `skylight_complete_chore`. The agent never auto-writes. (Same principle as Gmail action
  items — write intent is surfaced and confirmed at the orchestrator level.)
- **Validate before POST.** No malformed writes reach the real device — member/date/id are
  checked before any network write.
- **Echo what happened.** Each write tool returns a clear confirmation
  (e.g. `✓ Added "Take out trash" to Callum (Tue Jun 16)`).
- **Narrow surface.** No delete, no bulk, no recurring in v1.

## Error handling

- Fail fast and visibly (CLAUDE.md). No silent fallbacks.
- Missing credentials → `Skylight not configured — set SKYLIGHT_EMAIL/PASSWORD/FRAME_ID in .env.`
- `401` → re-auth once; on repeat failure surface the error.
- Unknown member in `add_chore` → `Unknown member 'X'. Known: <list> (or "up-for-grabs").`
- Any API error → `Skylight error: <detail>`.

## Testing strategy (mirrors YNAB/Calendar)

- **Unit (TDD, no network):** date normalization (today/tomorrow/ISO → API date),
  member name→category_id resolution + Up-for-Grabs sentinel detection, chore
  grouping/formatting (Up for Grabs bucket + per-member buckets + ✓/☐ + chore-id),
  `add_chore` validation (unknown member rejected before any POST). ~10–12 tests against
  fake API dicts.
- **Smoke (live):** `auth.py` + `client` get import/smoke checks; exercised end-to-end in
  the final task — read first (`status`, `chores`), then careful writes (add an assigned
  chore, add an Up-for-Grabs chore, complete one, re-list to confirm).

## Dependencies

No new Python dependencies — `httpx` is already present (YNAB agent).

## Discovery dependency (gates the Up-for-Grabs create path)

The exact Up-for-Grabs create payload is not in the documented community spec (newer
feature). Before that write path can be implemented/tested, a **one-time HAR capture** is
required: in the Skylight web app (`app.ourskylight.com`) with DevTools → Network open,
create one Up-for-Grabs chore and export the POST request. This pins whether an unassigned
chore omits the member relationship or carries an explicit flag (e.g. `up_for_grabs: true`).
Assigned-chore create/list/complete do **not** depend on this and can be built first.

## Wiring checklist (for the plan)

- `larvis/agents/skylight/{__init__,auth,client,tools}.py`
- `tests/test_skylight_*.py` (date/member/grouping/validation logic)
- `larvis/config.py` — `skylight_*` fields
- `larvis/server.py` — 4 `@mcp.tool()` wrappers
- `docker-compose.yml` — `SKYLIGHT_*` env + `./.skylight` mount
- `.env.example`, `.gitignore` (`.skylight/`), `CLAUDE.md` (tools table + Phase 6 notes)
- HAR-capture discovery task (Up-for-Grabs payload) + live smoke test + Linear sub-issues under PHA-52
