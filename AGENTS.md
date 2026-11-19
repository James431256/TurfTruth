# Project: TurfTruth

Analyses client garden photos into itemised labour quotes, lets gardeners adjust hours, and books the job into their next free weather-safe slot in one click.

## Stack

- Python 3.14 managed with `uv`, FastAPI, and Jinja2 templates (vanilla JS only, no frontend build step).
- In-memory Python state in `store.py` only—no database, no ORM, and no cross-session persistence.
- `google-genai` SDK for garden photo analysis with Pydantic `response_schema` structured outputs.

## Conventions

- Keep every Python file under 200 lines; split into `routes/`, `services/`, `store.py`, and `models.py` when larger.
- Store seeded calendar/weather data and active session quotes in a single `store.py` module in memory; do not add a database.
- Gemini's Pydantic `response_schema` must only output task names, estimated hours, and visual evidence—never prices or totals; all £ calculations must happen in Python code.
- Route handlers return typed Pydantic models or HTML responses—never bare strings or raw `dict`s on errors; use the shared `routes/errors.py` `error_response` helper instead of duplicating error builders across route modules.
- Keep all quote state and totals (including task `enabled` toggles, `Decimal` £ amounts, and bookable hours) backend-authoritative: UI `fetch` handlers must send toggle/hour changes to the backend, use backend-returned totals for display and booking, and surface non-OK or network errors rather than swallowing them.
- Every route and service function has a `pytest` test in `tests/`; mock `google-genai` calls in tests (no live API calls).
- No new dependency in `pyproject.toml` without a one-line justification in the commit message.

## Definition of done

- `uv run pytest` exits 0 with all tests passing.
- `uv run uvicorn main:app --port 8080` starts cleanly and `GET /health` returns HTTP 200.
- Do not report a task complete until both commands succeed after your final edit.

## Engineering rules

- Gemini estimates work only; all money is in integer pence, in pricing.py and one mirrored JS function.
- Every Gemini response is validated by the Pydantic schema and sanitised server-side.
- The app runs with no API key via DEMO_MODE using recorded fixtures.
- Pricing and scheduling are pure functions with unit tests.
- Each acceptance criterion has a named e2e test (test_c1 ... test_c5).
- No new dependencies without an entry in DECISIONS.md. No features beyond the brief.
- A task is complete only when ruff and pytest pass.

