"""Unit tests for pure weather-safe calendar scheduling in scheduler.py."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from scheduler import find_next_slot, find_next_slot_with_reason

MOCK_CALENDAR_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_calendar.json"


@pytest.fixture
def calendar_data() -> dict[str, Any]:
    """Load a fresh copy of data/mock_calendar.json for each test."""
    return json.loads(MOCK_CALENDAR_PATH.read_text(encoding="utf-8"))


def test_mock_calendar_json_contract(calendar_data: dict[str, Any]) -> None:
    """Verify data/mock_calendar.json has Mon-Fri, >=2 bookings, and >=1 rain day."""
    week = calendar_data["week"]
    assert len(week) == 5
    dates = [day["date"] for day in week]
    assert dates == [
        "2026-11-23",
        "2026-11-24",
        "2026-11-25",
        "2026-11-26",
        "2026-11-27",
    ]
    rain_days = [d for d in week if d.get("rain")]
    assert len(rain_days) >= 1
    total_bookings = sum(len(d.get("bookings", [])) for d in week)
    assert total_bookings >= 2
    assert calendar_data["working_hours"] == {"start": "08:00", "end": "17:00"}


def test_skips_monday_rain_and_fits_before_existing_booking(
    calendar_data: dict[str, Any],
) -> None:
    """1.0h job skips rainy Monday and fits in 08:00-09:00 on Tuesday before 09:00-11:30."""
    slot = find_next_slot(
        1.0,
        calendar_data["week"],
        calendar_data["working_hours"],
    )
    assert slot == {
        "date": "2026-11-24",
        "start": "08:00",
        "end": "09:00",
    }


def test_touching_edge_after_existing_booking(calendar_data: dict[str, Any]) -> None:
    """4.5h job does not fit in 08:00-09:00, so it starts at 11:30 right after 09:00-11:30."""
    slot, reason = find_next_slot_with_reason(
        4.5,
        calendar_data["week"],
        calendar_data["working_hours"],
    )
    assert slot == {
        "date": "2026-11-24",
        "start": "11:30",
        "end": "16:00",
    }
    assert "Tue 24 Nov" in reason
    assert "11:30–16:00" in reason


def test_touching_boundaries_exact_fit_between_bookings() -> None:
    """A 2.0h job fits tightly inside an exact 10:00-12:00 gap between two bookings."""
    week = [
        {
            "date": "2026-11-24",
            "label": "Tue 24 Nov",
            "rain": False,
            "bookings": [
                {"start": "12:00", "end": "15:00", "title": "Afternoon job"},
                {"start": "08:00", "end": "10:00", "title": "Morning job"},
            ],
        }
    ]
    slot = find_next_slot(2.0, week, {"start": "08:00", "end": "17:00"})
    assert slot == {
        "date": "2026-11-24",
        "start": "10:00",
        "end": "12:00",
    }


def test_skips_rain_and_insufficient_gaps_to_land_on_friday(
    calendar_data: dict[str, Any],
) -> None:
    """6.0h job skips Mon (rain), Tue (max 5.5h), Wed (rain), Thu (max 4.5h) -> Fri 08:00-14:00."""
    slot = find_next_slot(
        6.0,
        calendar_data["week"],
        calendar_data["working_hours"],
    )
    assert slot == {
        "date": "2026-11-27",
        "start": "08:00",
        "end": "14:00",
    }


def test_never_returns_rain_day_even_when_dry_days_full(
    calendar_data: dict[str, Any],
) -> None:
    """When all dry days are fully booked, returns None rather than booking a rain day."""
    week = deepcopy(calendar_data["week"])
    for day in week:
        if not day["rain"]:
            day["bookings"] = [{"start": "08:00", "end": "17:00", "title": "Full day"}]

    slot, reason = find_next_slot_with_reason(1.0, week, calendar_data["working_hours"])
    assert slot is None
    assert "No free dry-day slot" in reason


def test_returns_none_when_duration_exceeds_working_day(
    calendar_data: dict[str, Any],
) -> None:
    """A 9.5h job exceeds the 9.0h (08:00-17:00) working day and returns None."""
    slot, reason = find_next_slot_with_reason(
        9.5,
        calendar_data["week"],
        calendar_data["working_hours"],
    )
    assert slot is None
    assert "exceeds a single working day" in reason


def test_full_day_9h_job_fits_on_completely_free_dry_day(
    calendar_data: dict[str, Any],
) -> None:
    """An exact 9.0h job fits on Friday 08:00-17:00 which has no bookings."""
    slot = find_next_slot(9.0, calendar_data["week"], calendar_data["working_hours"])
    assert slot == {
        "date": "2026-11-27",
        "start": "08:00",
        "end": "17:00",
    }


@pytest.mark.parametrize(
    "bad_duration",
    [0, 0.0, -1.0, -0.25, float("nan"), float("inf"), float("-inf"), True, False, "2"],
)
def test_rejects_non_positive_or_non_finite_duration(
    bad_duration: object,
    calendar_data: dict[str, Any],
) -> None:
    """Duration <= 0, NaN, inf, bool, or non-number raises ValueError."""
    with pytest.raises(ValueError, match="duration_hours must be > 0"):
        find_next_slot(bad_duration, calendar_data["week"])  # type: ignore[arg-type]
