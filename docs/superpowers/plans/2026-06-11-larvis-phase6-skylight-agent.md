# Skylight Chores Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read + write Skylight chores agent for Larvis — list chores (grouped by member + Up for Grabs), add/assign chores, and mark them complete — via four MCP tools.

**Architecture:** Mirrors the YNAB agent's HTTP approach (`httpx`) and the gcal/ynab package layout. A package under `larvis/agents/skylight/` with `auth.py` (email/password → cached token, re-auth on 401), `client.py` (REST calls against `app.ourskylight.com/api`, normalizing the JSON:API responses), and `tools.py` (chores/add/complete/status). Python does all logic deterministically; no Ollama. Live-fetch, no cache. First write-capable agent — writes validated before POST and confirmed at the orchestrator level.

**Tech Stack:** Python 3.12, `httpx` (already used by YNAB), FastMCP, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-11-larvis-skylight-agent-design.md`

> **Reverse-engineered API caveat:** the exact sign-in endpoint, the `Authorization` header format, and the chore/category JSON shapes are **pinned in Task 2 (HAR capture)**. The HTTP code below is written from community references ([ha-skylight-tasks](https://github.com/riyadchowdhury/ha-skylight-tasks), [TheEagleByte/skylight-api](https://github.com/TheEagleByte/skylight-api)) as a JSON:API best-guess; Task 2's capture confirms or corrects the constants. All **pure logic** (normalization, validation, grouping, formatting) is TDD'd and does not depend on the live shapes.

---

## File structure

| File | Responsibility |
|------|----------------|
| `larvis/agents/skylight/__init__.py` | Package marker |
| `larvis/agents/skylight/auth.py` | Config check, sign-in, token cache, `Authorization` header (re-auth on 401) |
| `larvis/agents/skylight/client.py` | `httpx` REST calls + JSON:API normalization (`_normalize_chore`, `_normalize_member`) |
| `larvis/agents/skylight/tools.py` | `chores`, `add_chore`, `complete_chore`, `status` + helpers |
| `larvis/config.py` | Add `skylight_*` settings fields |
| `larvis/server.py` | Register 4 `@mcp.tool()` wrappers |
| `docker-compose.yml` | `SKYLIGHT_*` env + `./.skylight` bind mount |
| `docs/skylight-api-capture.md` | Task 2 output: captured endpoints/payloads/auth (gitignored) |
| `tests/test_skylight_auth.py` | Unit: configured check, session parse, token roundtrip, header |
| `tests/test_skylight_client.py` | Unit: chore + member normalization |
| `tests/test_skylight_tools.py` | Unit: window, when-parse, member resolve, sentinel, grouping, validation |

---

## Task 1: Scaffold package + config + env

**Files:**
- Create: `larvis/agents/skylight/__init__.py`
- Modify: `larvis/config.py`, `.env.example`, `.gitignore`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p larvis/agents/skylight
touch larvis/agents/skylight/__init__.py
```

- [ ] **Step 2: Add config fields**

In `larvis/config.py`, add to `Settings` after the `gmail_*` block (or after the last agent block):

```python
    skylight_email: str = ""
    skylight_password: str = ""
    skylight_frame_id: str = ""
    skylight_token_path: str = ".skylight/token.json"
    skylight_base_url: str = "https://app.ourskylight.com/api"
```

- [ ] **Step 3: Add `.env.example` block**

Append to `.env.example`:

```bash
# Skylight chores (Phase 6) — read + write. Unofficial reverse-engineered API.
SKYLIGHT_EMAIL=
SKYLIGHT_PASSWORD=
SKYLIGHT_FRAME_ID=
SKYLIGHT_TOKEN_PATH=.skylight/token.json
SKYLIGHT_BASE_URL=https://app.ourskylight.com/api
```

- [ ] **Step 4: Gitignore secrets + capture**

Add to `.gitignore`:

```
.skylight/
docs/skylight-api-capture.md
```

- [ ] **Step 5: Verify config loads**

Run: `uv run python -c "from larvis.config import settings; print(settings.skylight_base_url)"`
Expected: `https://app.ourskylight.com/api`

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/skylight/__init__.py larvis/config.py .env.example .gitignore
git commit -m "chore: scaffold skylight agent package + config"
```

---

## Task 2: Discovery — HAR capture (manual, pins the API)

**Files:** Create `docs/skylight-api-capture.md` (gitignored).

This is a **manual task done by the user** — no code. It captures the exact requests so the
client isn't guessing. Without it, the write paths (especially Up for Grabs) can't be trusted.

- [ ] **Step 1: Capture traffic**

In a desktop browser, log in to `https://app.ourskylight.com` with DevTools → Network open
(filter: Fetch/XHR). Perform each action and, for each, copy the request URL, method,
request headers (especially `Authorization`), and request/response JSON bodies:
1. **Sign in** (reload + log in) — capture the POST that returns the auth token.
2. **Open the chores/tasks tab** — capture the `GET …/frames/{id}/chores` (note query params).
3. **Open categories/members** — capture `GET …/frames/{id}/categories`.
4. **Create an assigned chore** — capture the POST body (note how the member/category is referenced).
5. **Create an Up for Grabs chore** — capture the POST body (note how "unassigned" is encoded).
6. **Mark a chore complete** — capture the PATCH/POST (note the path + status field).

- [ ] **Step 2: Record findings**

Write `docs/skylight-api-capture.md` with, for each call: method, full path, auth header
format, and example request/response JSON. Explicitly note:
- the `Authorization` header format (e.g. `Basic <user_id> <token>` vs base64 vs bearer),
- the assigned-chore `relationships`/attribute used for the member,
- the **Up for Grabs** delta vs an assigned chore (member relationship omitted? an
  `up_for_grabs: true` attribute? a null category?),
- the completion field/path.

- [ ] **Step 3: Reconcile the code constants**

In Tasks 3–4, where the code below differs from your capture, **use the captured values**
(endpoint paths, header format, attribute names, the Up-for-Grabs payload). The pure-logic
tests stay valid regardless; only the HTTP wiring + normalization keys may need adjusting.

*(No commit — `docs/skylight-api-capture.md` is gitignored. It may contain a live token; do not commit it.)*

---

## Task 3: `auth.py` — sign-in, token cache, header

**Files:**
- Create: `larvis/agents/skylight/auth.py`
- Test: `tests/test_skylight_auth.py`

Pure logic (`_configured`, `_parse_session`, token cache roundtrip, `_build_header`) is TDD'd.
The live `_sign_in` HTTP call is smoke-checked, exercised end-to-end in Task 8.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skylight_auth.py`:

```python
import json

from larvis.agents.skylight import auth


def test_configured_requires_all_three(monkeypatch):
    monkeypatch.setattr(auth.settings, "skylight_email", "a@b.com")
    monkeypatch.setattr(auth.settings, "skylight_password", "pw")
    monkeypatch.setattr(auth.settings, "skylight_frame_id", "")
    assert auth._configured() is False
    monkeypatch.setattr(auth.settings, "skylight_frame_id", "frame1")
    assert auth._configured() is True


def test_parse_session_extracts_user_id_and_token():
    raw = {"data": {"id": "999", "attributes": {"authentication_token": "tok123"}}}
    creds = auth._parse_session(raw)
    assert creds == {"user_id": "999", "token": "tok123"}


def test_build_header_uses_basic_user_token():
    header = auth._build_header({"user_id": "999", "token": "tok123"})
    assert header["Authorization"] == "Basic 999 tok123"


def test_token_cache_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(path))
    auth._save_creds({"user_id": "1", "token": "t"})
    assert auth._load_creds() == {"user_id": "1", "token": "t"}


def test_load_creds_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.settings, "skylight_token_path", str(tmp_path / "nope.json"))
    assert auth._load_creds() is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_skylight_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.agents.skylight.auth`

- [ ] **Step 3: Implement `auth.py`**

Create `larvis/agents/skylight/auth.py` (header format / session keys per Task 2 capture):

```python
import json
import os

import httpx

from larvis.config import settings


def _configured() -> bool:
    return bool(
        settings.skylight_email and settings.skylight_password and settings.skylight_frame_id
    )


def _parse_session(data: dict) -> dict:
    node = data.get("data", data)
    attrs = node.get("attributes", node)
    token = attrs.get("authentication_token") or attrs.get("token")
    user_id = str(node.get("id") or attrs.get("user_id") or "")
    return {"user_id": user_id, "token": token}


def _build_header(creds: dict) -> dict:
    # Per Task 2 capture. Community implementations use "Basic <user_id> <token>".
    return {
        "Authorization": f"Basic {creds['user_id']} {creds['token']}",
        "Content-Type": "application/json",
    }


def _save_creds(creds: dict) -> None:
    path = settings.skylight_token_path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(creds, f)


def _load_creds() -> dict | None:
    path = settings.skylight_token_path
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _sign_in() -> dict:
    if not _configured():
        raise RuntimeError(
            "Skylight not configured — set SKYLIGHT_EMAIL/PASSWORD/FRAME_ID in .env."
        )
    url = f"{settings.skylight_base_url.rstrip('/')}/sessions"
    resp = httpx.post(
        url,
        json={"email": settings.skylight_email, "password": settings.skylight_password},
        timeout=30,
    )
    resp.raise_for_status()
    creds = _parse_session(resp.json())
    _save_creds(creds)
    return creds


def auth_header(force_refresh: bool = False) -> dict:
    creds = None if force_refresh else _load_creds()
    if not creds:
        creds = _sign_in()
    return _build_header(creds)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_skylight_auth.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Import smoke check**

Run: `uv run python -c "from larvis.agents.skylight import auth; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/skylight/auth.py tests/test_skylight_auth.py
git commit -m "feat: skylight auth — sign-in, token cache, header (TDD)"
```

---

## Task 4: `client.py` — REST calls + normalization

**Files:**
- Create: `larvis/agents/skylight/client.py`
- Test: `tests/test_skylight_client.py`

Normalization (`_normalize_chore`, `_normalize_member`) is TDD'd. HTTP functions
(`get_categories`, `list_chores`, `create_chore`, `complete_chore`) use the Task 2 endpoints
and are smoke-checked, exercised in Task 8.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skylight_client.py`:

```python
from larvis.agents.skylight import client


def test_normalize_chore_assigned():
    raw = {
        "id": "c1",
        "attributes": {"summary": "Feed dog", "status": "complete", "start": "2026-06-11"},
        "relationships": {"category": {"data": {"id": "m1", "type": "category"}}},
    }
    out = client._normalize_chore(raw)
    assert out == {
        "id": "c1",
        "summary": "Feed dog",
        "completed": True,
        "category_id": "m1",
        "date": "2026-06-11",
    }


def test_normalize_chore_up_for_grabs_has_no_category():
    raw = {
        "id": "c2",
        "attributes": {"summary": "Empty dishwasher", "status": "incomplete", "start": "2026-06-11"},
        "relationships": {"category": {"data": None}},
    }
    out = client._normalize_chore(raw)
    assert out["category_id"] is None
    assert out["completed"] is False


def test_normalize_member_reads_label():
    raw = {"id": "m1", "attributes": {"label": "Callum"}}
    assert client._normalize_member(raw) == {"id": "m1", "name": "Callum"}


def test_normalize_member_falls_back_to_name():
    raw = {"id": "m2", "attributes": {"name": "Maeve"}}
    assert client._normalize_member(raw) == {"id": "m2", "name": "Maeve"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_skylight_client.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.agents.skylight.client`

- [ ] **Step 3: Implement `client.py`**

Create `larvis/agents/skylight/client.py` (endpoint paths / payloads per Task 2 capture):

```python
import httpx

from larvis.agents.skylight import auth
from larvis.config import settings


def _base() -> str:
    return settings.skylight_base_url.rstrip("/")


def _frame() -> str:
    return settings.skylight_frame_id


def _normalize_chore(raw: dict) -> dict:
    attrs = raw.get("attributes", {})
    cat = (raw.get("relationships", {}).get("category", {}) or {}).get("data")
    return {
        "id": raw.get("id"),
        "summary": attrs.get("summary", "(untitled)"),
        "completed": attrs.get("status") == "complete",
        "category_id": cat.get("id") if cat else None,
        "date": attrs.get("start"),
    }


def _normalize_member(raw: dict) -> dict:
    attrs = raw.get("attributes", {})
    return {"id": raw.get("id"), "name": attrs.get("label") or attrs.get("name")}


def _request(method: str, path: str, **kwargs) -> dict:
    url = f"{_base()}{path}"
    with httpx.Client(timeout=30) as c:
        r = c.request(method, url, headers=auth.auth_header(), **kwargs)
        if r.status_code == 401:
            r = c.request(method, url, headers=auth.auth_header(force_refresh=True), **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}


def get_categories() -> list[dict]:
    data = _request("GET", f"/frames/{_frame()}/categories")
    return [_normalize_member(x) for x in data.get("data", [])]


def list_chores(after: str, before: str) -> list[dict]:
    data = _request(
        "GET", f"/frames/{_frame()}/chores", params={"after": after, "before": before}
    )
    return [_normalize_chore(x) for x in data.get("data", [])]


def create_chore(summary: str, day: str, category_id: str | None) -> dict:
    attributes = {"summary": summary, "start": day, "status": "incomplete"}
    body: dict = {"data": {"type": "chore", "attributes": attributes}}
    if category_id is not None:
        body["data"]["relationships"] = {
            "category": {"data": {"type": "category", "id": category_id}}
        }
    # else: Up for Grabs — unassigned payload confirmed via Task 2 capture.
    data = _request("POST", f"/frames/{_frame()}/chores", json=body)
    return _normalize_chore(data.get("data", {}))


def complete_chore(chore_id: str) -> dict:
    body = {"data": {"type": "chore", "id": chore_id, "attributes": {"status": "complete"}}}
    return _request("PATCH", f"/frames/{_frame()}/chores/{chore_id}", json=body)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_skylight_client.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Import smoke check**

Run: `uv run python -c "from larvis.agents.skylight import client; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add larvis/agents/skylight/client.py tests/test_skylight_client.py
git commit -m "feat: skylight api client — chores/categories + normalization (TDD)"
```

---

## Task 5: `tools.py` — chores + status

**Files:**
- Create: `larvis/agents/skylight/tools.py`
- Test: `tests/test_skylight_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skylight_tools.py`:

```python
from datetime import date, timedelta

from larvis.agents.skylight import client, tools


def _chore(cid, summary, completed=False, category_id=None, day="2026-06-11"):
    return {
        "id": cid,
        "summary": summary,
        "completed": completed,
        "category_id": category_id,
        "date": day,
    }


def test_window_today():
    after, before, label = tools._window("today")
    assert after == before == date.today().isoformat()
    assert label == "today"


def test_window_week():
    after, before, label = tools._window("week")
    assert after == date.today().isoformat()
    assert before == (date.today() + timedelta(days=7)).isoformat()
    assert label == "this week"


def test_chores_groups_members_and_up_for_grabs(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    monkeypatch.setattr(
        client,
        "list_chores",
        lambda a, b: [
            _chore("c1", "Feed dog", completed=True, category_id="m1"),
            _chore("c2", "Empty dishwasher", category_id=None),
        ],
    )
    out = tools.chores("today")
    assert "UP FOR GRABS" in out
    assert "Empty dishwasher" in out and "c2" in out
    assert "Callum" in out
    assert "Feed dog" in out and "c1" in out
    assert "✓" in out  # completed marker


def test_chores_empty(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [])
    monkeypatch.setattr(client, "list_chores", lambda a, b: [])
    assert "No chores" in tools.chores("today")


def test_status_lists_members(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    monkeypatch.setattr(tools.settings, "skylight_frame_id", "frame1")
    out = tools.status()
    assert "frame1" in out and "Callum" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_skylight_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.agents.skylight.tools`

- [ ] **Step 3: Implement `tools.py` (window + chores + status)**

Create `larvis/agents/skylight/tools.py`:

```python
from datetime import date, timedelta

from larvis.agents.skylight import client
from larvis.config import settings


def _window(within: str) -> tuple[str, str, str]:
    today = date.today()
    if within == "week":
        return today.isoformat(), (today + timedelta(days=7)).isoformat(), "this week"
    return today.isoformat(), today.isoformat(), "today"


def _line(c: dict) -> str:
    mark = "✓" if c["completed"] else "☐"
    return f"  {mark} {c['summary']}  [{c['id']}]"


def chores(within: str = "today") -> str:
    try:
        members = client.get_categories()
        after, before, label = _window(within)
        items = client.list_chores(after, before)
    except Exception as e:
        return f"Skylight error: {e}"
    if not items:
        return f"No chores {label}."

    name_by_id = {m["id"]: m["name"] for m in members}
    up_for_grabs: list[dict] = []
    by_member: dict[str, list[dict]] = {}
    for c in items:
        if c["category_id"] is None:
            up_for_grabs.append(c)
        else:
            by_member.setdefault(name_by_id.get(c["category_id"], "Unknown"), []).append(c)

    lines = [f"=== Chores ({label}) ==="]
    if up_for_grabs:
        lines.append("\nUP FOR GRABS:")
        lines.extend(_line(c) for c in up_for_grabs)
    for name in sorted(by_member):
        lines.append(f"\n{name}:")
        lines.extend(_line(c) for c in by_member[name])
    return "\n".join(lines)


def status() -> str:
    try:
        members = client.get_categories()
    except Exception as e:
        return f"Skylight not authorized — {e}"
    lines = [f"Skylight authorized. Frame: {settings.skylight_frame_id}", "Members:"]
    lines.extend(f"  - {m['name']}" for m in members)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_skylight_tools.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/skylight/tools.py tests/test_skylight_tools.py
git commit -m "feat: skylight_chores + skylight_status tools (TDD)"
```

---

## Task 6: `tools.py` — add_chore + complete_chore (incl. Up for Grabs)

**Files:**
- Modify: `larvis/agents/skylight/tools.py`, `tests/test_skylight_tools.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_skylight_tools.py`:

```python
def test_normalize_when_keywords():
    assert tools._normalize_when("today") == date.today().isoformat()
    assert tools._normalize_when("tomorrow") == (date.today() + timedelta(days=1)).isoformat()
    assert tools._normalize_when("2026-07-04") == "2026-07-04"


def test_is_up_for_grabs():
    assert tools._is_up_for_grabs("up-for-grabs") is True
    assert tools._is_up_for_grabs("Anyone") is True
    assert tools._is_up_for_grabs("Callum") is False


def test_add_chore_unknown_member_is_rejected_before_post(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])

    def boom(*a, **k):
        raise AssertionError("create_chore must not be called for an unknown member")

    monkeypatch.setattr(client, "create_chore", boom)
    out = tools.add_chore("Nobody", "Sweep")
    assert "Unknown member" in out and "Callum" in out


def test_add_chore_assigned(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    captured = {}

    def fake_create(summary, day, category_id):
        captured.update(summary=summary, day=day, category_id=category_id)
        return {"id": "new1"}

    monkeypatch.setattr(client, "create_chore", fake_create)
    out = tools.add_chore("callum", "Take out trash", "tomorrow")
    assert captured["category_id"] == "m1"
    assert captured["day"] == (date.today() + timedelta(days=1)).isoformat()
    assert "Callum" in out and "Take out trash" in out


def test_add_chore_up_for_grabs(monkeypatch):
    captured = {}

    def fake_create(summary, day, category_id):
        captured.update(category_id=category_id)
        return {"id": "new2"}

    monkeypatch.setattr(client, "create_chore", fake_create)
    out = tools.add_chore("up-for-grabs", "Wipe counters")
    assert captured["category_id"] is None
    assert "Up for Grabs" in out


def test_add_chore_bad_date(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    out = tools.add_chore("Callum", "Sweep", "someday")
    assert "date" in out.lower()


def test_complete_chore_requires_id():
    assert "chore_id" in tools.complete_chore("  ")


def test_complete_chore_confirms(monkeypatch):
    monkeypatch.setattr(client, "complete_chore", lambda cid: {"id": cid})
    out = tools.complete_chore("c9")
    assert "c9" in out and "complete" in out.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_skylight_tools.py -k "add_chore or complete_chore or normalize_when or up_for_grabs" -v`
Expected: FAIL with `AttributeError: module ... has no attribute '_normalize_when'`

- [ ] **Step 3: Implement the write tools + helpers**

Append to `larvis/agents/skylight/tools.py`:

```python
_UP_FOR_GRABS = {"up-for-grabs", "up for grabs", "anyone", "unassigned"}


def _is_up_for_grabs(member: str) -> bool:
    return member.strip().lower() in _UP_FOR_GRABS


def _normalize_when(when: str) -> str:
    value = (when or "today").strip().lower()
    today = date.today()
    if value == "today":
        return today.isoformat()
    if value == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    date.fromisoformat(value)  # validates ISO; raises ValueError otherwise
    return value


def _resolve_member(name: str, members: list[dict]) -> str:
    for m in members:
        if (m["name"] or "").strip().lower() == name.strip().lower():
            return m["id"]
    known = ", ".join(m["name"] for m in members) or "(none)"
    raise ValueError(f'Unknown member \'{name}\'. Known: {known} (or "up-for-grabs").')


def add_chore(member: str, summary: str, when: str = "today") -> str:
    try:
        day = _normalize_when(when)
    except ValueError:
        return f"Couldn't parse date '{when}' — use today, tomorrow, or YYYY-MM-DD."

    try:
        if _is_up_for_grabs(member):
            category_id = None
            who = "Up for Grabs"
        else:
            members = client.get_categories()
            try:
                category_id = _resolve_member(member, members)
            except ValueError as e:
                return str(e)
            who = member
        client.create_chore(summary, day, category_id)
    except Exception as e:
        return f"Skylight error: {e}"
    return f'✓ Added "{summary}" to {who} ({day}).'


def complete_chore(chore_id: str) -> str:
    if not chore_id.strip():
        return "Provide a chore_id (see skylight_chores)."
    try:
        client.complete_chore(chore_id.strip())
    except Exception as e:
        return f"Skylight error: {e}"
    return f"✓ Marked chore {chore_id.strip()} complete."
```

- [ ] **Step 4: Run the full tools test file**

Run: `uv run pytest tests/test_skylight_tools.py -v`
Expected: 13 PASSED (5 from Task 5 + 8 here)

- [ ] **Step 5: Commit**

```bash
git add larvis/agents/skylight/tools.py tests/test_skylight_tools.py
git commit -m "feat: skylight_add_chore + skylight_complete_chore incl up-for-grabs (TDD)"
```

---

## Task 7: Register MCP tools + docker config + CLAUDE.md

**Files:**
- Modify: `larvis/server.py`, `docker-compose.yml`, `CLAUDE.md`

- [ ] **Step 1: Import the tools module in `server.py`**

In `larvis/server.py`, add alongside the other agent imports:

```python
from larvis.agents.skylight import tools as skylight_tools
```

- [ ] **Step 2: Register the 4 tool wrappers**

In `larvis/server.py`, after the gmail tools, add:

```python
@mcp.tool()
def skylight_chores(within: str = "today") -> str:
    """List Skylight chores grouped by family member (+ Up for Grabs). within="today" or "week"."""
    return skylight_tools.chores(within)


@mcp.tool()
def skylight_add_chore(member: str, summary: str, when: str = "today") -> str:
    """Add/assign a chore. member = a family member name or "up-for-grabs". when=today/tomorrow/YYYY-MM-DD."""
    return skylight_tools.add_chore(member, summary, when)


@mcp.tool()
def skylight_complete_chore(chore_id: str) -> str:
    """Mark a Skylight chore complete by its id (from skylight_chores)."""
    return skylight_tools.complete_chore(chore_id)


@mcp.tool()
def skylight_status() -> str:
    """Skylight auth/health check — confirms sign-in and lists frame + members."""
    return skylight_tools.status()
```

- [ ] **Step 3: Verify the tools register**

Run:
```bash
uv run python -c "import asyncio; from larvis.server import mcp; print([t.name for t in asyncio.run(mcp.list_tools()) if t.name.startswith('skylight_')])"
```
Expected: `['skylight_chores', 'skylight_add_chore', 'skylight_complete_chore', 'skylight_status']` (order may vary).

- [ ] **Step 4: Wire docker-compose**

In `docker-compose.yml`, under the `larvis` service `environment:` block (next to `SKYLIGHT`-less agents), add:

```yaml
      SKYLIGHT_EMAIL: ${SKYLIGHT_EMAIL:-}
      SKYLIGHT_PASSWORD: ${SKYLIGHT_PASSWORD:-}
      SKYLIGHT_FRAME_ID: ${SKYLIGHT_FRAME_ID:-}
      SKYLIGHT_TOKEN_PATH: ${SKYLIGHT_TOKEN_PATH:-.skylight/token.json}
      SKYLIGHT_BASE_URL: ${SKYLIGHT_BASE_URL:-https://app.ourskylight.com/api}
```

And under the `larvis` service `volumes:` block, add:

```yaml
      - ./.skylight:/app/.skylight
```

- [ ] **Step 5: Update `CLAUDE.md`**

In the MCP tools table heading, bump the phase list to include `+ 6` and add four rows:

```
| `skylight_chores` | `(within?: str) -> str` | Chores grouped by member (+ Up for Grabs) |
| `skylight_add_chore` | `(member, summary, when?) -> str` | Add/assign a chore (or up-for-grabs) |
| `skylight_complete_chore` | `(chore_id: str) -> str` | Mark a chore complete |
| `skylight_status` | `() -> str` | Skylight auth check + frame + members |
```

Add a row to "Known issues / architecture notes":

```
| Skylight is an unofficial API | Reverse-engineered `app.ourskylight.com`; email/password in `.env`, token cached in `.skylight/`. Confirm payloads via HAR if calls break. |
```

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `uv run pytest -q`
Expected: all tests pass (93 prior + 22 new Skylight = 115), 1 pre-existing ChromaDB warning.

- [ ] **Step 7: Commit**

```bash
git add larvis/server.py docker-compose.yml CLAUDE.md
git commit -m "feat: register skylight MCP tools + docker config"
```

---

## Task 8: Live smoke test + Linear tracking

**Files:** No new files. Validates end-to-end against the real Skylight frame.

- [ ] **Step 1: Configure `.env`**

Set `SKYLIGHT_EMAIL`, `SKYLIGHT_PASSWORD`, and `SKYLIGHT_FRAME_ID` (from the Task 2 capture —
the `{frameId}` in the API paths) in `.env`.

- [ ] **Step 2: Rebuild and restart the container**

```bash
docker compose build larvis
docker compose up -d larvis
sleep 12
docker compose logs larvis --tail 5
```
Expected: `Application startup complete.`

- [ ] **Step 3: Smoke — `skylight_status` (read, auth)**

In the container:
```bash
docker compose exec larvis uv run python -c "from larvis.agents.skylight import tools; print(tools.status())"
```
Expected: `Skylight authorized.` + your frame id + family members. (If auth/header is wrong, correct `auth._build_header` / `_parse_session` / the sign-in endpoint per the Task 2 capture and rebuild.)

- [ ] **Step 4: Smoke — `skylight_chores` (read)**

```bash
docker compose exec larvis uv run python -c "from larvis.agents.skylight import tools; print(tools.chores('week'))"
```
Expected: chores grouped by member, with an UP FOR GRABS section if any exist.

- [ ] **Step 5: Smoke — `skylight_add_chore` assigned (write)**

```bash
docker compose exec larvis uv run python -c "from larvis.agents.skylight import tools; print(tools.add_chore('<member>', 'Larvis test chore', 'today'))"
```
Expected: `✓ Added "Larvis test chore" to <member> (…)`. Verify it appears on the Skylight device/app.

- [ ] **Step 6: Smoke — `skylight_add_chore` up-for-grabs (write)**

```bash
docker compose exec larvis uv run python -c "from larvis.agents.skylight import tools; print(tools.add_chore('up-for-grabs', 'Larvis UFG test', 'today'))"
```
Expected: `✓ Added "Larvis UFG test" to Up for Grabs (…)`. Verify it lands in the Up for Grabs column (confirms the Task 2 unassigned payload).

- [ ] **Step 7: Smoke — `skylight_complete_chore` (write)**

Re-run `skylight_chores('today')`, copy a test chore-id, then:
```bash
docker compose exec larvis uv run python -c "from larvis.agents.skylight import tools; print(tools.complete_chore('<chore_id>'))"
```
Expected: `✓ Marked chore <id> complete.` Verify the ✓ on the device, then delete the test chores from the app.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass (115), 1 pre-existing ChromaDB warning.

- [ ] **Step 9: Linear tracking under PHA-52**

Create sub-issues under PHA-52 for each Phase 6 task and mark them Done as completed (mirrors PHA-90…96).

- [ ] **Step 10: Open the PR**

```bash
git push -u origin phase6-skylight-agent
gh pr create --base main --head phase6-skylight-agent --title "Phase 6: Skylight chores agent" --body "<summary>"
```
(Do not merge — the user merges.)

---

## Self-Review Notes

- **Spec coverage:** read chores grouped by member + Up for Grabs (`tools.chores`) ✓; add/assign incl. up-for-grabs sentinels (`add_chore` + `_is_up_for_grabs`) ✓; complete by id (`complete_chore`) ✓; status/auth/members (`status`) ✓; email/password→cached token + re-auth on 401 (`auth`) ✓; httpx, no new deps ✓; live-fetch no cache ✓; no Ollama ✓; write safety — validate-before-POST (member/date checked before `create_chore`; id checked before `complete_chore`), echo confirmation, no delete/bulk/recurring ✓; error handling (configured check, 401 retry, unknown member, `Skylight error:`) ✓; HAR discovery task for the Up-for-Grabs payload + auth/endpoint confirmation (Task 2, reconciled in Tasks 3–4 and Task 8) ✓; testing (pure logic TDD + live smoke) ✓.
- **Type consistency:** the normalized chore dict (`id`, `summary`, `completed`, `category_id`, `date`) is produced by `client._normalize_chore` and consumed identically in `tools._line`/`chores` and every tools test. Member dict (`id`, `name`) from `_normalize_member` is consumed in `chores`, `status`, `_resolve_member`. `client.create_chore(summary, day, category_id)` and `client.complete_chore(chore_id)` signatures match their `tools` call sites and the test monkeypatches. `auth.auth_header(force_refresh=False)` matches `client._request`.
- **Reverse-engineered unknowns are contained:** all are isolated to `auth._build_header`/`_parse_session`/`_sign_in` endpoint and `client._normalize_*`/endpoint paths/`create_chore` body, each explicitly flagged to reconcile against the Task 2 capture. Pure-logic tests do not depend on them.
- **Test count:** Task 3 (+5), Task 4 (+4), Task 5 (+5), Task 6 (+8) = 22 new → 115 total.
```
