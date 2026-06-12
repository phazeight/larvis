# Larvis — OpenAI-Compatible Endpoint (Deep Ask bridge) Design Spec

**Date:** 2026-06-12
**Status:** Approved (design)
**Tracking:** [PHA-73](https://linear.app/phazeight/issue/PHA-73/deep-ask-obsidian-integration-openai-compatible-api-endpoint) (under [PHA-52](https://linear.app/phazeight/issue/PHA-52/larvis-personal-ai-productivity-orchestrator))

## Summary

An OpenAI-compatible HTTP endpoint on the Larvis server so the **Deep Ask** Obsidian
plugin (and any OpenAI-compatible client) can talk to Larvis directly from inside Obsidian —
no Claude Code needed. Deep Ask supports a custom **Base URL + API Key + Model**; pointing it
at Larvis turns the right-hand AI panel into a Larvis front end. Two models are exposed:
`larvis-vault` (vault RAG) and `larvis` (the full orchestrator).

The endpoint mounts on the **existing** FastMCP server (port 8765) as a custom route — one
process, reusing the running RAG and orchestrator. No new dependencies (Starlette ships with
FastMCP).

## Goals (v1)

- `POST /v1/chat/completions` — OpenAI Chat Completions, supporting both non-streaming JSON
  and SSE streaming (`stream: true`).
- `GET /v1/models` — list the two Larvis models.
- **Model dispatch:** `larvis-vault` → `rag.ask`; anything else (`larvis`, unknown) → the
  orchestrator.
- Works end-to-end from the Deep Ask sidebar against the user's real vault.

## Non-goals (v1) — explicitly deferred

- **No conversation memory** — only the last user message is used (`rag.ask`/`orchestrate`
  are single-shot). Multi-turn context is a later enhancement.
- **No API-key authentication** — localhost, single user; any key value is accepted and
  ignored. (A token check is a trivial later add.)
- **No token-by-token streaming** — the answer is produced whole by Ollama, then emitted as a
  single SSE delta. The SSE format is honored; the typing animation just arrives in one burst.
- **No embeddings / other OpenAI endpoints** — only chat completions + models.
- **No write confirmation UX in the chat box** — the orchestrator still returns its
  propose→confirm text; executing a confirmed write from Deep Ask is out of scope for v1.

## Architecture

### Module layout

```
larvis/openai_api.py   # pure logic: parse request, dispatch model, shape OpenAI responses
larvis/server.py       # 2 thin @mcp.custom_route handlers that call into openai_api
```

### Endpoints (mounted via `@mcp.custom_route` on the FastMCP app, port 8765)

| Route | Method | Purpose |
|-------|--------|---------|
| `/v1/chat/completions` | POST | Chat completions. Reads `model` + last user message, dispatches, returns a completion (JSON) or an SSE stream when `stream: true`. |
| `/v1/models` | GET | Returns the two models (`larvis-vault`, `larvis`) in OpenAI list shape. |

### Model dispatch (`openai_api.answer`)

```
model == "larvis-vault"        -> rag.ask(message)
otherwise ("larvis", unknown)  -> orchestrator_tools.orchestrate(message)
```

The query is `_last_user_message(messages)` — the content of the last `role: "user"` entry.

### Response shapes

**Non-streaming** — standard `chat.completion`:
```json
{ "id": "chatcmpl-<uuid>", "object": "chat.completion", "created": <epoch>,
  "model": "larvis-vault",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "<answer>"},
               "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0} }
```

**Streaming** (`stream: true`) — `text/event-stream`, the full answer as one delta then stop:
```
data: {"id":"chatcmpl-<uuid>","object":"chat.completion.chunk","created":<epoch>,"model":"<m>","choices":[{"index":0,"delta":{"role":"assistant","content":"<answer>"},"finish_reason":null}]}

data: {"id":"chatcmpl-<uuid>","object":"chat.completion.chunk","created":<epoch>,"model":"<m>","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

**Models** — `GET /v1/models`:
```json
{ "object": "list", "data": [
  {"id": "larvis-vault", "object": "model", "owned_by": "larvis"},
  {"id": "larvis", "object": "model", "owned_by": "larvis"} ] }
```

### The blocking detail (critical)

The `custom_route` handlers are **async** (Starlette), but `rag.ask` / `orchestrate` are
**synchronous and block on Ollama**. They MUST run via `starlette.concurrency.run_in_threadpool`
so a single Deep Ask request does not freeze the event loop — which would also stall the MCP
server, since both share the one process and port.

## Data flow

`Deep Ask → POST /v1/chat/completions` → handler parses JSON → `_last_user_message` →
`run_in_threadpool(answer, model, query)` (→ `rag.ask` or `orchestrate`) → if `stream`, wrap in
SSE generator; else wrap in a `chat.completion` JSON → response.

## Error handling

- Malformed body / no user message → HTTP 400 with OpenAI error JSON
  (`{"error": {"message": ..., "type": "invalid_request_error"}}`).
- The dispatched brain raising (e.g. Ollama down) → return its error text as the assistant
  message content (so the sidebar shows something useful), consistent with how the tools already
  degrade — not a 500.
- Unknown model → treated as `larvis` (orchestrator), not an error.

## Testing strategy

- **Unit (TDD, no network):** `_last_user_message` (picks the last user turn; handles empty),
  `answer` dispatch (monkeypatch `rag.ask` + `orchestrate`, assert the right one is called per
  model), `completion_response` shape, `stream_chunks` SSE format (delta chunk + stop +
  `[DONE]`), `models_response` shape. ~8–10 tests.
- **Live smoke:** `curl` `/v1/models` and `/v1/chat/completions` for both models × stream and
  non-stream against the running container; then configure Deep Ask (Base URL
  `http://localhost:8765/v1`, dummy key, model `larvis-vault`) in Obsidian and confirm the
  sidebar answers a vault question end-to-end.

## Dependencies

No new Python dependencies — Starlette ships with FastMCP; `rag` and the orchestrator already exist.

## Wiring checklist (for the plan)

- `larvis/openai_api.py` (parse, dispatch, shape)
- `tests/test_openai_api.py`
- `larvis/server.py` — 2 `@mcp.custom_route` handlers + `run_in_threadpool`
- `CLAUDE.md` — document the endpoint + Deep Ask setup
- Live smoke + Deep Ask sidebar verification; mark PHA-73 done
