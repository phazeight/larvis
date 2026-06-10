from datetime import datetime, time, timedelta

import ollama

from larvis.agents.gcal import auth, client, scheduling
from larvis.config import settings


def _now() -> datetime:
    return datetime.now().astimezone()


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def agenda(range: str = "today") -> str:
    now = _now()
    if range == "week":
        start, end = now, now + timedelta(days=7)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    try:
        events = client.list_events(start, end)
    except Exception as e:
        return f"Calendar error: {e}"

    label = "this week" if range == "week" else "today"
    if not events:
        return f"No events {label}."

    lines = [f"=== Agenda ({label}) ==="]
    current_day = None
    for e in events:
        if range == "week":
            day = e["start"].strftime("%a %b %d")
            if day != current_day:
                lines.append(f"\n{day}:")
                current_day = day
        when = "all day" if e["all_day"] else e["start"].strftime("%H:%M")
        loc = f" @ {e['location']}" if e.get("location") else ""
        lines.append(f"  {when}  {e['summary']}{loc}")
    return "\n".join(lines)


def status() -> str:
    try:
        auth.get_service()
    except Exception as e:
        return f"Calendar not authorized — run `larvis gcal-auth`. ({e})"
    cals = client._calendar_ids()
    return "Calendar authorized.\nConfigured calendars:\n" + "\n".join(
        f"  - {c}" for c in cals
    )
