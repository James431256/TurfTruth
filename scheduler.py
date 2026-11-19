"""Pure weather-safe calendar slot scheduling functions for TurfTruth."""

import math
from typing import Any

DEFAULT_WORKING_HOURS: dict[str, str] = {"start": "08:00", "end": "17:00"}


def _to_minutes(hhmm: str) -> int:
    """Convert an 'HH:MM' time string into minutes since midnight."""
    parts = hhmm.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {hhmm!r}. Expected 'HH:MM'.")
    hours, minutes = int(parts[0]), int(parts[1])
    if not (0 <= hours <= 24 and 0 <= minutes < 60) or (hours == 24 and minutes > 0):
        raise ValueError(f"Out-of-range time: {hhmm!r}.")
    return hours * 60 + minutes


def _to_hhmm(total_minutes: int) -> str:
    """Convert minutes since midnight into an 'HH:MM' string."""
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _find_day_gap(
    day_start: int,
    day_end: int,
    bookings: list[dict[str, Any]],
    duration_minutes: int,
) -> tuple[int, int] | None:
    """Find the earliest [start_min, end_min] gap on a single day."""
    busy_intervals = sorted(
        (_to_minutes(b["start"]), _to_minutes(b["end"]))
        for b in bookings
        if b.get("booked", True)
    )
    cursor = day_start
    for busy_start, busy_end in busy_intervals:
        if busy_end <= cursor:
            continue
        window_end = min(busy_start, day_end)
        if window_end - cursor >= duration_minutes:
            return cursor, cursor + duration_minutes
        cursor = max(cursor, busy_end)
        if cursor >= day_end:
            return None

    if day_end - cursor >= duration_minutes:
        return cursor, cursor + duration_minutes
    return None


def find_next_slot_with_reason(
    duration_hours: float,
    week: list[dict[str, Any]],
    working_hours: dict[str, str] | None = None,
) -> tuple[dict[str, str] | None, str]:
    """Find the earliest dry-day slot and return (slot_or_none, human_message)."""
    if (
        isinstance(duration_hours, bool)
        or not isinstance(duration_hours, (int, float))
        or not math.isfinite(duration_hours)
        or duration_hours <= 0
    ):
        raise ValueError("duration_hours must be > 0")

    duration_minutes = round(duration_hours * 60)
    if duration_minutes <= 0:
        raise ValueError("duration_hours must be > 0")

    wh = working_hours or DEFAULT_WORKING_HOURS
    start_str = wh.get("start", DEFAULT_WORKING_HOURS["start"])
    end_str = wh.get("end", DEFAULT_WORKING_HOURS["end"])
    day_start = _to_minutes(start_str)
    day_end = _to_minutes(end_str)

    if day_end <= day_start:
        raise ValueError("working_hours end must be after start")

    if duration_minutes > (day_end - day_start):
        return (
            None,
            f"Job duration exceeds a single working day ({start_str}–{end_str}).",
        )

    for day in week:
        if bool(day.get("rain") or day.get("is_rain")):
            continue
        bookings = list(day.get("bookings", []))
        gap = _find_day_gap(day_start, day_end, bookings, duration_minutes)
        if gap is not None:
            start_min, end_min = gap
            slot = {
                "date": str(day["date"]),
                "start": _to_hhmm(start_min),
                "end": _to_hhmm(end_min),
            }
            label = day.get("label") or day.get("day_label") or slot["date"]
            return slot, f"Booked for {label}, {slot['start']}–{slot['end']}."

    return None, "No free dry-day slot available this week."


def find_next_slot(
    duration_hours: float,
    week: list[dict[str, Any]],
    working_hours: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Find the earliest contiguous dry-day slot of duration_hours without overlaps."""
    slot, _ = find_next_slot_with_reason(duration_hours, week, working_hours)
    return slot
