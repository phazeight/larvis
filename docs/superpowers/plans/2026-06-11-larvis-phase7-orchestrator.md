# Orchestrator Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A general intent router ("Larvis front door") that routes one NL request across the six agents, synthesizes a single answer, and handles writes via a safe propose→confirm protocol.

**Architecture:** A new `larvis/orchestrator/` package. Python does deterministic routing (`router.py`); the 8B only narrates read results (`synthesize.py`) and extracts write params (`adapters.extract_params`). Reads reuse each agent's existing NL/read function; writes use a small known set executed through a single-use token store (`pending.py`). Two MCP tools: `larvis_orchestrate(query)` + `larvis_confirm(token)`.

**Tech Stack:** Python 3.12, `ollama`, FastMCP, pytest. No new dependencies. Depends on all six agents (incl. Phase 6 Skylight) — this branch is stacked on `phase6-skylight-agent`.

**Spec:** `docs/superpowers/specs/2026-06-11-larvis-orchestrator-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `larvis/orchestrator/__init__.py` | Package marker |
| `larvis/orchestrator/router.py` | `route`, `is_write_intent`, `detect_action` — pure rules |
| `larvis/orchestrator/synthesize.py` | 8B narration of read blocks; degrade to concat |
| `larvis/orchestrator/pending.py` | propose → token store → execute (single-use) |
| `larvis/orchestrator/adapters.py` | read-adapter dispatch + `WRITE_TOOLS` + `extract_params` |
| `larvis/orchestrator/tools.py` | `orchestrate(query, session_id)` + `confirm(token)` |
| `larvis/server.py` | 2 `@mcp.tool()` wrappers |
| `larvis/cli.py` | optional `larvis orchestrate "<query>"` |
| `tests/test_orchestrator_*.py` | unit tests per module |

---

## Task 1: Scaffold the orchestrator package

**Files:**
- Create: `larvis/orchestrator/__init__.py`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p larvis/orchestrator
touch larvis/orchestrator/__init__.py
```

- [ ] **Step 2: Verify it imports**

Run: `uv run python -c "import larvis.orchestrator; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add larvis/orchestrator/__init__.py
git commit -m "chore: scaffold orchestrator package"
```

---

## Task 2: `router.py` — deterministic routing

**Files:**
- Create: `larvis/orchestrator/router.py`
- Test: `tests/test_orchestrator_router.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_router.py`:

```python
from larvis.orchestrator import router


def test_route_single_agent():
    assert router.route("what's on my calendar today?") == ["calendar"]


def test_route_multiple_agents():
    agents = router.route("do I have time and budget for a date night?")
    assert "calendar" in agents and "ynab" in agents


def test_route_falls_back_to_lifeos():
    assert router.route("hello there") == ["lifeos"]


def test_is_write_intent_true():
    assert router.is_write_intent("add a chore for Cal") is True
    assert router.is_write_intent("remind me to call mom") is True


def test_is_write_intent_false():
    assert router.is_write_intent("what chores are left today?") is False


def test_detect_action_chore():
    assert router.detect_action("add trash chore to Cal")["tool"] == "skylight_add_chore"


def test_detect_action_commit():
    assert router.detect_action("remind me to book flights")["tool"] == "lifeos_commit"


def test_detect_action_unknown_returns_none():
    assert router.detect_action("create a spreadsheet") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_orchestrator_router.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.orchestrator.router`

- [ ] **Step 3: Implement `router.py`**

Create `larvis/orchestrator/router.py`:

```python
import re

AGENT_KEYWORDS = {
    "calendar": ["calendar", "schedule", "meeting", "agenda", "free", "busy",
                 "appointment", "when am i", "my week", "my day"],
    "ynab": ["budget", "spend", "afford", "money", "cost", "bill", "paycheck",
             "category", "dollars", "$"],
    "gmail": ["email", "inbox", "mail", "message", "unread", "reply"],
    "skylight": ["chore", "chores", "up for grabs", "kids"],
    "lifeos": ["task", "project", "todo", "commitment", "overdue", "remind", "remember"],
    "vault": ["note", "notes", "journal", "vault", "wrote", "document"],
}

WRITE_VERBS = ["add", "create", "schedule", "mark", "complete", "assign", "remind", "remember"]


def route(query: str) -> list[str]:
    q = query.lower()
    hits = [agent for agent, kws in AGENT_KEYWORDS.items() if any(k in q for k in kws)]
    return hits or ["lifeos"]


def is_write_intent(query: str) -> bool:
    q = query.lower()
    return any(re.search(rf"\b{re.escape(v)}\b", q) for v in WRITE_VERBS)


def detect_action(query: str) -> dict | None:
    q = query.lower()
    if "chore" in q:
        return {"tool": "skylight_add_chore", "fields": ["member", "summary", "when"]}
    if any(k in q for k in ["remind", "remember", "commit", "note that"]):
        return {"tool": "lifeos_commit", "fields": ["text"]}
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_router.py -v`
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/orchestrator/router.py tests/test_orchestrator_router.py
git commit -m "feat: orchestrator router — route, write-intent, detect-action (TDD)"
```

---

## Task 3: `synthesize.py` — 8B narration

**Files:**
- Create: `larvis/orchestrator/synthesize.py`
- Test: `tests/test_orchestrator_synthesize.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_synthesize.py`:

```python
from larvis.orchestrator import synthesize


class _FakeOllama:
    def __init__(self, text):
        self._text = text

    def __call__(self, *a, **k):
        return self

    def generate(self, *a, **k):
        return type("R", (), {"response": self._text})()


def test_synthesize_uses_ollama(monkeypatch):
    monkeypatch.setattr(synthesize.ollama, "Client", _FakeOllama("Friday works."))
    out = synthesize.synthesize("date night?", {"calendar": "free fri", "ynab": "$120"})
    assert out == "Friday works."


def test_synthesize_degrades_to_concat_when_ollama_down(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(synthesize.ollama, "Client", Boom)
    out = synthesize.synthesize("date night?", {"calendar": "free fri", "ynab": "$120"})
    assert "calendar" in out and "free fri" in out and "$120" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_orchestrator_synthesize.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `synthesize.py`**

Create `larvis/orchestrator/synthesize.py`:

```python
import ollama

from larvis.config import settings


def _concat(blocks: dict[str, str]) -> str:
    return "\n\n".join(f"[{agent}]\n{text}" for agent, text in blocks.items())


def synthesize(query: str, blocks: dict[str, str]) -> str:
    context = _concat(blocks)
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "You are Larvis, a personal assistant. Answer the user's request using "
                "ONLY the agent results below. Be concise and direct; do not invent facts. "
                "If the results don't answer it, say so.\n\n"
                f"Agent results:\n{context}\n\nRequest: {query}"
            ),
        )
        return resp.response.strip()
    except Exception:
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_synthesize.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/orchestrator/synthesize.py tests/test_orchestrator_synthesize.py
git commit -m "feat: orchestrator synthesize — 8B narration with concat fallback (TDD)"
```

---

## Task 4: `pending.py` — propose→confirm token store

**Files:**
- Create: `larvis/orchestrator/pending.py`
- Test: `tests/test_orchestrator_pending.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_pending.py`:

```python
from larvis.orchestrator import pending


def test_propose_returns_token_and_get_retrieves():
    token = pending.propose({"tool": "x", "params": {"a": 1}})
    assert pending.get(token) == {"tool": "x", "params": {"a": 1}}


def test_execute_calls_registry_and_clears(monkeypatch):
    calls = {}

    def fake(**kwargs):
        calls.update(kwargs)
        return "done"

    token = pending.propose({"tool": "do_thing", "params": {"member": "Cal"}})
    out = pending.execute(token, {"do_thing": fake})
    assert out == "done"
    assert calls == {"member": "Cal"}
    assert pending.get(token) is None  # single-use, cleared


def test_execute_unknown_token():
    assert "No pending action" in pending.execute("nope", {})


def test_execute_unknown_tool():
    token = pending.propose({"tool": "missing", "params": {}})
    assert "Unknown action tool" in pending.execute(token, {})
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_orchestrator_pending.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `pending.py`**

Create `larvis/orchestrator/pending.py`:

```python
import uuid
from typing import Callable

_PENDING: dict[str, dict] = {}


def propose(action: dict) -> str:
    token = uuid.uuid4().hex[:8]
    _PENDING[token] = action
    return token


def get(token: str) -> dict | None:
    return _PENDING.get(token)


def execute(token: str, registry: dict[str, Callable]) -> str:
    action = _PENDING.pop(token, None)
    if not action:
        return "No pending action for that token (it may have expired or already run)."
    fn = registry.get(action["tool"])
    if not fn:
        return f"Unknown action tool: {action['tool']}."
    return fn(**action["params"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_pending.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/orchestrator/pending.py tests/test_orchestrator_pending.py
git commit -m "feat: orchestrator pending — single-use action token store (TDD)"
```

---

## Task 5: `adapters.py` — read dispatch + write tools + param extraction

**Files:**
- Create: `larvis/orchestrator/adapters.py`
- Test: `tests/test_orchestrator_adapters.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_adapters.py`:

```python
import pytest

from larvis.orchestrator import adapters


def test_gather_dispatches_to_agent(monkeypatch):
    monkeypatch.setattr(adapters.gcal_tools, "ask", lambda q: "CAL ANSWER")
    blocks = adapters.gather(["calendar"], "free friday?", "sid")
    assert blocks == {"calendar": "CAL ANSWER"}


def test_gather_catches_agent_error(monkeypatch):
    def boom(q):
        raise RuntimeError("down")

    monkeypatch.setattr(adapters.ynab_tools, "ask", boom)
    blocks = adapters.gather(["ynab"], "budget?", "sid")
    assert "ynab error" in blocks["ynab"]


def test_write_tools_registry_has_known_actions():
    assert "skylight_add_chore" in adapters.WRITE_TOOLS
    assert "lifeos_commit" in adapters.WRITE_TOOLS


class _FakeOllama:
    def __init__(self, text):
        self._text = text

    def __call__(self, *a, **k):
        return self

    def generate(self, *a, **k):
        return type("R", (), {"response": self._text})()


def test_extract_params_parses_json(monkeypatch):
    monkeypatch.setattr(
        adapters.ollama,
        "Client",
        _FakeOllama('{"member": "Cal", "summary": "trash", "when": "tomorrow"}'),
    )
    action = {"tool": "skylight_add_chore", "fields": ["member", "summary", "when"]}
    params = adapters.extract_params(action, "add trash to cal tomorrow")
    assert params == {"member": "Cal", "summary": "trash", "when": "tomorrow"}


def test_extract_params_raises_on_garbage(monkeypatch):
    monkeypatch.setattr(adapters.ollama, "Client", _FakeOllama("i cannot help"))
    action = {"tool": "lifeos_commit", "fields": ["text"]}
    with pytest.raises(ValueError):
        adapters.extract_params(action, "remember milk")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_orchestrator_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `adapters.py`**

Create `larvis/orchestrator/adapters.py`:

```python
import json

import ollama

from larvis import rag
from larvis.agents.gcal import tools as gcal_tools
from larvis.agents.gmail import tools as gmail_tools
from larvis.agents.lifeos import tools as lifeos_tools
from larvis.agents.skylight import tools as skylight_tools
from larvis.agents.ynab import tools as ynab_tools
from larvis.config import settings


def _read_calendar(query, session_id):
    return gcal_tools.ask(query)


def _read_ynab(query, session_id):
    return ynab_tools.ask(query)


def _read_gmail(query, session_id):
    return gmail_tools.ask(query)


def _read_vault(query, session_id):
    return rag.ask(query)


def _read_lifeos(query, session_id):
    return lifeos_tools.ask(query, session_id)


def _read_skylight(query, session_id):
    return skylight_tools.chores("week")


READ_ADAPTERS = {
    "calendar": _read_calendar,
    "ynab": _read_ynab,
    "gmail": _read_gmail,
    "vault": _read_vault,
    "lifeos": _read_lifeos,
    "skylight": _read_skylight,
}

WRITE_TOOLS = {
    "skylight_add_chore": skylight_tools.add_chore,
    "lifeos_commit": lifeos_tools.commit,
}


def gather(agents: list[str], query: str, session_id: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for agent in agents:
        adapter = READ_ADAPTERS.get(agent)
        if not adapter:
            continue
        try:
            blocks[agent] = adapter(query, session_id)
        except Exception as e:
            blocks[agent] = f"{agent} error: {e}"
    return blocks


def extract_params(action: dict, query: str) -> dict:
    fields = ", ".join(action["fields"])
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                f"Extract a flat JSON object with EXACTLY these keys: {fields}. "
                "For a 'when' field use today, tomorrow, or YYYY-MM-DD. "
                "Output ONLY the JSON object, no prose.\n\n"
                f"Request: {query}"
            ),
        )
        text = resp.response
        text = text[text.find("{"): text.rfind("}") + 1]
        parsed = json.loads(text)
    except Exception as e:
        raise ValueError(f"could not extract {fields}") from e
    return {k: parsed.get(k) for k in action["fields"]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_adapters.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/orchestrator/adapters.py tests/test_orchestrator_adapters.py
git commit -m "feat: orchestrator adapters — read dispatch, write registry, param extraction (TDD)"
```

---

## Task 6: `tools.py` — orchestrate + confirm

**Files:**
- Create: `larvis/orchestrator/tools.py`
- Test: `tests/test_orchestrator_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_tools.py`:

```python
from larvis.orchestrator import adapters, pending, router, synthesize, tools


def test_orchestrate_read_path(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: False)
    monkeypatch.setattr(router, "route", lambda q: ["calendar"])
    monkeypatch.setattr(adapters, "gather", lambda agents, q, sid: {"calendar": "x"})
    monkeypatch.setattr(synthesize, "synthesize", lambda q, blocks: "ANSWER")
    assert tools.orchestrate("what's today?") == "ANSWER"


def test_orchestrate_write_proposal(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: True)
    monkeypatch.setattr(
        router, "detect_action",
        lambda q: {"tool": "skylight_add_chore", "fields": ["member", "summary", "when"]},
    )
    monkeypatch.setattr(
        adapters, "extract_params",
        lambda action, q: {"member": "Cal", "summary": "trash", "when": "today"},
    )
    out = tools.orchestrate("add trash to Cal")
    assert "Proposed" in out and "Cal" in out and "larvis_confirm" in out


def test_orchestrate_write_unknown_action(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: True)
    monkeypatch.setattr(router, "detect_action", lambda q: None)
    assert "don't have a tool" in tools.orchestrate("create a spreadsheet")


def test_orchestrate_write_extract_fails(monkeypatch):
    monkeypatch.setattr(router, "is_write_intent", lambda q: True)
    monkeypatch.setattr(
        router, "detect_action",
        lambda q: {"tool": "lifeos_commit", "fields": ["text"]},
    )

    def boom(action, q):
        raise ValueError("nope")

    monkeypatch.setattr(adapters, "extract_params", boom)
    assert "be explicit" in tools.orchestrate("remind me")


def test_confirm_executes(monkeypatch):
    calls = {}
    monkeypatch.setattr(adapters, "WRITE_TOOLS", {"t": lambda **k: calls.update(k) or "OK"})
    token = pending.propose({"tool": "t", "params": {"x": 1}})
    assert tools.confirm(token) == "OK"
    assert calls == {"x": 1}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_orchestrator_tools.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `tools.py`**

Create `larvis/orchestrator/tools.py`:

```python
from larvis.orchestrator import adapters, pending, router, synthesize


def _describe(tool: str, params: dict) -> str:
    if tool == "skylight_add_chore":
        return f'add chore "{params.get("summary")}" to {params.get("member")} ({params.get("when")})'
    if tool == "lifeos_commit":
        return f'commit: "{params.get("text")}"'
    return tool


def orchestrate(query: str, session_id: str = "orchestrator") -> str:
    if router.is_write_intent(query):
        action = router.detect_action(query)
        if not action:
            return "That looks like an action, but I don't have a tool for it yet."
        try:
            params = adapters.extract_params(action, query)
        except ValueError:
            fields = ", ".join(action["fields"])
            return (
                f"I think you want to {action['tool']}, but couldn't parse the details — "
                f"please state {fields} explicitly."
            )
        token = pending.propose({"tool": action["tool"], "params": params})
        return f'Proposed: {_describe(action["tool"], params)}.\nConfirm with larvis_confirm("{token}").'

    agents = router.route(query)
    blocks = adapters.gather(agents, query, session_id)
    return synthesize.synthesize(query, blocks)


def confirm(token: str) -> str:
    return pending.execute(token, adapters.WRITE_TOOLS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_orchestrator_tools.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/orchestrator/tools.py tests/test_orchestrator_tools.py
git commit -m "feat: orchestrator tools — orchestrate (read+propose) + confirm (TDD)"
```

---

## Task 7: Register MCP tools + CLI + CLAUDE.md

**Files:**
- Modify: `larvis/server.py`, `larvis/cli.py`, `CLAUDE.md`

- [ ] **Step 1: Import + register in `server.py`**

In `larvis/server.py`, add the import alongside the other agent imports:

```python
from larvis.orchestrator import tools as orchestrator_tools
```

After the skylight tools, add:

```python
@mcp.tool()
def larvis_orchestrate(query: str) -> str:
    """Larvis front door — routes your request across all agents and answers, or proposes a write to confirm."""
    return orchestrator_tools.orchestrate(query)


@mcp.tool()
def larvis_confirm(token: str) -> str:
    """Execute a write action that larvis_orchestrate proposed (pass the token it returned)."""
    return orchestrator_tools.confirm(token)
```

- [ ] **Step 2: Verify the tools register**

Run:
```bash
uv run python -c "import asyncio; from larvis.server import mcp; print([t.name for t in asyncio.run(mcp.list_tools()) if t.name.startswith('larvis_')])"
```
Expected: includes `larvis_orchestrate` and `larvis_confirm` (plus `larvis_ask`/`larvis_search`/`larvis_status`).

- [ ] **Step 3: Add the optional CLI command**

In `larvis/cli.py`, add after the existing commands:

```python
@cli.command()
@click.argument("query")
def orchestrate(query: str) -> None:
    """Ask Larvis anything — routes across all agents and answers."""
    from larvis.orchestrator import tools as orchestrator_tools

    click.echo(orchestrator_tools.orchestrate(query))
```

- [ ] **Step 4: Verify the CLI command exists**

Run: `uv run larvis orchestrate --help`
Expected: usage text showing the `QUERY` argument.

- [ ] **Step 5: Update `CLAUDE.md`**

In the MCP tools table, add two rows:

```
| `larvis_orchestrate` | `(query: str) -> str` | Front door — routes across all agents + synthesizes; proposes writes |
| `larvis_confirm` | `(token: str) -> str` | Execute a proposed write action by token |
```

Add a row to "Known issues / architecture notes":

```
| Orchestrator write safety | `larvis_orchestrate` never writes; it proposes a token, `larvis_confirm` executes. Tokens are in-process (MCP server). |
```

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `uv run pytest -q`
Expected: all pass (115 prior + 25 new orchestrator = 140), 1 pre-existing ChromaDB warning.

- [ ] **Step 7: Commit**

```bash
git add larvis/server.py larvis/cli.py CLAUDE.md
git commit -m "feat: register larvis_orchestrate + larvis_confirm tools + CLI"
```

---

## Task 8: Live smoke test + Linear tracking

**Files:** No new files. Validates end-to-end against the real agents.

- [ ] **Step 1: Rebuild and restart the container**

```bash
docker compose build larvis
docker compose up -d larvis
sleep 12
docker compose logs larvis --tail 5
```
Expected: `Application startup complete.`

- [ ] **Step 2: Smoke — single-agent read**

```bash
docker compose exec larvis uv run python -c "from larvis.orchestrator import tools; print(tools.orchestrate('what is on my calendar this week?'))"
```
Expected: a calendar-grounded answer (routed to the calendar agent only).

- [ ] **Step 3: Smoke — cross-agent read**

```bash
docker compose exec larvis uv run python -c "from larvis.orchestrator import tools; print(tools.orchestrate('do I have time and budget for a date night this week?'))"
```
Expected: an answer combining calendar availability + YNAB dining budget.

- [ ] **Step 4: Smoke — write propose→confirm**

```bash
docker compose exec larvis uv run python -c "from larvis.orchestrator import tools; print(tools.orchestrate('add a chore Larvis orch test to Cal today'))"
```
Expected: a `Proposed: add chore ... to Cal ...` line with a `larvis_confirm("<token>")` hint.
Then confirm with that token:
```bash
docker compose exec larvis uv run python -c "from larvis.orchestrator import tools; print(tools.confirm('<token>'))"
```
Expected: `✓ Added "Larvis orch test" to Cal ...`. Verify on the device, then delete the test chore.

> Note: propose and confirm must run in the **same process** (in-process token store). The two
> separate `docker compose exec` calls above are different processes — for the live check, run
> propose+confirm in one `python -c` (capture the token from `orchestrate`'s return and pass it
> to `confirm` in the same script). In the persistent MCP server (Claude Code), separate
> `larvis_orchestrate` then `larvis_confirm` calls share the process and work normally.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass (140), 1 pre-existing ChromaDB warning.

- [ ] **Step 6: Linear tracking under PHA-52**

Create sub-issues under PHA-52 for each Phase 7 task and mark them Done as completed.

- [ ] **Step 7: Open the PR**

```bash
git push -u origin phase7-orchestrator
gh pr create --base main --head phase7-orchestrator --title "Phase 7: Orchestrator layer" --body "<summary>"
```
(Merge Phase 6 PR #5 first so this PR's diff is clean against main. Do not merge — the user merges.)

---

## Self-Review Notes

- **Spec coverage:** general intent router front door (`tools.orchestrate`) ✓; hybrid brain — deterministic `router` + 8B only in `synthesize`/`extract_params` ✓; reads fan out via `adapters.gather` reusing each agent's existing fn (calendar/ynab/gmail/lifeos/vault `.ask`, skylight `.chores`) ✓; synthesize with concat fallback ✓; read+confirmed actions via `pending` propose→confirm + `larvis_confirm` ✓; write set limited to `skylight_add_chore` + `lifeos_commit` (`WRITE_TOOLS`/`detect_action`) ✓; never writes on first call ✓; proposal echoes extracted params (`_describe`) ✓; error handling — fallback to lifeos, synth concat fallback, extract-fail message, per-agent error blocks, unknown/expired token, unknown tool ✓; two MCP tools + optional CLI ✓; no new deps ✓; live smoke + Linear ✓.
- **Type consistency:** `route(query) -> list[str]`, `is_write_intent(query) -> bool`, `detect_action(query) -> {tool, fields} | None` match all call sites in `tools.orchestrate`. `adapters.gather(agents, query, session_id) -> dict` and `synthesize.synthesize(query, blocks) -> str` match. `pending.propose(action) -> token`, `pending.execute(token, registry) -> str`, and `adapters.WRITE_TOOLS` (a `{name: callable}` dict) match `confirm`. `extract_params(action, query) -> dict` raises `ValueError` (caught in `orchestrate`). The action dict shape `{"tool": str, "fields": list, "params": dict}` is consistent across `detect_action` → `extract_params` → `pending.propose` → `pending.execute`.
- **Test count:** Task 2 (8) + Task 3 (2) + Task 4 (4) + Task 5 (6) + Task 6 (5) = 25 new → 140 total.
```
