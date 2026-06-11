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


def test_normalize_when_keywords():
    assert tools._normalize_when("today") == date.today().isoformat()
    assert tools._normalize_when("tomorrow") == (date.today() + timedelta(days=1)).isoformat()
    assert tools._normalize_when("2026-07-04") == "2026-07-04"


def test_is_up_for_grabs():
    assert tools._is_up_for_grabs("up-for-grabs") is True
    assert tools._is_up_for_grabs("Anyone") is True
    assert tools._is_up_for_grabs("Callum") is False


def test_add_chore_unknown_member_is_rejected_before_post(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])

    def boom(*a, **k):
        raise AssertionError("create_chore must not be called for an unknown member")

    monkeypatch.setattr(client, "create_chore", boom)
    out = tools.add_chore("Nobody", "Sweep")
    assert "Unknown member" in out and "Callum" in out


def test_add_chore_assigned(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    captured = {}

    def fake_create(summary, day, category_id):
        captured.update(summary=summary, day=day, category_id=category_id)
        return {"id": "new1"}

    monkeypatch.setattr(client, "create_chore", fake_create)
    out = tools.add_chore("callum", "Take out trash", "tomorrow")
    assert captured["category_id"] == "m1"
    assert captured["day"] == (date.today() + timedelta(days=1)).isoformat()
    assert "Callum" in out and "Take out trash" in out


def test_add_chore_up_for_grabs(monkeypatch):
    captured = {}

    def fake_create(summary, day, category_id):
        captured.update(category_id=category_id)
        return {"id": "new2"}

    monkeypatch.setattr(client, "create_chore", fake_create)
    out = tools.add_chore("up-for-grabs", "Wipe counters")
    assert captured["category_id"] is None
    assert "Up for Grabs" in out


def test_add_chore_bad_date(monkeypatch):
    monkeypatch.setattr(client, "get_categories", lambda: [{"id": "m1", "name": "Callum"}])
    out = tools.add_chore("Callum", "Sweep", "someday")
    assert "date" in out.lower()


def test_complete_chore_requires_id():
    assert "chore_id" in tools.complete_chore("  ")


def test_complete_chore_confirms(monkeypatch):
    monkeypatch.setattr(client, "complete_chore", lambda cid: {"id": cid})
    out = tools.complete_chore("c9")
    assert "c9" in out and "complete" in out.lower()
