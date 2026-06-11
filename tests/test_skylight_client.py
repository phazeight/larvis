from larvis.agents.skylight import client


def test_normalize_chore_assigned():
    raw = {
        "id": "c1",
        "attributes": {"summary": "Feed dog", "status": "complete", "start": "2026-06-11"},
        "relationships": {"category": {"data": {"id": "m1", "type": "category"}}},
    }
    out = client._normalize_chore(raw)
    assert out == {
        "id": "c1",
        "summary": "Feed dog",
        "completed": True,
        "category_id": "m1",
        "date": "2026-06-11",
    }


def test_normalize_chore_up_for_grabs_has_no_category():
    raw = {
        "id": "c2",
        "attributes": {"summary": "Empty dishwasher", "status": "incomplete", "start": "2026-06-11"},
        "relationships": {"category": {"data": None}},
    }
    out = client._normalize_chore(raw)
    assert out["category_id"] is None
    assert out["completed"] is False


def test_normalize_member_reads_label():
    raw = {"id": "m1", "attributes": {"label": "Callum"}}
    assert client._normalize_member(raw) == {"id": "m1", "name": "Callum"}


def test_normalize_member_falls_back_to_name():
    raw = {"id": "m2", "attributes": {"name": "Maeve"}}
    assert client._normalize_member(raw) == {"id": "m2", "name": "Maeve"}
