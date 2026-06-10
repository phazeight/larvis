# Phase 4 — Calendar Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only Google Calendar agent to Larvis with 4 MCP tools — `calendar_agenda`, `calendar_find_time`, `calendar_ask`, `calendar_status`.

**Architecture:** Live-fetch (no cache) from the Google Calendar API across configured calendars. Python does all logic (event normalization, free-slot computation); Ollama only narrates in `calendar_ask`. OAuth read-only scope, token authorized once on the Mac and bind-mounted into the container. Mirrors the YNAB agent's structure and division of labour.

**Tech Stack:** Python 3.12+, FastMCP, `google-api-python-client` / `google-auth` / `google-auth-oauthlib`, Ollama, click, uv, pytest.

**Spec:** `docs/superpowers/specs/2026-06-10-larvis-calendar-agent-design.md`

---

## File Structure

| File | Create/Modify | Responsibility |
|------|---------------|----------------|
| `larvis/agents/gcal/__init__.py` | Create | Package marker. |
| `larvis/agents/gcal/scheduling.py` | Create | Pure logic: merge busy blocks, compute open slots ≥ duration within working hours. No I/O. |
| `larvis/agents/gcal/auth.py` | Create | Load/refresh OAuth token, build the Calendar API service. |
| `larvis/agents/gcal/client.py` | Create | Google API wrapper: `list_events`, `free_busy`, normalization. |
| `larvis/agents/gcal/tools.py` | Create | The 4 tool functions + formatting helpers. |
| `larvis/config.py` | Modify | Add `gcal_*` settings fields. |
| `larvis/server.py` | Modify | Register the 4 MCP tools. |
| `larvis/cli.py` | Modify | Add the `gcal-auth` one-time OAuth command. |
| `.env.example` | Modify | Document `GCAL_*` env vars. |
| `.gitignore` | Modify | Ignore `.gcal/`. |
| `docker-compose.yml` | Modify | `GCAL_*` env + `./.gcal` bind mount. |
| `CLAUDE.md` | Modify | Add the 4 tools to the MCP tools table. |
| `tests/test_gcal_scheduling.py` | Create | Unit tests for `scheduling.open_slots`. |
| `tests/test_gcal_tools.py` | Create | Unit tests for the tools (mocked client/ollama). |
| `pyproject.toml` | Modify (via `uv add`) | Add the three Google libraries. |

---

## Task 1: Scaffold package, config, dependencies

**Files:**
- Create: `larvis/agents/gcal/__init__.py`
- Modify: `larvis/config.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `pyproject.toml` (via `uv add`)

- [ ] **Step 1: Create the package marker**

Create `larvis/agents/gcal/__init__.py` as an empty file:

```python
```

- [ ] **Step 2: Add the Google client libraries**

Run:
```bash
uv add google-api-python-client google-auth google-auth-oauthlib
```
Expected: `pyproject.toml` gains the three packages and they install into `.venv`.

- [ ] **Step 3: Add config fields**

In `larvis/config.py`, add these five fields immediately after the `ynab_budget_id` line (inside the `Settings` class):

```python
    gcal_credentials_path: str = ".gcal/credentials.json"
    gcal_token_path: str = ".gcal/token.json"
    gcal_calendar_ids: str = "primary"
    gcal_work_start: str = "09:00"
    gcal_work_end: str = "17:00"
```

- [ ] **Step 4: Document env vars in `.env.example`**

Append to `.env.example`:

```bash

# Google Calendar Agent (Phase 4) — read-only
# One-time setup: create a Google Cloud project, enable the Calendar API,
# create an OAuth client (type "Desktop app"), download the secret to
# .gcal/credentials.json, then run: uv run larvis gcal-auth
GCAL_CREDENTIALS_PATH=.gcal/credentials.json
GCAL_TOKEN_PATH=.gcal/token.json
GCAL_CALENDAR_IDS=primary
GCAL_WORK_START=09:00
GCAL_WORK_END=17:00
```

- [ ] **Step 5: Ignore the `.gcal/` secrets directory**

Append to `.gitignore`:

```
.gcal/
```

- [ ] **Step 6: Verify config loads**

Run:
```bash
uv run python -c "from larvis.config import settings; print(settings.gcal_calendar_ids, settings.gcal_work_start)"
```
Expected: `primary 09:00`

- [ ] **Step 7: Confirm `.gcal/` is ignored**

Run:
```bash
git check-ignore .gcal/credentials.json
```
Expected: prints `.gcal/credentials.json` (i.e. it is ignored).

- [ ] **Step 8: Commit**

```bash
git add larvis/agents/gcal/__init__.py larvis/config.py .env.example .gitignore pyproject.toml uv.lock
git commit -m "chore: scaffold gcal agent package + config + deps"
```

---

## Task 2: `scheduling.py` — open-slot computation (TDD)

**Files:**
- Create: `tests/test_gcal_scheduling.py`
- Create: `larvis/agents/gcal/scheduling.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gcal_scheduling.py`:

```python
from datetime import datetime, time, timezone

from larvis.agents.gcal.scheduling import open_slots

UTC = timezone.utc


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=UTC)


def test_no_busy_returns_full_working_window():
    slots = open_slots(
        busy_blocks=[],
        window_start=_dt(10, 0),
        window_end=_dt(10, 23, 59),
        work_start=time(9, 0),
        work_end=time(17, 0),
        duration_minutes=60,
    )
    assert slots == [(_dt(10, 9), _dt(10, 17))]


def test_meeting_splits_into_two_slots():
    busy = [(_dt(10, 12), _dt(10, 13))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == [(_dt(10, 9), _dt(10, 12)), (_dt(10, 13), _dt(10, 17))]


def test_all_day_event_blocks_the_day():
    busy = [(_dt(10, 0), _dt(11, 0))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == []


def test_overlapping_busy_blocks_merge():
    busy = [(_dt(10, 10), _dt(10, 12)), (_dt(10, 11), _dt(10, 13))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == [(_dt(10, 9), _dt(10, 10)), (_dt(10, 13), _dt(10, 17))]


def test_duration_larger_than_gaps_excluded():
    busy = [(_dt(10, 10), _dt(10, 16))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 120)
    assert slots == []


def test_spans_multiple_days():
    slots = open_slots([], _dt(10, 0), _dt(11, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == [(_dt(10, 9), _dt(10, 17)), (_dt(11, 9), _dt(11, 17))]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gcal_scheduling.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'larvis.agents.gcal.scheduling'`

- [ ] **Step 3: Implement `scheduling.py`**

Create `larvis/agents/gcal/scheduling.py`:

```python
from datetime import datetime, time, timedelta


def _merge(blocks: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: b[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def open_slots(
    busy_blocks: list[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
    work_start: time,
    work_end: time,
    duration_minutes: int,
) -> list[tuple[datetime, datetime]]:
    """Free slots >= duration within working hours, for each day in the window."""
    duration = timedelta(minutes=duration_minutes)
    tz = window_start.tzinfo
    merged = _merge(busy_blocks)
    slots: list[tuple[datetime, datetime]] = []

    day = window_start.date()
    last_day = window_end.date()
    while day <= last_day:
        day_ws = datetime.combine(day, work_start, tzinfo=tz)
        day_we = datetime.combine(day, work_end, tzinfo=tz)
        seg_start = max(day_ws, window_start)
        seg_end = min(day_we, window_end)
        if seg_start < seg_end:
            cursor = seg_start
            for b_start, b_end in merged:
                if b_end <= seg_start or b_start >= seg_end:
                    continue
                bs = max(b_start, seg_start)
                if bs - cursor >= duration:
                    slots.append((cursor, bs))
                cursor = max(cursor, min(b_end, seg_end))
            if seg_end - cursor >= duration:
                slots.append((cursor, seg_end))
        day += timedelta(days=1)
    return slots
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gcal_scheduling.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/gcal/scheduling.py tests/test_gcal_scheduling.py
git commit -m "feat: gcal open-slot scheduling logic (TDD)"
```

---

## Task 3: `auth.py` — OAuth token + service builder

**Files:**
- Create: `larvis/agents/gcal/auth.py`

No unit tests — this performs live OAuth/token I/O. It gets an import/smoke check here and is exercised end-to-end in Task 8.

- [ ] **Step 1: Implement `auth.py`**

Create `larvis/agents/gcal/auth.py`:

```python
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from larvis.config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_credentials() -> Credentials:
    token_path = settings.gcal_token_path
    if not os.path.exists(token_path):
        raise RuntimeError("Calendar not authorized — run `larvis gcal-auth`.")
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("Calendar token invalid — run `larvis gcal-auth`.")
    return creds


def get_service():
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)
```

- [ ] **Step 2: Import/smoke check**

Run:
```bash
uv run python -c "from larvis.agents.gcal import auth; print('ok', auth.SCOPES)"
```
Expected: `ok ['https://www.googleapis.com/auth/calendar.readonly']`

- [ ] **Step 3: Commit**

```bash
git add larvis/agents/gcal/auth.py
git commit -m "feat: gcal oauth credentials + service builder"
```

---

## Task 4: `client.py` — Google Calendar API wrapper

**Files:**
- Create: `larvis/agents/gcal/client.py`

No unit tests — live API. Import/smoke check here; exercised in Task 8.

- [ ] **Step 1: Implement `client.py`**

Create `larvis/agents/gcal/client.py`:

```python
from datetime import datetime

from larvis.agents.gcal import auth
from larvis.config import settings


def _calendar_ids() -> list[str]:
    return [c.strip() for c in settings.gcal_calendar_ids.split(",") if c.strip()]


def _parse_dt(raw: str) -> datetime:
    if "T" in raw:  # timed event, e.g. "2026-06-10T09:00:00-04:00"
        return datetime.fromisoformat(raw)
    # all-day event: date only ("2026-06-10") -> midnight in local tz
    local_tz = datetime.now().astimezone().tzinfo
    return datetime.fromisoformat(raw).replace(tzinfo=local_tz)


def _normalize(event: dict, cal_id: str) -> dict:
    all_day = "date" in event["start"]
    start_raw = event["start"].get("dateTime", event["start"].get("date"))
    end_raw = event["end"].get("dateTime", event["end"].get("date"))
    return {
        "summary": event.get("summary", "(no title)"),
        "start": _parse_dt(start_raw),
        "end": _parse_dt(end_raw),
        "all_day": all_day,
        "location": event.get("location"),
        "calendar": cal_id,
    }


def list_events(time_min: datetime, time_max: datetime) -> list[dict]:
    service = auth.get_service()
    events: list[dict] = []
    for cal_id in _calendar_ids():
        resp = (
            service.events()
            .list(
                calendarId=cal_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        for item in resp.get("items", []):
            events.append(_normalize(item, cal_id))
    events.sort(key=lambda e: e["start"])
    return events


def free_busy(time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
    service = auth.get_service()
    body = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "items": [{"id": c} for c in _calendar_ids()],
    }
    resp = service.freebusy().query(body=body).execute()
    blocks: list[tuple[datetime, datetime]] = []
    for cal in resp.get("calendars", {}).values():
        for b in cal.get("busy", []):
            blocks.append(
                (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            )
    return blocks
```

- [ ] **Step 2: Import/smoke check**

Run:
```bash
uv run python -c "from larvis.agents.gcal import client; print('ok', client._calendar_ids())"
```
Expected: `ok ['primary']`

- [ ] **Step 3: Commit**

```bash
git add larvis/agents/gcal/client.py
git commit -m "feat: gcal api client — list_events + free_busy"
```

---

## Task 5: `tools.py` — `calendar_agenda` + `calendar_status` (TDD)

**Files:**
- Create: `tests/test_gcal_tools.py`
- Create: `larvis/agents/gcal/tools.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gcal_tools.py`:

```python
from datetime import datetime, timezone

from larvis.agents.gcal import auth, client, tools

UTC = timezone.utc


def _event(day, hour, summary, all_day=False, location=None):
    return {
        "summary": summary,
        "start": datetime(2026, 6, day, hour, 0, tzinfo=UTC),
        "end": datetime(2026, 6, day, hour + 1, 0, tzinfo=UTC),
        "all_day": all_day,
        "location": location,
        "calendar": "primary",
    }


def test_agenda_lists_events(monkeypatch):
    monkeypatch.setattr(client, "list_events", lambda a, b: [_event(10, 9, "Standup")])
    out = tools.agenda("today")
    assert "Standup" in out
    assert "09:00" in out


def test_agenda_empty(monkeypatch):
    monkeypatch.setattr(client, "list_events", lambda a, b: [])
    assert "No events" in tools.agenda("today")


def test_status_lists_calendars(monkeypatch):
    monkeypatch.setattr(auth, "get_service", lambda: object())
    monkeypatch.setattr(client, "_calendar_ids", lambda: ["primary", "work@example.com"])
    out = tools.status()
    assert "primary" in out
    assert "work@example.com" in out


def test_status_reports_unauthorized(monkeypatch):
    def boom():
        raise RuntimeError("no token")

    monkeypatch.setattr(auth, "get_service", boom)
    out = tools.status()
    assert "gcal-auth" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gcal_tools.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'larvis.agents.gcal.tools'`

- [ ] **Step 3: Implement `tools.py` (agenda + status + helpers)**

Create `larvis/agents/gcal/tools.py`:

```python
from datetime import datetime, time, timedelta

import ollama

from larvis.agents.gcal import auth, client, scheduling
from larvis.config import settings


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def agenda(range: str = "today") -> str:
    now = _now()
    if range == "week":
        start, end = now, now + timedelta(days=7)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    try:
        events = client.list_events(start, end)
    except Exception as e:
        return f"Calendar error: {e}"

    label = "this week" if range == "week" else "today"
    if not events:
        return f"No events {label}."

    lines = [f"=== Agenda ({label}) ==="]
    current_day = None
    for e in events:
        if range == "week":
            day = e["start"].strftime("%a %b %d")
            if day != current_day:
                lines.append(f"\n{day}:")
                current_day = day
        when = "all day" if e["all_day"] else e["start"].strftime("%H:%M")
        loc = f" @ {e['location']}" if e.get("location") else ""
        lines.append(f"  {when}  {e['summary']}{loc}")
    return "\n".join(lines)


def status() -> str:
    try:
        auth.get_service()
    except Exception as e:
        return f"Calendar not authorized — run `larvis gcal-auth`. ({e})"
    cals = client._calendar_ids()
    return "Calendar authorized.\nConfigured calendars:\n" + "\n".join(
        f"  - {c}" for c in cals
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gcal_tools.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/gcal/tools.py tests/test_gcal_tools.py
git commit -m "feat: calendar_agenda + calendar_status tools (TDD)"
```

---

## Task 6: `tools.py` — `calendar_find_time` + `calendar_ask` (TDD)

**Files:**
- Modify: `tests/test_gcal_tools.py`
- Modify: `larvis/agents/gcal/tools.py`

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_gcal_tools.py`:

```python
def test_find_time_returns_slot(monkeypatch):
    busy = [(datetime(2026, 6, 10, 12, tzinfo=UTC), datetime(2026, 6, 10, 13, tzinfo=UTC))]
    monkeypatch.setattr(tools, "_now", lambda: datetime(2026, 6, 10, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(client, "free_busy", lambda a, b: busy)
    out = tools.find_time(60, "today")
    assert "Open slots" in out


def test_find_time_none_available(monkeypatch):
    busy = [(datetime(2026, 6, 10, 9, tzinfo=UTC), datetime(2026, 6, 10, 17, tzinfo=UTC))]
    monkeypatch.setattr(tools, "_now", lambda: datetime(2026, 6, 10, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(client, "free_busy", lambda a, b: busy)
    out = tools.find_time(60, "today")
    assert "No 60-minute openings" in out


def test_ask_degrades_when_ollama_down(monkeypatch):
    monkeypatch.setattr(client, "list_events", lambda a, b: [_event(11, 15, "Dentist")])

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(tools.ollama, "Client", Boom)
    out = tools.ask("when is my dentist appointment?")
    assert "Dentist" in out
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_gcal_tools.py -k "find_time or ask" -q`
Expected: FAIL — `AttributeError: module 'larvis.agents.gcal.tools' has no attribute 'find_time'` (and `ask`)

- [ ] **Step 3: Implement `find_time`, `ask`, `_build_context`**

Append to `larvis/agents/gcal/tools.py`:

```python
def find_time(duration_minutes: int, within: str = "week") -> str:
    now = _now()
    if within == "week":
        end = now + timedelta(days=7)
    else:
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    try:
        busy = client.free_busy(now, end)
    except Exception as e:
        return f"Calendar error: {e}"

    slots = scheduling.open_slots(
        busy,
        now,
        end,
        _parse_hhmm(settings.gcal_work_start),
        _parse_hhmm(settings.gcal_work_end),
        duration_minutes,
    )
    label = "this week" if within == "week" else "today"
    if not slots:
        return f"No {duration_minutes}-minute openings in working hours {label}."

    lines = [f"=== Open slots (>= {duration_minutes} min, {label}) ==="]
    for s, e in slots:
        lines.append(f"  {s.strftime('%a %b %d  %H:%M')} - {e.strftime('%H:%M')}")
    return "\n".join(lines)


def _build_context(events: list[dict]) -> str:
    if not events:
        return "No events in the next 7 days."
    lines = []
    for e in events:
        if e["all_day"]:
            when = e["start"].strftime("%a %b %d") + " all day"
        else:
            when = (
                e["start"].strftime("%a %b %d %H:%M")
                + "-"
                + e["end"].strftime("%H:%M")
            )
        lines.append(f"  {when}  {e['summary']}")
    return "\n".join(lines)


def ask(query: str) -> str:
    now = _now()
    try:
        events = client.list_events(now, now + timedelta(days=7))
    except Exception as e:
        return f"Calendar error: {e}"

    context = _build_context(events)
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "You are a calendar assistant. Answer the question using ONLY the "
                "schedule below. Do not invent events. If the data does not contain "
                "the answer, say so.\n\n"
                f"Schedule (next 7 days):\n{context}\n\n"
                f"Question: {query}"
            ),
        )
        return resp.response
    except Exception:
        return context
```

- [ ] **Step 4: Run the tool tests to verify they pass**

Run: `uv run pytest tests/test_gcal_tools.py -q`
Expected: `7 passed`

- [ ] **Step 5: Full-suite regression check**

Run: `uv run pytest -q`
Expected: all tests pass (41 prior + 6 scheduling + 7 tools = 54 passed), 1 pre-existing ChromaDB deprecation warning.

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/gcal/tools.py tests/test_gcal_tools.py
git commit -m "feat: calendar_find_time + calendar_ask tools (TDD)"
```

---

## Task 7: Wire into server, CLI, docker, docs

**Files:**
- Modify: `larvis/server.py`
- Modify: `larvis/cli.py`
- Modify: `docker-compose.yml`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Import the gcal tools in `server.py`**

In `larvis/server.py`, add this import after the `ynab_tools` import (line 5):

```python
from larvis.agents.gcal import tools as gcal_tools
```

- [ ] **Step 2: Register the 4 tools in `server.py`**

In `larvis/server.py`, add after the `ynab_upcoming` tool (after line 76, before `def main()`):

```python
@mcp.tool()
def calendar_agenda(range: str = "today") -> str:
    """Your calendar agenda. range="today" (full day) or "week" (next 7 days)."""
    return gcal_tools.agenda(range)


@mcp.tool()
def calendar_find_time(duration_minutes: int, within: str = "week") -> str:
    """Find open slots >= duration_minutes within working hours. within="today" or "week"."""
    return gcal_tools.find_time(duration_minutes, within)


@mcp.tool()
def calendar_ask(query: str) -> str:
    """Ask a natural-language question about your calendar (next 7 days)."""
    return gcal_tools.ask(query)


@mcp.tool()
def calendar_status() -> str:
    """Calendar auth/health check — confirms authorization and lists configured calendars."""
    return gcal_tools.status()
```

- [ ] **Step 3: Add the `gcal-auth` command to `cli.py`**

In `larvis/cli.py`, add these imports after the existing imports (after line 7):

```python
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from larvis.config import settings

GCAL_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
```

Then add this command at the end of the file:

```python
@cli.command(name="gcal-auth")
def gcal_auth() -> None:
    """One-time Google Calendar OAuth — opens a browser for read-only consent."""
    os.makedirs(os.path.dirname(settings.gcal_token_path) or ".", exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(
        settings.gcal_credentials_path, GCAL_SCOPES
    )
    creds = flow.run_local_server(port=0)
    with open(settings.gcal_token_path, "w") as f:
        f.write(creds.to_json())
    click.echo(f"Authorized. Token saved to {settings.gcal_token_path}")
```

- [ ] **Step 4: Add `GCAL_*` env + bind mount to `docker-compose.yml`**

In `docker-compose.yml`, add to the `larvis` service `environment:` block (after the `YNAB_BUDGET_ID` line):

```yaml
      GCAL_CALENDAR_IDS: ${GCAL_CALENDAR_IDS:-primary}
      GCAL_WORK_START: ${GCAL_WORK_START:-09:00}
      GCAL_WORK_END: ${GCAL_WORK_END:-17:00}
```

And add to the `larvis` service `volumes:` block (after the `./.ynab:/app/.ynab` line):

```yaml
      - ./.gcal:/app/.gcal
```

(The credential/token paths use the relative `.gcal/...` defaults, which resolve to this bind mount inside the container.)

- [ ] **Step 5: Update the MCP tools table in `CLAUDE.md`**

In `CLAUDE.md`, change the tools section header from `## MCP tools (Phase 1 + 2 + 3)` to `## MCP tools (Phase 1 + 2 + 3 + 4)` and add these rows to the bottom of the table:

```markdown
| `calendar_agenda` | `(range?: str) -> str` | Calendar agenda — "today" or "week" |
| `calendar_find_time` | `(duration_minutes: int, within?: str) -> str` | Open slots in working hours |
| `calendar_ask` | `(query: str) -> str` | NL question about your calendar (next 7 days) |
| `calendar_status` | `() -> str` | Calendar auth check + configured calendars |
```

- [ ] **Step 6: Verify the server imports and registers all 4 tools**

Run:
```bash
uv run python -c "
import asyncio
from larvis import server
tools = asyncio.run(server.mcp.list_tools())
cal = sorted(t.name for t in tools if t.name.startswith('calendar_'))
print(cal)
assert cal == ['calendar_agenda','calendar_ask','calendar_find_time','calendar_status']
print('OK: 4 calendar tools registered')
"
```
Expected: prints the 4 tool names then `OK: 4 calendar tools registered`

- [ ] **Step 7: Verify the CLI command is registered**

Run: `uv run larvis gcal-auth --help`
Expected: help text for the `gcal-auth` command ("One-time Google Calendar OAuth …"). It does not perform auth with `--help`.

- [ ] **Step 8: Commit**

```bash
git add larvis/server.py larvis/cli.py docker-compose.yml CLAUDE.md
git commit -m "feat: register calendar MCP tools + gcal-auth CLI + docker config"
```

---

## Task 8: Live smoke test + Linear tracking

**Files:** No new files. Validates end-to-end against the real Google account.

- [ ] **Step 1: One-time Google Cloud setup (manual)**

1. Go to https://console.cloud.google.com → create a project (or reuse one).
2. APIs & Services → Library → enable **Google Calendar API**.
3. APIs & Services → Credentials → Create Credentials → **OAuth client ID** → type **Desktop app**.
4. If prompted, configure the OAuth consent screen as **External**, add yourself as a **Test user** (no app verification needed for personal use).
5. Download the client secret JSON to `.gcal/credentials.json` in the repo root.

- [ ] **Step 2: Configure calendars in `.env`**

Set `GCAL_CALENDAR_IDS` in `.env` to your primary plus any others (comma-separated). Find calendar IDs in Google Calendar → each calendar's Settings → "Integrate calendar" → Calendar ID. `primary` always means your main calendar. Example:
```bash
# in .env
GCAL_CALENDAR_IDS=primary,family123@group.calendar.google.com
```

- [ ] **Step 3: Authorize (one-time, on the Mac)**

Run:
```bash
uv run larvis gcal-auth
```
Expected: a browser opens for read-only consent; after approving, `.gcal/token.json` is written and the CLI prints `Authorized. Token saved to .gcal/token.json`.

- [ ] **Step 4: Rebuild and restart the container**

```bash
docker compose build larvis
docker compose up -d larvis
sleep 12
docker compose logs larvis --tail 5
```
Expected: `Application startup complete.`

- [ ] **Step 5: Smoke test — `calendar_status`**

From Claude Code (MCP connected) call `calendar_status()`.
Expected: `Calendar authorized.` followed by your configured calendar list.

- [ ] **Step 6: Smoke test — `calendar_agenda`**

Call `calendar_agenda("week")`.
Expected: a chronological, day-grouped list of your next 7 days of events (or `No events this week.`).

- [ ] **Step 7: Smoke test — `calendar_find_time`**

Call `calendar_find_time(60, "week")`.
Expected: a list of open ≥60-minute slots within `GCAL_WORK_START`–`GCAL_WORK_END` (or a "No 60-minute openings" message).

- [ ] **Step 8: Smoke test — `calendar_ask`**

Call `calendar_ask("what's my next meeting?")`.
Expected: an Ollama-narrated answer grounded in your real upcoming events.

- [ ] **Step 9: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass (54 passed), 1 pre-existing ChromaDB warning.

- [ ] **Step 10: Linear tracking under PHA-52**

Create sub-issues under PHA-52 for each Phase 4 task and mark them Done as completed (mirrors the Phase 3 PHA-74…81 approach).

- [ ] **Step 11: Final commit**

```bash
git add -A
git commit -m "chore: Phase 4 calendar agent complete — all smoke tests passing"
```

---

## Self-Review Notes

- **Spec coverage:** read-only (no write paths) ✓; primary + named calendars (`_calendar_ids` splits `GCAL_CALENDAR_IDS`) ✓; agenda (Task 5) ✓; targeted lookups + Q&A (`calendar_ask`, Task 6) ✓; free/busy scheduling (`calendar_find_time` + `scheduling.open_slots`, Tasks 2/6) ✓; live fetch / no cache ✓; OAuth read-only + bind mount (Tasks 3/7/8) ✓; LifeOS-aware scheduling explicitly deferred ✓; error handling fail-fast (auth raises, tools surface `Calendar error:`, ask degrades) ✓; testing (scheduling + tools TDD, auth/client smoke) ✓.
- **Type consistency:** `scheduling.open_slots(busy_blocks, window_start, window_end, work_start, work_end, duration_minutes)` is called identically in `tools.find_time`. `client.list_events`/`client.free_busy` signatures match their call sites. Tool functions `agenda(range)`, `find_time(duration_minutes, within)`, `ask(query)`, `status()` match the `server.py` wrappers.
- **"week" semantics** consistent: next 7 days from now in both `agenda` and `find_time`.
