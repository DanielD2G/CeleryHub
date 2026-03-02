"""Fixtures for CeleryHub integration tests.

Docker Compose lifecycle is managed by `make test-integration`.
These fixtures only wait for services to become healthy.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, AsyncGenerator

import httpx
import pytest
import pytest_asyncio

_BASE_URL = "http://localhost:3099"
AUTH_TOKEN = "test-token-123"
AUTH_HEADERS: dict[str, str] = {"Authorization": f"Bearer {AUTH_TOKEN}"}
_HEALTH_TIMEOUT = 90
_HEALTH_INTERVAL = 2


# ---------------------------------------------------------------------------
# Wait for services
# ---------------------------------------------------------------------------


def _wait_for_healthy(url: str, timeout: int = _HEALTH_TIMEOUT) -> None:
    """Poll the health endpoint until it returns healthy."""
    deadline = time.monotonic() + timeout
    last_error: str = ""
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/health", timeout=5)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "healthy":
                    return
                last_error = f"status={body.get('status')}"
            else:
                last_error = f"http {resp.status_code}"
        except httpx.ConnectError:
            last_error = "connection refused"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(_HEALTH_INTERVAL)
    raise TimeoutError(
        f"CeleryHub not healthy after {timeout}s — last: {last_error}"
    )


def _wait_for_worker(
    client: httpx.Client,
    timeout: int = 60,
) -> None:
    """Poll until at least one worker is visible with registered tasks."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = client.get("/api/tasks/registered")
            if resp.status_code == 200:
                data = resp.json()
                tasks: list[str] = data.get("tasks", [])
                if "integration.add" in tasks:
                    return
        except Exception:
            pass
        time.sleep(_HEALTH_INTERVAL)
    raise TimeoutError(f"Worker not visible after {timeout}s")


@pytest.fixture(scope="session", autouse=True)
def _wait_for_services() -> None:
    """Block until CeleryHub + worker are ready (compose managed externally)."""
    _wait_for_healthy(_BASE_URL)
    with httpx.Client(base_url=_BASE_URL, timeout=10) as client:
        _wait_for_worker(client)


# ---------------------------------------------------------------------------
# HTTP clients
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url() -> str:
    return _BASE_URL


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client with auth header pre-configured."""
    async with httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
        timeout=30,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    """Generate a short unique id for step IDs."""
    return uuid.uuid4().hex[:8]


def simple_workflow(
    name: str = "test-wf",
    task: str = "integration.add",
    args: str = "[2, 3]",
) -> dict[str, Any]:
    """Return a minimal workflow payload with one step."""
    return {
        "name": name,
        "steps": [
            {
                "id": f"step-{_uid()}",
                "label": "Step A",
                "taskNames": [task],
                "args": args,
            }
        ],
    }


@pytest_asyncio.fixture
async def anon_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client without auth header."""
    async with httpx.AsyncClient(
        base_url=_BASE_URL,
        timeout=30,
    ) as client:
        yield client
