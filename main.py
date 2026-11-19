"""FastAPI entrypoint for TurfTruth."""

import base64
import binascii
from email.parser import BytesParser
from email.policy import default as default_policy
import json
import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

import ai
from models import ApiBookedSlot, ApiBookResponse, ApiCalendarResponse
from routes import booking, pages, quote
from routes.errors import error_response
import scheduler
import store

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SAMPLE_IMAGE_PATH = Path(__file__).parent / "static" / "sample_garden.png"

app = FastAPI(title="TurfTruth")
if (Path(__file__).parent / "static").exists():
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return typed ErrorResponse on Pydantic request validation errors."""
    first_msg = exc.errors()[0].get("msg", "Invalid request") if exc.errors() else "Invalid request"
    status = 400 if request.url.path.startswith("/api/") else 422
    return error_response(status, str(first_msg), "validation_error")


def _extract_multipart_image(
    body: bytes, content_type: str
) -> tuple[bytes | None, str, str | None, bool]:
    """Parse multipart/form-data body using stdlib email.parser without python-multipart."""
    if not body:
        return None, "image/png", None, False
    header = b"Content-Type: " + content_type.encode("latin-1", errors="ignore") + b"\r\nMIME-Version: 1.0\r\n\r\n"
    msg = BytesParser(policy=default_policy).parsebytes(header + body)
    if not msg.is_multipart():
        return None, "image/png", None, False
    use_sample = False
    for part in msg.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        part_bytes = payload if isinstance(payload, bytes) else b""
        if filename is not None or field_name in ("image", "file", "photo"):
            return part_bytes, part.get_content_type() or "image/png", filename, False
        if field_name == "use_sample" and part_bytes.decode("utf-8", errors="ignore").strip().lower() in ("1", "true", "yes"):
            use_sample = True
    return None, "image/png", None, use_sample


@app.post("/api/analyse", response_model=ai.AnalysisResult)
async def api_analyse(request: Request) -> ai.AnalysisResult | JSONResponse:
    """Analyse an uploaded garden image or sample garden photo."""
    content_type = request.headers.get("content-type", "")
    body = await request.body()
    if len(body) > MAX_UPLOAD_BYTES + 65536:
        return error_response(400, "Uploaded file exceeds the 10 MB limit.", "file_too_large")

    image_bytes: bytes | None = None
    mime_type = "image/png"
    filename: str | None = None

    if "multipart/form-data" in content_type:
        image_bytes, mime_type, filename, use_sample = _extract_multipart_image(body, content_type)
        if use_sample and not image_bytes and SAMPLE_IMAGE_PATH.exists():
            image_bytes, filename = SAMPLE_IMAGE_PATH.read_bytes(), "sample_garden.png"
    elif "application/json" in content_type and body:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return error_response(400, "Invalid JSON payload.", "invalid_request")
        if isinstance(data, dict):
            filename = data.get("filename")
            if data.get("use_sample") and SAMPLE_IMAGE_PATH.exists():
                image_bytes, filename = SAMPLE_IMAGE_PATH.read_bytes(), filename or "sample_garden.png"
            elif isinstance(data.get("image_base64"), str) and data["image_base64"].strip():
                b64 = data["image_base64"].strip().split(",", 1)[-1]
                try:
                    image_bytes = base64.b64decode(b64, validate=False)
                except (binascii.Error, ValueError):
                    return error_response(400, "Invalid base64 image data.", "invalid_image")

    if not image_bytes:
        return error_response(400, "Please select a garden photo before analysing.", "no_file")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        return error_response(400, "Uploaded file exceeds the 10 MB limit.", "file_too_large")
    if not ai.is_valid_image_bytes(image_bytes):
        return error_response(400, "File is not a supported image format (PNG, JPEG, WebP).", "invalid_image")

    try:
        result = ai.analyse_image(image_bytes, mime_type=mime_type, filename=filename)
        return ai.AnalysisResult.model_validate(dict(result))
    except (ai.AITimeoutError, TimeoutError) as exc:
        return error_response(504, str(exc) or "AI analysis timed out.", "ai_timeout")
    except (ai.AISchemaError, ValidationError) as exc:
        return error_response(502, str(exc) or "AI schema validation failed.", "schema_failure")
    except ai.InvalidImageError as exc:
        return error_response(400, str(exc), "invalid_image")
    except Exception as exc:
        if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
            return error_response(504, str(exc), "ai_timeout")
        return error_response(502, str(exc) or "AI service error.", "ai_error")


@app.get("/api/calendar", response_model=ApiCalendarResponse)
def api_calendar() -> ApiCalendarResponse:
    """Return the seeded week schedule and working hours."""
    return ApiCalendarResponse.model_validate(store.get_api_calendar())


@app.post("/api/book", response_model=ApiBookResponse)
async def api_book(request: Request) -> ApiBookResponse | JSONResponse:
    """Book the earliest contiguous weather-safe slot for the requested hours."""
    try:
        payload: Any = await request.json()
    except Exception:
        return error_response(400, "Invalid JSON request body.", "invalid_hours")
    if not isinstance(payload, dict):
        return error_response(400, "Request body must be a JSON object.", "invalid_hours")

    hours = payload.get("hours")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not math.isfinite(hours) or hours <= 0 or hours > 40:
        return error_response(400, "Hours must be a finite number greater than 0 and at most 40.", "invalid_hours")

    cal = store.get_api_calendar()
    slot = scheduler.find_next_slot(float(hours), cal["week"], cal["working_hours"])
    if slot is None:
        _, reason = scheduler.find_next_slot_with_reason(float(hours), cal["week"], cal["working_hours"])
        return ApiBookResponse(slot=None, message=reason)

    title = str(payload.get("title") or "Booked Garden Job")
    _, day_label = store.record_api_booking(slot["date"], slot["start"], slot["end"], title=title)
    return ApiBookResponse(
        slot=ApiBookedSlot(date=slot["date"], start=slot["start"], end=slot["end"]),
        message=f"Booked for {day_label}, {slot['start']}–{slot['end']}.",
    )


app.include_router(pages.router)
app.include_router(quote.router)
app.include_router(booking.router)
