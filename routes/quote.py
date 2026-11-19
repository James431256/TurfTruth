"""Quote adjustment and retrieval routes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import store
from models import (
    AnalyseQuoteRequest,
    ErrorResponse,
    Quote,
    QuoteAdjustRequest,
    QuoteAdjustResponse,
    QuoteTask,
)
from routes.errors import error_response
from services.pricing import (
    DEFAULT_HOURLY_RATE_GBP,
    InvalidHoursError,
    QuotePricingError,
    TaskNotFoundError,
    apply_hour_adjustments,
    recalculate_quote,
)
from services.vision import NoPhotoError, NotAGardenError, analyse_garden_photo

router = APIRouter(prefix="/quote", tags=["quote"])


@router.get(
    "/{quote_id}",
    response_model=Quote,
    responses={404: {"model": ErrorResponse}},
)
def get_quote(quote_id: str) -> Quote | JSONResponse:
    """Fetch a quote by ID from the in-memory store."""
    quote = store.get_quote(quote_id)
    if quote is None:
        return error_response(404, f"Quote '{quote_id}' not found.", "quote_not_found")
    return quote


@router.post(
    "/adjust",
    response_model=QuoteAdjustResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def adjust_quote_hours(payload: QuoteAdjustRequest) -> QuoteAdjustResponse | JSONResponse:
    """Adjust task hours on a quote and recalculate £ totals."""
    quote = store.get_quote(payload.quote_id)
    if quote is None:
        return error_response(
            404,
            f"Quote '{payload.quote_id}' not found.",
            "quote_not_found",
        )

    try:
        updated = apply_hour_adjustments(quote, payload.adjustments)
    except TaskNotFoundError as exc:
        return error_response(404, exc.message, exc.code)
    except InvalidHoursError as exc:
        return error_response(400, exc.message, exc.code)
    except QuotePricingError as exc:
        return error_response(400, exc.message, exc.code)

    saved = store.save_quote(updated)
    return QuoteAdjustResponse(quote=saved)


@router.post(
    "/analyse",
    response_model=Quote,
    responses={400: {"model": ErrorResponse}},
)
def analyse_quote(payload: AnalyseQuoteRequest) -> Quote | JSONResponse:
    """Analyse a garden photo or sample garden and return a priced Quote."""
    try:
        analysis = analyse_garden_photo(
            use_sample=payload.use_sample,
            image_base64=payload.image_base64,
            filename=payload.filename,
        )
    except NoPhotoError as exc:
        return error_response(400, str(exc), "no_photo")
    except NotAGardenError as exc:
        return error_response(400, str(exc), "not_a_garden")

    tasks = [
        QuoteTask(
            task_id=f"t{idx}",
            task_name=task.task_name,
            estimated_hours=task.estimated_hours,
            visual_evidence=task.visual_evidence,
            hourly_rate_gbp=DEFAULT_HOURLY_RATE_GBP,
            line_total_gbp=0.0,
            enabled=True,
        )
        for idx, task in enumerate(analysis.tasks, start=1)
    ]
    raw_quote = Quote(
        quote_id=store.next_quote_id(),
        client_name=payload.client_name,
        tasks=tasks,
        total_hours=0.0,
        total_gbp=0.0,
    )
    calculated = recalculate_quote(raw_quote)
    return store.save_quote(calculated)
