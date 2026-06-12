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
