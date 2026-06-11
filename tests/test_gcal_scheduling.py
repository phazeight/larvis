from datetime import datetime, time, timezone

from larvis.agents.gcal.scheduling import open_slots

UTC = timezone.utc


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=UTC)


def test_no_busy_returns_full_working_window():
    slots = open_slots(
        busy_blocks=[],
        window_start=_dt(10, 0),
        window_end=_dt(10, 23, 59),
        work_start=time(9, 0),
        work_end=time(17, 0),
        duration_minutes=60,
    )
    assert slots == [(_dt(10, 9), _dt(10, 17))]


def test_meeting_splits_into_two_slots():
    busy = [(_dt(10, 12), _dt(10, 13))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == [(_dt(10, 9), _dt(10, 12)), (_dt(10, 13), _dt(10, 17))]


def test_all_day_event_blocks_the_day():
    busy = [(_dt(10, 0), _dt(11, 0))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == []


def test_overlapping_busy_blocks_merge():
    busy = [(_dt(10, 10), _dt(10, 12)), (_dt(10, 11), _dt(10, 13))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == [(_dt(10, 9), _dt(10, 10)), (_dt(10, 13), _dt(10, 17))]


def test_duration_larger_than_gaps_excluded():
    busy = [(_dt(10, 10), _dt(10, 16))]
    slots = open_slots(busy, _dt(10, 0), _dt(10, 23, 59), time(9, 0), time(17, 0), 120)
    assert slots == []


def test_spans_multiple_days():
    slots = open_slots([], _dt(10, 0), _dt(11, 23, 59), time(9, 0), time(17, 0), 60)
    assert slots == [(_dt(10, 9), _dt(10, 17)), (_dt(11, 9), _dt(11, 17))]
