UV_PYTHON ?= 3.14
PORT ?= 8080

.PHONY: install run test e2e evals lint

install:
	UV_PYTHON=3.14 uv sync

run:
	DEMO_MODE=1 UV_PYTHON=3.14 uv run uvicorn main:app --host 0.0.0.0 --port $(PORT)

test:
	DEMO_MODE=1 UV_PYTHON=3.14 uv run pytest --ignore=tests/e2e

e2e:
	DEMO_MODE=1 UV_PYTHON=3.14 uv run pytest tests/e2e

evals:
	UV_PYTHON=3.14 uv run python evals/run_evals.py

lint:
	UV_PYTHON=3.14 uv run ruff check .
