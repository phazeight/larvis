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


def find_time(duration_minutes: int, within: str = "week") -> str:
    now = _now()
    if within == "week":
        end = now + timedelta(days=7)
    else:
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    try:
        busy = client.free_busy(now, end)
    except Exception as e:
        return f"Calendar error: {e}"

    slots = scheduling.open_slots(
        busy,
        now,
        end,
        _parse_hhmm(settings.gcal_work_start),
        _parse_hhmm(settings.gcal_work_end),
        duration_minutes,
    )
    label = "this week" if within == "week" else "today"
    if not slots:
        return f"No {duration_minutes}-minute openings in working hours {label}."

    lines = [f"=== Open slots (>= {duration_minutes} min, {label}) ==="]
    for s, e in slots:
        lines.append(f"  {s.strftime('%a %b %d  %H:%M')} - {e.strftime('%H:%M')}")
    return "\n".join(lines)


def _build_context(events: list[dict]) -> str:
    if not events:
        return "No events in the next 7 days."
    lines = []
    for e in events:
        if e["all_day"]:
            when = e["start"].strftime("%a %b %d") + " all day"
        else:
            when = (
                e["start"].strftime("%a %b %d %H:%M")
                + "-"
                + e["end"].strftime("%H:%M")
            )
        lines.append(f"  {when}  {e['summary']}")
    return "\n".join(lines)


def ask(query: str) -> str:
    now = _now()
    try:
        events = client.list_events(now, now + timedelta(days=7))
    except Exception as e:
        return f"Calendar error: {e}"

    context = _build_context(events)
    try:
        resp = ollama.Client(host=settings.ollama_host).generate(
            model=settings.ollama_model,
            prompt=(
                "You are a calendar assistant. Answer the question using ONLY the "
                "schedule below. Do not invent events. If the data does not contain "
                "the answer, say so.\n\n"
                f"Schedule (next 7 days):\n{context}\n\n"
                f"Question: {query}"
            ),
        )
        return resp.response
    except Exception:
        return context
