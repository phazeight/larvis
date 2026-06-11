from datetime import datetime, timezone

from larvis.agents.gcal import auth, client, tools

UTC = timezone.utc


def _event(day, hour, summary, all_day=False, location=None):
    return {
        "summary": summary,
        "start": datetime(2026, 6, day, hour, 0, tzinfo=UTC),
        "end": datetime(2026, 6, day, hour + 1, 0, tzinfo=UTC),
        "all_day": all_day,
        "location": location,
        "calendar": "primary",
    }


def test_agenda_lists_events(monkeypatch):
    monkeypatch.setattr(client, "list_events", lambda a, b: [_event(10, 9, "Standup")])
    out = tools.agenda("today")
    assert "Standup" in out
    assert "09:00" in out


def test_agenda_empty(monkeypatch):
    monkeypatch.setattr(client, "list_events", lambda a, b: [])
    assert "No events" in tools.agenda("today")


def test_status_lists_calendars(monkeypatch):
    monkeypatch.setattr(auth, "get_service", lambda: object())
    monkeypatch.setattr(client, "_calendar_ids", lambda: ["primary", "work@example.com"])
    out = tools.status()
    assert "primary" in out
    assert "work@example.com" in out


def test_status_reports_unauthorized(monkeypatch):
    def boom():
        raise RuntimeError("no token")

    monkeypatch.setattr(auth, "get_service", boom)
    out = tools.status()
    assert "gcal-auth" in out


def test_find_time_returns_slot(monkeypatch):
    busy = [(datetime(2026, 6, 10, 12, tzinfo=UTC), datetime(2026, 6, 10, 13, tzinfo=UTC))]
    monkeypatch.setattr(tools, "_now", lambda: datetime(2026, 6, 10, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(client, "free_busy", lambda a, b: busy)
    out = tools.find_time(60, "today")
    assert "Open slots" in out


def test_find_time_none_available(monkeypatch):
    busy = [(datetime(2026, 6, 10, 9, tzinfo=UTC), datetime(2026, 6, 10, 17, tzinfo=UTC))]
    monkeypatch.setattr(tools, "_now", lambda: datetime(2026, 6, 10, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(client, "free_busy", lambda a, b: busy)
    out = tools.find_time(60, "today")
    assert "No 60-minute openings" in out


def test_ask_degrades_when_ollama_down(monkeypatch):
    monkeypatch.setattr(client, "list_events", lambda a, b: [_event(11, 15, "Dentist")])

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("ollama down")

    monkeypatch.setattr(tools.ollama, "Client", Boom)
    out = tools.ask("when is my dentist appointment?")
    assert "Dentist" in out
