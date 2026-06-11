from larvis.agents.skylight import client


def test_normalize_chore_assigned():
    raw = {
        "id": "16089131-2026-06-06",
        "attributes": {
            "summary": "Pick up living room ",
            "status": "pending",
            "start": "2026-06-06",
            "up_for_grabs": False,
        },
        "relationships": {"category": {"data": {"id": "578315", "type": "category"}}},
    }
    out = client._normalize_chore(raw)
    assert out == {
        "id": "16089131-2026-06-06",
        "summary": "Pick up living room",
        "completed": False,
        "category_id": "578315",
        "up_for_grabs": False,
        "date": "2026-06-06",
    }


def test_normalize_chore_completed_via_status():
    raw = {
        "id": "x",
        "attributes": {"summary": "s", "status": "complete", "start": "2026-06-06"},
        "relationships": {"category": {"data": None}},
    }
    assert client._normalize_chore(raw)["completed"] is True


def test_normalize_chore_up_for_grabs():
    raw = {
        "id": "y",
        "attributes": {"summary": "s", "status": "pending", "start": "2026-06-06", "up_for_grabs": True},
        "relationships": {"category": {"data": None}},
    }
    out = client._normalize_chore(raw)
    assert out["category_id"] is None
    assert out["up_for_grabs"] is True


def test_normalize_member_uses_label():
    raw = {"id": "578315", "attributes": {"label": "Cal"}}
    assert client._normalize_member(raw) == {"id": "578315", "name": "Cal"}


def test_is_member_requires_chore_chart():
    assert client._is_member({"attributes": {"selected_for_chore_chart": True}}) is True
    assert client._is_member({"attributes": {"selected_for_chore_chart": False}}) is False
