"""HTML page and health check routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import ai
import store
from models import HealthResponse

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check endpoint."""
    return HealthResponse(
        status="ok",
        mode=ai.get_mode(),
        prompt_version=ai.PROMPT_VERSION,
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Render the TurfTruth quote review & hour-adjustment view."""
    quotes = store.list_quotes()
    active_quote = quotes[0] if quotes else None
    return templates.TemplateResponse(
        request,
        "index.html",
        {"quote": active_quote},
    )
