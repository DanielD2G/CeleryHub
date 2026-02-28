from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


class TestHealth:
    async def test_broker_ok(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        with patch("celery_gateway.main.celery_app", mock_celery_app):
            resp = await client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["broker_connected"] is True
        assert data["workers_reachable"] == 1

    async def test_broker_error(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        mock_celery_app.control.inspect.return_value.ping.side_effect = RuntimeError(
            "connection refused"
        )

        with patch("celery_gateway.main.celery_app", mock_celery_app):
            resp = await client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["broker_connected"] is False
        assert data["workers_reachable"] == 0

    async def test_version(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        with patch("celery_gateway.main.celery_app", mock_celery_app):
            resp = await client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["version"] == "0.1.0"
