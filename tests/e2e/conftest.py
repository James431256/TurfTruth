"""Pytest fixtures for TurfTruth E2E tests against a live DEMO_MODE server."""

import os
import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn

import main
import store
from tests.e2e.cdp_driver import CDPPage


@pytest.fixture(scope="session")
def live_server_url() -> Iterator[str]:
    """Start uvicorn main:app on a free localhost port with DEMO_MODE=1."""
    os.environ["DEMO_MODE"] = "1"
    os.environ["HOURLY_RATE_PENCE"] = "2500"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(f"{base_url}/health", timeout=0.5).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)

    yield base_url
    server.should_exit = True


@pytest.fixture()
def page(live_server_url: str) -> Iterator[CDPPage]:
    """Provide a fresh headless Chrome page with reset store state for each E2E test."""
    os.environ["DEMO_MODE"] = "1"
    os.environ["HOURLY_RATE_PENCE"] = "2500"
    store.reset_store()
    browser_page = CDPPage()
    yield browser_page
    browser_page.close()
