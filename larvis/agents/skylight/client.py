import httpx

from larvis.agents.skylight import auth
from larvis.config import settings

# Pinned from a HAR capture + live probe of app.ourskylight.com.
API_VERSION = "2026-05-01"


def _base() -> str:
    return settings.skylight_base_url.rstrip("/")


def _frame() -> str:
    return settings.skylight_frame_id


def _headers(refresh: bool = False) -> dict:
    bearer = auth.refresh() if refresh else auth.auth_header()
    return {**bearer, "skylight-api-version": API_VERSION, "Content-Type": "application/json"}


def _request(method: str, path: str, **kwargs) -> dict:
    url = f"{_base()}/api{path}"
    with httpx.Client(timeout=30) as c:
        r = c.request(method, url, headers=_headers(), **kwargs)
        if r.status_code == 401:
            r = c.request(method, url, headers=_headers(refresh=True), **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}


def _is_member(raw: dict) -> bool:
    # Chore-chart profiles (the people you can assign chores to).
    return raw.get("attributes", {}).get("selected_for_chore_chart") is True


def _normalize_member(raw: dict) -> dict:
    attrs = raw.get("attributes", {})
    return {"id": str(raw.get("id")), "name": attrs.get("label") or attrs.get("name")}


def _normalize_chore(raw: dict) -> dict:
    attrs = raw.get("attributes", {})
    cat = (raw.get("relationships", {}).get("category", {}) or {}).get("data")
    return {
        "id": str(raw.get("id")),
        "summary": (attrs.get("summary") or "(untitled)").strip(),
        "completed": attrs.get("status") == "complete" or attrs.get("completed_on") is not None,
        "category_id": str(cat["id"]) if cat else None,
        "up_for_grabs": bool(attrs.get("up_for_grabs")),
        "date": attrs.get("start"),
    }


def get_categories() -> list[dict]:
    """Family members (chore-chart profiles) only."""
    data = _request("GET", f"/frames/{_frame()}/categories")
    return [_normalize_member(x) for x in data.get("data", []) if _is_member(x)]


def list_chores(after: str, before: str) -> list[dict]:
    data = _request(
        "GET",
        f"/frames/{_frame()}/chores",
        params={
            "after": after,
            "before": before,
            "include_late": "true",
            "include_up_for_grabs": "true",
            "filter": "linked_to_profile",
        },
    )
    return [_normalize_chore(x) for x in data.get("data", [])]


def create_chore(summary: str, day: str, category_id: str | None) -> dict:
    body: dict = {
        "start": day,
        "up_for_grabs": category_id is None,
        "routine": False,
        "start_time": None,
        "recurrence_set": None,
        "summary": summary,
    }
    if category_id is not None:
        body["category_ids"] = [category_id]
    else:
        body["timer_seconds"] = None
    return _request("POST", f"/frames/{_frame()}/chores/create_multiple", json=body)


def complete_chore(chore_id: str) -> dict:
    return _request(
        "PUT",
        f"/frames/{_frame()}/chores/{chore_id}/completions",
        json={"status": "complete"},
    )
