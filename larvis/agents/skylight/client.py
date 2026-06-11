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
