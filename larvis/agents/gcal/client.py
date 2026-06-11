from datetime import datetime

from larvis.agents.gcal import auth
from larvis.config import settings


def _calendar_ids() -> list[str]:
    return [c.strip() for c in settings.gcal_calendar_ids.split(",") if c.strip()]


def _parse_dt(raw: str) -> datetime:
    if "T" in raw:  # timed event, e.g. "2026-06-10T09:00:00-04:00"
        return datetime.fromisoformat(raw)
    # all-day event: date only ("2026-06-10") -> midnight in local tz
    local_tz = datetime.now().astimezone().tzinfo
    return datetime.fromisoformat(raw).replace(tzinfo=local_tz)


def _normalize(event: dict, cal_id: str) -> dict:
    all_day = "date" in event["start"]
    start_raw = event["start"].get("dateTime", event["start"].get("date"))
    end_raw = event["end"].get("dateTime", event["end"].get("date"))
    return {
        "summary": event.get("summary", "(no title)"),
        "start": _parse_dt(start_raw),
        "end": _parse_dt(end_raw),
        "all_day": all_day,
        "location": event.get("location"),
        "calendar": cal_id,
    }


def list_events(time_min: datetime, time_max: datetime) -> list[dict]:
    service = auth.get_service()
    events: list[dict] = []
    for cal_id in _calendar_ids():
        resp = (
            service.events()
            .list(
                calendarId=cal_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        for item in resp.get("items", []):
            events.append(_normalize(item, cal_id))
    events.sort(key=lambda e: e["start"])
    return events


def free_busy(time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
    service = auth.get_service()
    body = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "items": [{"id": c} for c in _calendar_ids()],
    }
    resp = service.freebusy().query(body=body).execute()
    blocks: list[tuple[datetime, datetime]] = []
    for cal in resp.get("calendars", {}).values():
        for b in cal.get("busy", []):
            blocks.append(
                (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            )
    return blocks
