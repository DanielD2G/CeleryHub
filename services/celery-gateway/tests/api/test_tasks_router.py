from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


class TestActiveTasks:
    async def test_active_tasks(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        mock_celery_cache.get = AsyncMock(
            side_effect=lambda key: [
                {"taskId": "t1", "name": "add", "worker": "w1", "startedAt": 123.0, "status": "started"}
            ]
            if key == "active-tasks"
            else []
        )
        resp = await client.get("/api/tasks/active")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_active_tasks_empty(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        resp = await client.get("/api/tasks/active")
        assert resp.status_code == 200
        assert resp.json() == []


class TestTaskHistory:
    async def test_history_default(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        resp = await client.get("/api/tasks/history")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_history_with_limit(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        items = [
            {"taskId": f"t{i}", "name": "add", "status": "SUCCESS"}
            for i in range(10)
        ]

        async def _get(key: str) -> Any:
            if key == "task-history":
                return items
            return []

        mock_celery_cache.get = AsyncMock(side_effect=_get)
        resp = await client.get("/api/tasks/history?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 5


class TestRegisteredTasks:
    async def test_registered(
        self, client: AsyncClient, mock_celery_cache: AsyncMock
    ) -> None:
        async def _get(key: str) -> Any:
            if key == "registered-tasks":
                return {"byWorker": {"w1": ["add", "mul"]}, "tasks": ["add", "mul"]}
            return None

        mock_celery_cache.get = AsyncMock(side_effect=_get)
        resp = await client.get("/api/tasks/registered")
        assert resp.status_code == 200
        data = resp.json()
        assert "byWorker" in data
        assert "tasks" in data


class TestPayloads:
    async def test_payloads_with_name(
        self, client: AsyncClient, fake_redis: Any
    ) -> None:
        import json

        payload = {"args": "[1]", "kwargs": "{}", "queue": "celery", "timestamp": 1.0}
        await fake_redis.lpush("celeryhub:payloads:tasks.add", json.dumps(payload))

        resp = await client.get("/api/tasks/payloads?name=tasks.add")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_payloads_without_name(self, client: AsyncClient) -> None:
        resp = await client.get("/api/tasks/payloads")
        assert resp.status_code == 422  # FastAPI Query validation


class TestSendTask:
    async def test_send_valid(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.id = "new-task-id"
        mock_celery_app.send_task.return_value = mock_result

        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "tasks.add", "args": "[1, 2]", "kwargs": "{}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "taskId" in data

    async def test_send_without_task_name(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": ""},
        )
        assert resp.status_code == 400
        assert "Task name is required" in resp.json()["error"]

    async def test_send_invalid_task_name(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "invalid task!@#"},
        )
        assert resp.status_code == 400
        assert "Invalid task name" in resp.json()["error"]

    async def test_send_args_not_array(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "tasks.add", "args": '{"not": "array"}'},
        )
        assert resp.status_code == 400
        assert "array" in resp.json()["error"].lower()

    async def test_send_kwargs_not_object(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "tasks.add", "kwargs": "[1, 2]"},
        )
        assert resp.status_code == 400
        assert "object" in resp.json()["error"].lower()

    async def test_send_invalid_args_json(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "tasks.add", "args": "not json"},
        )
        assert resp.status_code == 400

    async def test_send_fallback_to_redis(
        self, client: AsyncClient, mock_celery_app: MagicMock, fake_redis: Any
    ) -> None:
        mock_celery_app.send_task.side_effect = RuntimeError("broker down")

        resp = await client.post(
            "/api/tasks/send",
            json={"taskName": "tasks.add"},
        )
        assert resp.status_code == 200
        assert "taskId" in resp.json()


class TestRevokeTask:
    async def test_revoke(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        resp = await client.post("/api/tasks/test-task-id/revoke")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "test-task-id"
        assert data["revoked"] is True

    async def test_revoke_with_terminate(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        resp = await client.post(
            "/api/tasks/test-task-id/revoke",
            json={"terminate": True, "signal": "SIGKILL"},
        )
        assert resp.status_code == 200
        assert resp.json()["revoked"] is True


class TestTaskStatus:
    async def test_status_existing(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.status = "SUCCESS"
        mock_result.result = 42
        mock_result.backend = MagicMock()
        mock_result.backend.get_task_meta.return_value = {
            "status": "SUCCESS",
            "result": 42,
        }

        with patch(
            "celery_gateway.routers.tasks.AsyncResult",
            return_value=mock_result,
        ):
            resp = await client.get("/api/tasks/test-task-id/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["result"] == 42

    async def test_status_pending(
        self, client: AsyncClient, mock_celery_app: MagicMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.status = "PENDING"
        mock_result.result = None
        mock_result.backend = MagicMock()
        mock_result.backend.get_task_meta.return_value = {"status": "PENDING"}

        with patch(
            "celery_gateway.routers.tasks.AsyncResult",
            return_value=mock_result,
        ):
            resp = await client.get("/api/tasks/test-task-id/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PENDING"
        assert data["result"] is None

    async def test_status_fallback_to_redis(
        self, client: AsyncClient, mock_celery_app: MagicMock, fake_redis: Any
    ) -> None:
        import json

        # Make AsyncResult fail
        with patch(
            "celery_gateway.routers.tasks.AsyncResult",
            side_effect=RuntimeError("no backend"),
        ):
            # Set up Redis fallback data
            await fake_redis.set(
                "celery-task-meta-test-task-id",
                json.dumps({"task_id": "test-task-id", "status": "SUCCESS", "result": 99}),
            )

            resp = await client.get("/api/tasks/test-task-id/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"

    async def test_status_not_found(
        self, client: AsyncClient, mock_celery_app: MagicMock, fake_redis: Any
    ) -> None:
        with patch(
            "celery_gateway.routers.tasks.AsyncResult",
            side_effect=RuntimeError("no backend"),
        ):
            resp = await client.get("/api/tasks/nonexistent-id/status")

        assert resp.status_code == 200
        assert resp.json() is None
