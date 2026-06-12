# OpenAI-Compatible Endpoint (Deep Ask bridge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An OpenAI-compatible HTTP endpoint on the Larvis server so the Deep Ask Obsidian plugin can talk to Larvis (vault RAG or full orchestrator) from inside Obsidian.

**Architecture:** A pure-logic module `larvis/openai_api.py` (parse request, dispatch model, shape OpenAI responses) plus two thin `@mcp.custom_route` handlers in `larvis/server.py` that run the blocking brains via `run_in_threadpool`. Mounts on the existing FastMCP server (port 8765). Two models: `larvis-vault` → `rag.ask`, `larvis`/unknown → orchestrator.

**Tech Stack:** Python 3.12, FastMCP (`custom_route`), Starlette (`JSONResponse`/`StreamingResponse`/`run_in_threadpool`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-12-larvis-openai-endpoint-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `larvis/openai_api.py` | Pure logic: `last_user_message`, `answer` (model dispatch), `completion_response`, `stream_chunks`, `models_response` |
| `larvis/server.py` | Two `@mcp.custom_route` handlers (`/v1/chat/completions`, `/v1/models`) calling the module via `run_in_threadpool` |
| `tests/test_openai_api.py` | Unit tests for the pure logic |
| `CLAUDE.md` | Document the endpoint + Deep Ask setup |

---

## Task 1: `openai_api.py` — request parsing, dispatch, response shaping

**Files:**
- Create: `larvis/openai_api.py`
- Test: `tests/test_openai_api.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_openai_api.py`:

```python
import json

from larvis import openai_api


def test_last_user_message_picks_last_user_turn():
    msgs = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "second"},
    ]
    assert openai_api.last_user_message(msgs) == "second"


def test_last_user_message_empty_when_no_user():
    assert openai_api.last_user_message([]) == ""
    assert openai_api.last_user_message([{"role": "assistant", "content": "x"}]) == ""


def test_answer_routes_vault_model_to_rag(monkeypatch):
    monkeypatch.setattr(openai_api.rag, "ask", lambda q: f"RAG:{q}")
    monkeypatch.setattr(openai_api.orchestrator_tools, "orchestrate", lambda q: "ORCH")
    assert openai_api.answer("larvis-vault", "hi") == "RAG:hi"


def test_answer_routes_default_and_unknown_to_orchestrator(monkeypatch):
    monkeypatch.setattr(openai_api.rag, "ask", lambda q: "RAG")
    monkeypatch.setattr(openai_api.orchestrator_tools, "orchestrate", lambda q: f"ORCH:{q}")
    assert openai_api.answer("larvis", "hi") == "ORCH:hi"
    assert openai_api.answer("something-else", "hi") == "ORCH:hi"


def test_completion_response_shape():
    r = openai_api.completion_response("larvis-vault", "hello")
    assert r["object"] == "chat.completion"
    assert r["model"] == "larvis-vault"
    assert r["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert r["choices"][0]["finish_reason"] == "stop"
    assert r["id"].startswith("chatcmpl-")


def test_stream_chunks_format():
    chunks = list(openai_api.stream_chunks("larvis", "hi there"))
    assert chunks[-1] == "data: [DONE]\n\n"
    first = json.loads(chunks[0][len("data: "):])
    assert first["object"] == "chat.completion.chunk"
    assert first["choices"][0]["delta"]["content"] == "hi there"
    stop = json.loads(chunks[1][len("data: "):])
    assert stop["choices"][0]["finish_reason"] == "stop"


def test_models_response_lists_both():
    r = openai_api.models_response()
    ids = [m["id"] for m in r["data"]]
    assert r["object"] == "list"
    assert "larvis-vault" in ids and "larvis" in ids
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_openai_api.py -v`
Expected: FAIL with `ModuleNotFoundError: larvis.openai_api`

- [ ] **Step 3: Implement `openai_api.py`**

Create `larvis/openai_api.py`:

```python
import json
import time
import uuid
from collections.abc import Iterator

from larvis import rag
from larvis.orchestrator import tools as orchestrator_tools


def last_user_message(messages: list[dict]) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user":
            return message.get("content", "") or ""
    return ""


def answer(model: str, query: str) -> str:
    if (model or "").strip() == "larvis-vault":
        return rag.ask(query)
    return orchestrator_tools.orchestrate(query)


def completion_response(model: str, content: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def stream_chunks(model: str, content: str) -> Iterator[str]:
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    delta = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}
        ],
    }
    yield f"data: {json.dumps(delta)}\n\n"
    stop = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(stop)}\n\n"
    yield "data: [DONE]\n\n"


def models_response() -> dict:
    return {
        "object": "list",
        "data": [
            {"id": "larvis-vault", "object": "model", "owned_by": "larvis"},
            {"id": "larvis", "object": "model", "owned_by": "larvis"},
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_openai_api.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add larvis/openai_api.py tests/test_openai_api.py
git commit -m "feat: openai-compatible api helpers — dispatch + response shaping (TDD)"
```

---

## Task 2: Register the routes in `server.py`

**Files:**
- Modify: `larvis/server.py`

- [ ] **Step 1: Add imports**

In `larvis/server.py`, add near the top (after the existing imports):

```python
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from larvis import openai_api
```

- [ ] **Step 2: Add the two route handlers**

In `larvis/server.py`, add after the tool definitions and before `def main()`:

```python
@mcp.custom_route("/v1/models", methods=["GET"])
async def openai_models(request: Request) -> JSONResponse:
    return JSONResponse(openai_api.models_response())


@mcp.custom_route("/v1/chat/completions", methods=["POST"])
async def openai_chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
            status_code=400,
        )
    query = openai_api.last_user_message(body.get("messages") or [])
    if not query:
        return JSONResponse(
            {"error": {"message": "No user message provided", "type": "invalid_request_error"}},
            status_code=400,
        )
    model = body.get("model") or "larvis"
    try:
        content = await run_in_threadpool(openai_api.answer, model, query)
    except Exception as e:  # surface as assistant text so the sidebar shows something
        content = f"Larvis error: {e}"
    if body.get("stream"):
        return StreamingResponse(
            openai_api.stream_chunks(model, content), media_type="text/event-stream"
        )
    return JSONResponse(openai_api.completion_response(model, content))
```

- [ ] **Step 3: Verify the server imports cleanly with the routes**

Run:
```bash
uv run python -c "from larvis.server import mcp, openai_chat_completions, openai_models; print('routes ok')"
```
Expected: `routes ok`

- [ ] **Step 4: Run the full suite (no regressions)**

Run: `uv run pytest -q`
Expected: all pass (154 prior + 7 new = 161), 1 pre-existing ChromaDB warning.

- [ ] **Step 5: Commit**

```bash
git add larvis/server.py
git commit -m "feat: mount /v1/chat/completions + /v1/models on the larvis server"
```

---

## Task 3: Docs + live smoke + Deep Ask verification

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Document the endpoint in `CLAUDE.md`**

Add a new section to `CLAUDE.md` (after the MCP tools table):

```markdown
## OpenAI-compatible endpoint (Deep Ask / Obsidian)

Larvis also serves an OpenAI-compatible API on the same port, so the Deep Ask Obsidian
plugin (or any OpenAI-compatible client) can use it directly:

- `POST http://localhost:8765/v1/chat/completions` — chat completions (stream + non-stream)
- `GET  http://localhost:8765/v1/models`

Models: `larvis-vault` (vault RAG) and `larvis` (full orchestrator).

**Deep Ask setup:** Base URL `http://localhost:8765/v1`, API Key any value, Model `larvis-vault`
or `larvis`. Only the last user message is used (no multi-turn memory yet); the API key is ignored.
```

- [ ] **Step 2: Rebuild and restart the container**

```bash
docker compose build larvis
docker compose up -d larvis
sleep 12
docker compose logs larvis --tail 5
```
Expected: `Application startup complete.`

- [ ] **Step 3: Smoke — `GET /v1/models`**

```bash
curl -s http://localhost:8765/v1/models
```
Expected: JSON listing `larvis-vault` and `larvis`.

- [ ] **Step 4: Smoke — non-streaming completion (vault RAG)**

```bash
curl -s http://localhost:8765/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"larvis-vault","messages":[{"role":"user","content":"what is my spring garage cleanout budget and target weekend?"}]}'
```
Expected: a `chat.completion` JSON whose `choices[0].message.content` answers from the vault (e.g. "$300, June 21").

- [ ] **Step 5: Smoke — streaming completion (orchestrator)**

```bash
curl -s -N http://localhost:8765/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"larvis","stream":true,"messages":[{"role":"user","content":"what is on my calendar this week?"}]}'
```
Expected: `data:` SSE lines — a content delta chunk, a stop chunk, then `data: [DONE]`.

- [ ] **Step 6: Deep Ask end-to-end (manual, in Obsidian)**

In the Deep Ask plugin settings: set **Base URL** `http://localhost:8765/v1`, **API Key** any
value, **Model** `larvis-vault`. Open the Deep Ask sidebar and ask a vault question; confirm a
grounded answer appears. Switch the model to `larvis` and ask a cross-agent question (e.g.
"do I have time and budget for a date night?") to confirm orchestrator routing.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass (161), 1 pre-existing ChromaDB warning.

- [ ] **Step 8: Commit + Linear**

```bash
git add CLAUDE.md
git commit -m "docs: document the OpenAI-compatible endpoint + Deep Ask setup"
```
Mark PHA-73 Done in Linear. Push the branch and open a PR (do not merge — the user merges).

---

## Self-Review Notes

- **Spec coverage:** `POST /v1/chat/completions` non-stream + SSE stream (Task 2 handler + `completion_response`/`stream_chunks`) ✓; `GET /v1/models` (Task 2 + `models_response`) ✓; model dispatch `larvis-vault`→`rag.ask`, else→orchestrator (`answer`) ✓; last-user-message query (`last_user_message`) ✓; mounted on existing server via `custom_route` ✓; blocking brains via `run_in_threadpool` ✓; no API auth / any key accepted (handler ignores key) ✓; malformed body / no user message → 400 OpenAI error ✓; brain error → assistant text, not 500 ✓; unknown model → orchestrator ✓; no new deps ✓; live smoke + Deep Ask verification ✓.
- **Type consistency:** `last_user_message(messages) -> str`, `answer(model, query) -> str`, `completion_response(model, content) -> dict`, `stream_chunks(model, content) -> Iterator[str]`, `models_response() -> dict` are defined in Task 1 and called with those exact signatures in the Task 2 handlers. `openai_api.rag` and `openai_api.orchestrator_tools` are the monkeypatch targets in the tests and the real imports in the module.
- **Test count:** Task 1 adds 7 tests → 161 total.
```
