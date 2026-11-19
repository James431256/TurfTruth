"""Calendar retrieval and one-click weather-safe booking routes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import store
from models import (
    BookSlotRequest,
    BookSlotResponse,
    CalendarResponse,
    ErrorResponse,
)
from routes.errors import error_response
from services.booking import (
    AlreadyBookedError,
    NoSlotAvailableError,
    book_next_free_slot,
)

router = APIRouter(tags=["booking"])


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar() -> CalendarResponse:
    """Return seeded calendar days and currently booked slots."""
    return CalendarResponse(
        days=store.list_calendar_days(),
        slots=store.list_calendar_slots(),
    )


@router.post(
    "/booking/next",
    response_model=BookSlotResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def book_next_slot(payload: BookSlotRequest) -> BookSlotResponse | JSONResponse:
    """Book the next free dry-weather slot for an existing quote."""
    quote = store.get_quote(payload.quote_id)
    if quote is None:
        return error_response(
            404,
            f"Quote '{payload.quote_id}' not found.",
            "quote_not_found",
        )

    try:
        booked_slot = book_next_free_slot(
            quote_id=quote.quote_id,
            client_name=quote.client_name,
            duration_hours=payload.duration_hours,
        )
    except AlreadyBookedError as exc:
        return error_response(409, exc.message, exc.code)
    except NoSlotAvailableError as exc:
        return error_response(400, exc.message, exc.code)

    return BookSlotResponse(
        booked_slot=booked_slot,
        days=store.list_calendar_days(),
        slots=store.list_calendar_slots(),
    )
