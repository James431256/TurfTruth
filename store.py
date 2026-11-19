"""In-memory state for TurfTruth quotes and seeded weather/calendar slots."""

from copy import deepcopy
from typing import Any

from models import CalendarDay, CalendarSlot, Quote, QuoteTask
from services.pricing import DEFAULT_HOURLY_RATE_GBP, recalculate_quote


def _build_seed_quote() -> Quote:
    """Create the initial demo quote for the session."""
    raw = Quote(
        quote_id="demo-quote-1",
        client_name="Mrs. Higgins — 14 Oak Lane",
        tasks=[
            QuoteTask(
                task_id="t1",
                task_name="Overgrown lawn mow & edge",
                estimated_hours=2.0,
                visual_evidence="Grass ~15cm tall with creeping border edges.",
                hourly_rate_gbp=DEFAULT_HOURLY_RATE_GBP,
                line_total_gbp=0.0,
            ),
            QuoteTask(
                task_id="t2",
                task_name="Privet hedge trim & clear",
                estimated_hours=1.5,
                visual_evidence="Front boundary hedge ~2.2m tall, uneven top.",
                hourly_rate_gbp=DEFAULT_HOURLY_RATE_GBP,
                line_total_gbp=0.0,
            ),
            QuoteTask(
                task_id="t3",
                task_name="Patio weeding & sweep",
                estimated_hours=1.0,
                visual_evidence="Dandelions and moss between Yorkstone slabs.",
                hourly_rate_gbp=DEFAULT_HOURLY_RATE_GBP,
                line_total_gbp=0.0,
            ),
        ],
        total_hours=0.0,
        total_gbp=0.0,
    )
    return recalculate_quote(raw)


def _initial_store() -> dict[str, Any]:
    seed_quote = _build_seed_quote()
    days = [
        CalendarDay(date="2026-11-23", day_label="Mon 23 Nov", weather="Rain, 9C", is_rain=True),
        CalendarDay(date="2026-11-24", day_label="Tue 24 Nov", weather="Dry, 11C", is_rain=False),
        CalendarDay(date="2026-11-25", day_label="Wed 25 Nov", weather="Heavy Rain, 8C", is_rain=True),
        CalendarDay(date="2026-11-26", day_label="Thu 26 Nov", weather="Partly cloudy, 12C", is_rain=False),
        CalendarDay(date="2026-11-27", day_label="Fri 27 Nov", weather="Sunny, 13C", is_rain=False),
    ]
    slots = [
        CalendarSlot(
            slot_id="existing-1",
            date="2026-11-24",
            day_label="Tue 24 Nov",
            start="09:00",
            end="11:30",
            weather="Dry, 11C",
            is_rain=False,
            booked=True,
            quote_id="existing-patel",
            title="Mrs. Patel — Lawn & Borders",
        ),
        CalendarSlot(
            slot_id="existing-2",
            date="2026-11-26",
            day_label="Thu 26 Nov",
            start="10:00",
            end="12:30",
            weather="Partly cloudy, 12C",
            is_rain=False,
            booked=True,
            quote_id="existing-evans",
            title="Mr. Evans — Hedge Trim",
        ),
    ]
    return {
        "quotes": {seed_quote.quote_id: seed_quote},
        "calendar_days": days,
        "calendar_slots": slots,
        "working_hours": {"start": "08:00", "end": "17:00"},
        "quote_counter": 1,
    }


STORE: dict[str, Any] = _initial_store()


def get_quote(quote_id: str) -> Quote | None:
    """Return a copy of a quote by ID, or None if missing."""
    quote = STORE["quotes"].get(quote_id)
    return deepcopy(quote) if quote is not None else None


def save_quote(quote: Quote) -> Quote:
    """Persist a quote in the in-memory store and return it."""
    stored = deepcopy(quote)
    STORE["quotes"][stored.quote_id] = stored
    return deepcopy(stored)


def list_quotes() -> list[Quote]:
    """Return all quotes currently in memory."""
    return [deepcopy(q) for q in STORE["quotes"].values()]


def next_quote_id() -> str:
    """Generate a unique session quote ID."""
    STORE["quote_counter"] += 1
    return f"quote-{STORE['quote_counter']}"


def list_calendar_days() -> list[CalendarDay]:
    """Return all days in the week calendar."""
    return deepcopy(STORE["calendar_days"])


def list_calendar_slots() -> list[CalendarSlot]:
    """Return all booked slots in the week calendar."""
    return deepcopy(STORE["calendar_slots"])


def add_calendar_slot(slot: CalendarSlot) -> CalendarSlot:
    """Persist a new booked slot in memory."""
    stored = deepcopy(slot)
    STORE["calendar_slots"].append(stored)
    return deepcopy(stored)


def get_api_calendar() -> dict[str, Any]:
    """Return the /api/calendar week and working_hours payload."""
    slots = list_calendar_slots()
    week = []
    for day in list_calendar_days():
        day_bookings = sorted(
            (
                {"start": s.start, "end": s.end, "title": s.title}
                for s in slots
                if s.date == day.date and s.booked
            ),
            key=lambda b: (b["start"], b["end"]),
        )
        week.append(
            {
                "date": day.date,
                "label": day.day_label,
                "weather": day.weather,
                "rain": day.is_rain,
                "bookings": day_bookings,
            }
        )
    return {
        "week": week,
        "working_hours": deepcopy(STORE.get("working_hours", {"start": "08:00", "end": "17:00"})),
    }


def record_api_booking(
    date: str,
    start: str,
    end: str,
    title: str = "Booked Garden Job",
) -> tuple[CalendarSlot, str]:
    """Record a newly booked slot from POST /api/book into STORE and return (slot, day_label)."""
    days_by_date = {d.date: d for d in list_calendar_days()}
    day = days_by_date.get(date)
    day_label = day.day_label if day else date
    weather = day.weather if day else "Dry"
    is_rain = day.is_rain if day else False
    slot_num = len(STORE["calendar_slots"]) + 1
    slot = CalendarSlot(
        slot_id=f"slot-{slot_num}",
        date=date,
        day_label=day_label,
        start=start,
        end=end,
        weather=weather,
        is_rain=is_rain,
        booked=True,
        quote_id=f"api-book-{slot_num}",
        title=title,
    )
    return add_calendar_slot(slot), day_label


def reset_store() -> None:
    """Reset in-memory state to initial seeded values."""
    STORE.clear()
    STORE.update(_initial_store())
