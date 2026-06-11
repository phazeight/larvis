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
            who = next(
                (m["name"] for m in members if m["id"] == category_id),
                member,
            )
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
