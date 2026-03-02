from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


class TestQueuesRouter:
    async def test_queue_details(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        async def _get(key: str) -> Any:
            if key == "queue-details":
                return {
                    "queueNames": ["celery", "high"],
                    "depths": {"celery": 5, "high": 2},
                    "pending": {
                        "celery": [{"taskId": "t1", "taskName": "add"}],
                        "high": [],
                    },
                }
            return None

        mock_celery_cache.get = AsyncMock(side_effect=_get)
        resp = await client.get("/api/queues")
        assert resp.status_code == 200
        data = resp.json()
        assert "queueNames" in data
        assert "depths" in data
        assert "pending" in data

    async def test_camel_case_keys(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        resp = await client.get("/api/queues")
        assert resp.status_code == 200
        data = resp.json()
        assert "queueNames" in data
        assert "queue_names" not in data

    async def test_cache_empty_defaults(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        resp = await client.get("/api/queues")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["queueNames"], list)
        assert isinstance(data["depths"], dict)
        assert isinstance(data["pending"], dict)
