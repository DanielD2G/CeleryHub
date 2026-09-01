from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSpaCatchAll:
    async def test_unknown_api_route_is_json_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/definitely/not/a/route")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"detail": "Not found"}


@pytest.mark.asyncio
class TestSendTaskValidation:
    async def test_malformed_args_is_400(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "t", "args": "not json", "kwargs": "{}"},
        )
        # model-level validation returns 422; the router guard is defense
        assert resp.status_code in (400, 422)

    async def test_wrong_shapes_are_400(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "t", "args": "{}", "kwargs": "[]"},
        )
        assert resp.status_code in (400, 422)


@pytest.mark.asyncio
class TestControlRouter:
    async def test_purge_calls_celery(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        mock_celery_app.control.purge.return_value = 7
        with patch("celery_gateway.routers.control.celery_app", mock_celery_app):
            resp = await client.post("/api/control/purge")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["responses"] == {"purged": 7}

    async def test_pool_grow(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        mock_celery_app.control.pool_grow.return_value = [{"celery@a": {"ok": "pool will grow"}}]
        with patch("celery_gateway.routers.control.celery_app", mock_celery_app):
            resp = await client.post("/api/control/pool-grow", json={"n": 1})
        assert resp.status_code == 200
