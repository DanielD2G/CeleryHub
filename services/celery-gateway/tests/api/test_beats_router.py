from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _create_interval_beat(
    client: AsyncClient,
    name: str = "test-beat",
    task_names: list[str] | None = None,
    interval_seconds: int = 60,
) -> dict[str, Any]:
    resp = await client.post(
        "/api/beats/",
        json={
            "name": name,
            "taskNames": task_names or ["tasks.add"],
            "scheduleType": "interval",
            "intervalSeconds": interval_seconds,
        },
    )
    return resp.json()


async def _create_cron_beat(
    client: AsyncClient,
    name: str = "cron-beat",
    cron_expression: str = "*/5 * * * *",
) -> dict[str, Any]:
    resp = await client.post(
        "/api/beats/",
        json={
            "name": name,
            "taskNames": ["tasks.add"],
            "scheduleType": "cron",
            "cronExpression": cron_expression,
        },
    )
    return resp.json()


class TestCreateBeat:
    async def test_create_interval(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "my-interval",
                "taskNames": ["tasks.add"],
                "scheduleType": "interval",
                "intervalSeconds": 60,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data

    async def test_create_cron(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "my-cron",
                "taskNames": ["tasks.add"],
                "scheduleType": "cron",
                "cronExpression": "*/5 * * * *",
            },
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_without_name(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "",
                "taskNames": ["tasks.add"],
                "scheduleType": "interval",
                "intervalSeconds": 60,
            },
        )
        assert resp.status_code == 400
        assert "Name is required" in resp.json()["error"]

    async def test_create_empty_task_names(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "test",
                "taskNames": [],
                "scheduleType": "interval",
                "intervalSeconds": 60,
            },
        )
        assert resp.status_code == 400
        assert "task" in resp.json()["error"].lower()

    async def test_create_invalid_schedule_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "test",
                "taskNames": ["tasks.add"],
                "scheduleType": "weekly",
            },
        )
        assert resp.status_code == 400
        assert "Schedule type" in resp.json()["error"]

    async def test_create_interval_without_seconds(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "test",
                "taskNames": ["tasks.add"],
                "scheduleType": "interval",
            },
        )
        assert resp.status_code == 400
        assert "Interval" in resp.json()["error"]

    async def test_create_cron_without_expression(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "test",
                "taskNames": ["tasks.add"],
                "scheduleType": "cron",
            },
        )
        assert resp.status_code == 400
        assert "Cron expression" in resp.json()["error"]

    async def test_create_cron_invalid_expression(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "test",
                "taskNames": ["tasks.add"],
                "scheduleType": "cron",
                "cronExpression": "invalid",
            },
        )
        assert resp.status_code == 400
        assert "Invalid cron" in resp.json()["error"]

    async def test_create_invalid_args_json(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/beats/",
            json={
                "name": "test",
                "taskNames": ["tasks.add"],
                "scheduleType": "interval",
                "intervalSeconds": 60,
                "args": "not valid json",
            },
        )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["error"]


class TestListBeats:
    async def test_list_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/beats/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_data(self, client: AsyncClient) -> None:
        await _create_interval_beat(client, name="beat-1")
        await _create_interval_beat(client, name="beat-2")

        resp = await client.get("/api/beats/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


class TestGetBeat:
    async def test_get_existing(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        resp = await client.get(f"/api/beats/{beat_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == beat_id
        assert data["name"] == "test-beat"
        # Verify camelCase keys
        assert "scheduleType" in data
        assert "intervalSeconds" in data
        assert "taskNames" in data

    async def test_get_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.get("/api/beats/nonexistent-id")
        assert resp.status_code == 404


class TestUpdateBeat:
    async def test_update_name(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        resp = await client.put(
            f"/api/beats/{beat_id}",
            json={"name": "updated-name"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify
        get_resp = await client.get(f"/api/beats/{beat_id}")
        assert get_resp.json()["name"] == "updated-name"

    async def test_update_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/beats/nonexistent-id",
            json={"name": "x"},
        )
        assert resp.status_code == 404


class TestDeleteBeat:
    async def test_delete(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        resp = await client.delete(f"/api/beats/{beat_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify deleted
        get_resp = await client.get(f"/api/beats/{beat_id}")
        assert get_resp.status_code == 404


class TestToggleBeat:
    async def test_toggle_on_to_off(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        resp = await client.post(f"/api/beats/{beat_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_toggle_off_to_on(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        # Toggle off
        await client.post(f"/api/beats/{beat_id}/toggle")
        # Toggle on
        resp = await client.post(f"/api/beats/{beat_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    async def test_toggle_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.post("/api/beats/nonexistent-id/toggle")
        assert resp.status_code == 404


class TestRunNow:
    async def test_run_now(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        with patch(
            "celery_gateway.routers.beats.dispatch_task",
            new_callable=AsyncMock,
            return_value="dispatched-task-id",
        ):
            resp = await client.post(f"/api/beats/{beat_id}/run-now")

        assert resp.status_code == 200
        data = resp.json()
        assert "taskIds" in data
        assert len(data["taskIds"]) == 1

    async def test_run_now_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.post("/api/beats/nonexistent-id/run-now")
        assert resp.status_code == 404


class TestGetRuns:
    async def test_get_runs_empty(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        resp = await client.get(f"/api/beats/{beat_id}/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_runs_after_run_now(self, client: AsyncClient) -> None:
        created = await _create_interval_beat(client)
        beat_id = created["id"]

        with patch(
            "celery_gateway.routers.beats.dispatch_task",
            new_callable=AsyncMock,
            return_value="dispatched-task-id",
        ):
            await client.post(f"/api/beats/{beat_id}/run-now")

        resp = await client.get(f"/api/beats/{beat_id}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 1
        assert runs[0]["taskId"] == "dispatched-task-id"
