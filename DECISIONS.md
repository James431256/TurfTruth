# Architecture Decision Records (`DECISIONS.md`)

Concise architecture and dependency records for **TurfTruth**. Any new dependency in `pyproject.toml` or structural trade-off must be recorded here.

---

## ADR-001: FastAPI + Python 3.14 (`uv`) Backend with In-Memory Store

- **Status:** Accepted
- **Context:** TurfTruth needs a fast, strictly typed HTTP API and HTML view server that validates image uploads, enforces structured schemas for AI outputs, and manages a single-gardener weekly schedule without operational database overhead.
- **Decision:** Build the backend on Python 3.14 managed via `uv`, using FastAPI (`fastapi`, `uvicorn`) and Pydantic v2 (`pydantic`) with in-memory session and calendar state in `store.py` (seeded from `data/mock_calendar.json`) and server-rendered Jinja2 templates (`jinja2`). Keep every Python module strictly under 200 lines.
- **Consequences:** Zero database setup, instant startup (`make run`), deterministic test isolation via store resets, and full request/response schema validation. State resets on process restart by design.

---

## ADR-002: Zero-Hallucination Pricing — Gemini Estimates Work Only, Code Calculates Money

- **Status:** Accepted
- **Context:** Vision LLMs are effective at identifying visible garden maintenance tasks and estimating approximate labour hours, but unreliable at arithmetic, currency formatting, and applying configurable hourly rates without hallucinating inconsistent line totals or grand totals.
- **Decision:** Restrict Gemini's Pydantic `response_schema` (`RawGardenAnalysis` / `RawTaskEstimate` in `ai.py`) to `is_garden: bool`, `name: str`, `hours: float`, and `evidence: str`. No price, rate, cost, or currency fields exist in the AI schema or prompt (`prompts/analyse_v1.txt`). All server-side outputs pass through `sanitise_analysis` (clamping hours to `[0.25, 40.0]` in `0.25h` increments, dropping empty tasks, capping at 12 tasks, and assigning stable IDs `t1..tN`).
- **Consequences:** The LLM can never invent a price, discount, or mismatched sum. Hourly rates (`HOURLY_RATE_PENCE`) can be changed via environment configuration without re-prompting or re-running vision analysis.

---

## ADR-003: Integer Pence Arithmetic (`pricing.py` + Mirrored JS Function)

- **Status:** Accepted
- **Context:** IEEE-754 binary floating-point arithmetic (`0.1 + 0.2`) introduces rounding drift between line items and quote totals, and between backend Python calculations and interactive browser recalculations.
- **Decision:** Represent all currency values as integer pence (`HOURLY_RATE_PENCE = 2500` for `£25.00/hr`). In Python (`pricing.py`), `line_cost_pence(hours, rate_pence)` uses `Decimal(str(hours)) * Decimal(int(rate_pence))` with `ROUND_HALF_UP` to the nearest penny, and `total_pence(tasks, rate_pence)` sums enabled line costs in integer pence. In the browser (`static/app.js`), a single mirrored function `lineCostPence(hours, ratePence)` and `totalPence(tasks, ratePence)` computes integer pence and formats `£XX.XX` at render time.
- **Consequences:** Line costs and quote totals always agree to the exact penny across Python unit tests, API responses, and live UI adjustments.

---

## ADR-004: Deterministic `DEMO_MODE` Through the Identical Schema & Sanitiser Pipeline

- **Status:** Accepted
- **Context:** Evaluators, CI pipelines, and developers need to run the application, unit/API tests, Playwright end-to-end tests, and offline evals without a live `GEMINI_API_KEY` or network flakiness, while still testing the real validation and sanitisation code paths.
- **Decision:** Enable `DEMO_MODE` automatically when `GEMINI_API_KEY` is unset/empty or when `DEMO_MODE=1`. In `DEMO_MODE`, `ai.analyse_image` selects recorded JSON fixtures (`fixtures/sample_garden.json` or `fixtures/not_a_garden.json` via SHA-256 / image inspection) and feeds the raw fixture payload through the exact same `RawGardenAnalysis.model_validate(...)` and `sanitise_analysis(...)` pipeline used for live `google-genai` responses.
- **Consequences:** One-command startup (`make run`) works out of the box with zero secrets, and offline tests exercise 100% of schema validation and sanitisation logic.

---

## ADR-005: Pure-Python Seeded Week Calendar & Weather-Safe Slot Scheduler (`scheduler.py`)

- **Status:** Accepted
- **Context:** Gardeners cannot mow lawns or cut hedges in heavy rain and need one-click booking into the earliest contiguous dry-day gap that fits the total ticked labour hours without clashing with existing jobs.
- **Decision:** Implement scheduling as a pure function `find_next_slot(duration_hours, week, working_hours)` in `scheduler.py` operating on the seeded week calendar (`data/mock_calendar.json`, `08:00–17:00`). The algorithm skips any day where `rain` is `true`, sorts existing bookings by start time, allows touching boundaries (`end == start`), and returns the earliest contiguous gap `>= duration_minutes` (or `None` with an explanatory message if the job exceeds a single working day or the week is full).
- **Consequences:** Scheduling is fast, deterministic, side-effect-free, and unit-testable across edge cases (rain days, back-to-back boundary slots, over-day durations, and full weeks).

---

## ADR-006: Vanilla JS Frontend with Zero Build Step and Strict `data-testid` Contract

- **Status:** Accepted
- **Context:** A single-page gardener workflow (upload/sample -> itemised table with live hours/tick adjustments -> weather-safe calendar booking -> copyable client quote message) does not warrant a bundler, Virtual DOM framework, or Node build pipeline.
- **Decision:** Serve semantic HTML from `templates/index.html` with static assets (`static/app.js`, `static/styles.css`, `static/logo.svg`, `static/sample_garden.png`). Enforce a strict 20-element `data-testid` contract (`CONTRACT.md`) across all interactive controls, table cells, calendar states, and error banners, while preserving existing DOM IDs and responsive layout down to `375px` mobile viewports.
- **Consequences:** Zero frontend build step, instant page loads, accessible keyboard/screen-reader semantics, and resilient Playwright e2e selectors (`test_c1` through `test_c5`).

---

## Dependency Log (`pyproject.toml` / `requirements*.txt`)

| Package | Scope | One-line Justification |
|---|---|---|
| `fastapi` | Runtime | HTTP API routing, request handling, and OpenAPI schema support. |
| `uvicorn` | Runtime | ASGI server for local development and e2e test fixtures. |
| `pydantic` | Runtime | Structured `response_schema` validation for Gemini and typed API models. |
| `jinja2` | Runtime | Server-side HTML rendering for `templates/index.html`. |
| `google-genai` | Runtime (optional in demo) | Official Google Gemini SDK for live garden photo vision analysis. |
| `httpx` | Dev / Test | Backing client for FastAPI `TestClient`. |
| `pytest` | Dev / Test | Unit, API, and Playwright end-to-end test runner. |
| `playwright` | Dev / Test | Headless Chromium browser automation for `test_c1..test_c5`. |
| `ruff` | Dev / Test | Fast Python linter and formatter check (`py314`, line-length 100). |
