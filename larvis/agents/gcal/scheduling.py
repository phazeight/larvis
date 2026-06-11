from datetime import datetime, time, timedelta


def _merge(blocks: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: b[0])
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def open_slots(
    busy_blocks: list[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
    work_start: time,
    work_end: time,
    duration_minutes: int,
) -> list[tuple[datetime, datetime]]:
    """Free slots >= duration within working hours, for each day in the window."""
    duration = timedelta(minutes=duration_minutes)
    tz = window_start.tzinfo
    merged = _merge(busy_blocks)
    slots: list[tuple[datetime, datetime]] = []

    day = window_start.date()
    last_day = window_end.date()
    while day <= last_day:
        day_ws = datetime.combine(day, work_start, tzinfo=tz)
        day_we = datetime.combine(day, work_end, tzinfo=tz)
        seg_start = max(day_ws, window_start)
        seg_end = min(day_we, window_end)
        if seg_start < seg_end:
            cursor = seg_start
            for b_start, b_end in merged:
                if b_end <= seg_start or b_start >= seg_end:
                    continue
                bs = max(b_start, seg_start)
                if bs - cursor >= duration:
                    slots.append((cursor, bs))
                cursor = max(cursor, min(b_end, seg_end))
            if seg_end - cursor >= duration:
                slots.append((cursor, seg_end))
        day += timedelta(days=1)
    return slots
