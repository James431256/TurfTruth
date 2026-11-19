"""Weather-aware calendar slot booking service."""

import math

import store
from models import CalendarDay, CalendarSlot


class BookingError(Exception):
    """Base error for calendar booking failures."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class AlreadyBookedError(BookingError):
    """Raised when a quote already has a booked calendar slot."""

    def __init__(self, quote_id: str) -> None:
        super().__init__(
            f"Quote '{quote_id}' already has a booked slot.",
            code="already_booked",
        )


class NoSlotAvailableError(BookingError):
    """Raised when no contiguous dry slot can fit the requested duration."""

    def __init__(self, duration_hours: float) -> None:
        super().__init__(
            f"No dry calendar slot available for {duration_hours:.2f} hours.",
            code="no_slot_available",
        )


def _to_minutes(hhmm: str) -> int:
    hours, minutes = map(int, hhmm.split(":"))
    return hours * 60 + minutes


def _to_hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _find_free_window(
    day: CalendarDay,
    existing_slots: list[CalendarSlot],
    duration_minutes: int,
) -> tuple[int, int] | None:
    """Return the earliest (start_min, end_min) window on a day, or None."""
    day_start = _to_minutes(day.work_start)
    day_end = _to_minutes(day.work_end)
    busy_intervals = sorted(
        (_to_minutes(slot.start), _to_minutes(slot.end))
        for slot in existing_slots
        if slot.date == day.date and slot.booked
    )

    cursor = day_start
    for busy_start, busy_end in busy_intervals:
        window_end = min(busy_start, day_end)
        if window_end - cursor >= duration_minutes:
            return cursor, cursor + duration_minutes
        cursor = max(cursor, busy_end)
        if cursor >= day_end:
            return None

    if day_end - cursor >= duration_minutes:
        return cursor, cursor + duration_minutes
    return None


def book_next_free_slot(
    quote_id: str,
    client_name: str,
    duration_hours: float,
) -> CalendarSlot:
    """Book the earliest contiguous dry-day window for a quote."""
    if not math.isfinite(duration_hours) or duration_hours <= 0:
        raise NoSlotAvailableError(duration_hours)

    duration_minutes = round(duration_hours * 60)
    if duration_minutes <= 0:
        raise NoSlotAvailableError(duration_hours)

    existing_slots = store.list_calendar_slots()
    if any(slot.booked and slot.quote_id == quote_id for slot in existing_slots):
        raise AlreadyBookedError(quote_id)

    for day in store.list_calendar_days():
        if day.is_rain:
            continue
        window = _find_free_window(day, existing_slots, duration_minutes)
        if window is None:
            continue

        start_min, end_min = window
        slot = CalendarSlot(
            slot_id=f"slot-{len(existing_slots) + 1}",
            date=day.date,
            day_label=day.day_label,
            start=_to_hhmm(start_min),
            end=_to_hhmm(end_min),
            weather=day.weather,
            is_rain=day.is_rain,
            booked=True,
            quote_id=quote_id,
            title=client_name,
        )
        return store.add_calendar_slot(slot)

    raise NoSlotAvailableError(duration_hours)
