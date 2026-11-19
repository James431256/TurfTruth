"""Shared typed JSON error response helper for route handlers."""

from fastapi.responses import JSONResponse

from models import ErrorDetail, ErrorResponse


def error_response(status_code: int, detail: str, code: str) -> JSONResponse:
    """Build a typed JSON error response."""
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=detail),
        detail=detail,
        code=code,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())
