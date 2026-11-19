"""Typed Pydantic models for TurfTruth, keeping Gemini schemas free of pricing."""

from pydantic import BaseModel, Field


class GeminiTaskEstimate(BaseModel):
    """Structured task output from Gemini photo analysis (no £ fields)."""

    task_name: str
    estimated_hours: float = Field(gt=0)
    visual_evidence: str


class GeminiGardenAnalysisSchema(BaseModel):
    """Top-level Gemini response_schema for garden photo analysis."""

    tasks: list[GeminiTaskEstimate]


class QuoteTask(BaseModel):
    """A single itemised gardening task with Python-computed £ pricing."""

    task_id: str
    task_name: str
    estimated_hours: float = Field(gt=0)
    visual_evidence: str
    hourly_rate_gbp: float = Field(gt=0)
    line_total_gbp: float = Field(ge=0)
    enabled: bool = True


class Quote(BaseModel):
    """Complete itemised labour quote for a client garden."""

    quote_id: str
    client_name: str
    tasks: list[QuoteTask]
    total_hours: float = Field(ge=0)
    total_gbp: float = Field(ge=0)


class TaskHourAdjustment(BaseModel):
    """Gardener adjustment to a single task's estimated hours and enabled state."""

    task_id: str = Field(min_length=1)
    hours: float = Field(gt=0)
    enabled: bool = True


class QuoteAdjustRequest(BaseModel):
    """Request body for POST /quote/adjust."""

    quote_id: str = Field(min_length=1)
    adjustments: list[TaskHourAdjustment] = Field(min_length=1)


class QuoteAdjustResponse(BaseModel):
    """Response body for POST /quote/adjust."""

    quote: Quote


class AnalyseQuoteRequest(BaseModel):
    """Request body for POST /quote/analyse."""

    use_sample: bool = False
    image_base64: str | None = None
    filename: str | None = None
    client_name: str = "Mrs. Higgins — 14 Oak Lane"


class CalendarDay(BaseModel):
    """A single day on the gardener's week calendar."""

    date: str
    day_label: str
    weather: str
    is_rain: bool
    work_start: str = "08:00"
    work_end: str = "17:00"


class CalendarSlot(BaseModel):
    """A booked time block on the week calendar."""

    slot_id: str
    date: str
    day_label: str
    start: str
    end: str
    weather: str
    is_rain: bool
    booked: bool = True
    quote_id: str | None = None
    title: str


class CalendarResponse(BaseModel):
    """Week calendar days and booked slots."""

    days: list[CalendarDay]
    slots: list[CalendarSlot]


class BookSlotRequest(BaseModel):
    """Request body for POST /booking/next."""

    quote_id: str = Field(min_length=1)
    duration_hours: float = Field(gt=0)


class BookSlotResponse(BaseModel):
    """Response body for POST /booking/next."""

    booked_slot: CalendarSlot
    days: list[CalendarDay]
    slots: list[CalendarSlot]


class ApiBookingEntry(BaseModel):
    """Booked time range inside a week day for GET /api/calendar."""

    start: str
    end: str
    title: str


class ApiCalendarDay(BaseModel):
    """Day entry in GET /api/calendar response."""

    date: str
    label: str
    weather: str
    rain: bool
    bookings: list[ApiBookingEntry]


class ApiCalendarResponse(BaseModel):
    """Response body for GET /api/calendar."""

    week: list[ApiCalendarDay]
    working_hours: dict[str, str]


class ApiBookedSlot(BaseModel):
    """Slot summary returned by POST /api/book."""

    date: str
    start: str
    end: str


class ApiBookResponse(BaseModel):
    """Response body for POST /api/book."""

    slot: ApiBookedSlot | None
    message: str | None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    mode: str = "demo"
    prompt_version: str = "analyse_v1"


class ErrorDetail(BaseModel):
    """Structured error object inside ErrorResponse."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Typed error payload returned on 4xx/5xx responses."""

    error: ErrorDetail
    detail: str
    code: str
