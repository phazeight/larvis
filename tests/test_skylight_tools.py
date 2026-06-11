from datetime import date, timedelta

from larvis.agents.skylight import client, tools


def _chore(cid, summary, completed=False, category_id=None, day="2026-06-11"):
    return {
        "id": cid,
        "summary": summary,
        "completed": completed,
        "category_id": category_id,
        "date": day,
    }


def test_window_today():
    after, before, label = tools._window("today")
    assert after == before == date.today().isoformat()
    assert label == "today"


def test_window_week():
    after, before, label = tools._window("week")
    assert after == date.today().isoformat()
    assert before == (date.today() + timedelta(days=7)).isoformat()
    assert label == "this week"


def test_chores_groups_members_and_up_for_grabs(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    monkeypatch.setattr(
        client,
        "list_chores",
        lambda a, b: [
            _chore("c1", "Feed dog", completed=True, category_id="m1"),
            _chore("c2", "Empty dishwasher", category_id=None),
        ],
    )
    out = tools.chores("today")
    assert "UP FOR GRABS" in out
    assert "Empty dishwasher" in out and "c2" in out
    assert "Callum" in out
    assert "Feed dog" in out and "c1" in out
    assert "✓" in out  # completed marker


def test_chores_empty(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [])
    monkeypatch.setattr(client, "list_chores", lambda a, b: [])
    assert "No chores" in tools.chores("today")


def test_status_lists_members(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    monkeypatch.setattr(tools.settings, "skylight_frame_id", "frame1")
    out = tools.status()
    assert "frame1" in out and "Callum" in out
