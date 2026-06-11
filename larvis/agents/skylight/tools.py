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
