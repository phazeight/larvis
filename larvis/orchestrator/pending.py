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
