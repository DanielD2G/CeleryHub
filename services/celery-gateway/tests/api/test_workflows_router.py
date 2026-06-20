from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


def _make_node(
    label: str = "Node 1",
    task_name: str = "tasks.add",
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "label": label,
        "taskName": task_name,
    }


async def _create_interval_workflow(
    client: AsyncClient,
    name: str = "test-workflow",
    nodes: list[dict[str, Any]] | None = None,
    interval_seconds: int = 60,
) -> dict[str, Any]:
    resp = await client.post(
        "/api/workflows",
        json={
            "name": name,
            "scheduleType": "interval",
            "intervalSeconds": interval_seconds,
            "nodes": nodes or [_make_node()],
        },
    )
    return resp.json()


async def _create_cron_workflow(
    client: AsyncClient,
    name: str = "cron-workflow",
    cron_expression: str = "*/5 * * * *",
) -> dict[str, Any]:
    resp = await client.post(
        "/api/workflows",
        json={
            "name": name,
            "scheduleType": "cron",
            "cronExpression": cron_expression,
            "nodes": [_make_node()],
        },
    )
    return resp.json()


async def _create_unscheduled_workflow(
    client: AsyncClient,
    name: str = "manual-workflow",
    nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resp = await client.post(
        "/api/workflows",
        json={
            "name": name,
            "nodes": nodes or [_make_node()],
        },
    )
    return resp.json()


class TestCreateWorkflow:
    async def test_create_interval(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "my-interval",
                "scheduleType": "interval",
                "intervalSeconds": 60,
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data

    async def test_create_cron(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "my-cron",
                "scheduleType": "cron",
                "cronExpression": "*/5 * * * *",
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_unscheduled(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "manual",
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_without_name(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "",
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 422

    async def test_create_empty_nodes(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "nodes": [],
            },
        )
        assert resp.status_code == 422

    async def test_create_invalid_schedule_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "scheduleType": "weekly",
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 422

    async def test_create_interval_without_seconds(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "scheduleType": "interval",
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 400

    async def test_create_cron_without_expression(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "scheduleType": "cron",
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 400

    async def test_create_cron_invalid_expression(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "scheduleType": "cron",
                "cronExpression": "invalid",
                "nodes": [_make_node()],
            },
        )
        assert resp.status_code == 400

    async def test_create_with_node_invalid_args_json(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "nodes": [
                    {
                        "id": str(uuid.uuid4()),
                        "label": "Node 1",
                        "taskName": "tasks.add",
                        "args": "not valid json",
                    }
                ],
            },
        )
        assert resp.status_code == 422

    async def test_create_multi_node_dag(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "dag-workflow",
                "nodes": [
                    {"id": "n1", "label": "Extract", "taskName": "tasks.extract"},
                    {
                        "id": "n2",
                        "label": "Transform",
                        "taskName": "tasks.transform",
                        "dependsOn": ["n1"],
                    },
                    {
                        "id": "n3",
                        "label": "Load",
                        "taskName": "tasks.load",
                        "dependsOn": ["n2"],
                    },
                ],
            },
        )
        assert resp.status_code == 201

    async def test_create_with_node_dependency(self, client: AsyncClient) -> None:
        payload = {
            "name": "wf",
            "nodes": [
                {"id": "a", "label": "A", "taskName": "tasks.a"},
                {"id": "b", "label": "B", "taskName": "tasks.b", "dependsOn": ["a"]},
            ],
        }
        resp = await client.post("/api/workflows", json=payload)
        assert resp.status_code == 201

    async def test_create_cycle_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "cycle",
                "nodes": [
                    {
                        "id": "n1",
                        "label": "A",
                        "taskName": "a",
                        "dependsOn": ["n2"],
                    },
                    {
                        "id": "n2",
                        "label": "B",
                        "taskName": "b",
                        "dependsOn": ["n1"],
                    },
                ],
            },
        )
        assert resp.status_code == 400

    async def test_create_self_dep_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "self-dep",
                "nodes": [
                    {
                        "id": "n1",
                        "label": "A",
                        "taskName": "a",
                        "dependsOn": ["n1"],
                    }
                ],
            },
        )
        assert resp.status_code == 400

    async def test_create_unknown_dep_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "unknown-dep",
                "nodes": [
                    {
                        "id": "n1",
                        "label": "A",
                        "taskName": "a",
                        "dependsOn": ["does-not-exist"],
                    }
                ],
            },
        )
        assert resp.status_code == 400


class TestListWorkflows:
    async def test_list_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/workflows")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_data(self, client: AsyncClient) -> None:
        await _create_unscheduled_workflow(client, name="wf-1")
        await _create_unscheduled_workflow(client, name="wf-2")

        resp = await client.get("/api/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


class TestGetWorkflow:
    async def test_get_existing(self, client: AsyncClient) -> None:
        created = await _create_interval_workflow(client)
        wf_id: str = created["id"]

        resp = await client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == wf_id
        assert data["name"] == "test-workflow"
        assert "scheduleType" in data
        assert "intervalSeconds" in data
        assert "nodes" in data
        assert len(data["nodes"]) == 1

    async def test_get_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.get("/api/workflows/nonexistent-id")
        assert resp.status_code == 404


class TestUpdateWorkflow:
    async def test_update_name(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        resp = await client.put(
            f"/api/workflows/{wf_id}",
            json={"name": "updated-name"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        get_resp = await client.get(f"/api/workflows/{wf_id}")
        assert get_resp.json()["name"] == "updated-name"

    async def test_update_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/workflows/nonexistent-id",
            json={"name": "x"},
        )
        assert resp.status_code == 404


class TestDeleteWorkflow:
    async def test_delete(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        resp = await client.delete(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        get_resp = await client.get(f"/api/workflows/{wf_id}")
        assert get_resp.status_code == 404

    async def test_delete_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/workflows/nonexistent-id")
        assert resp.status_code == 404


class TestToggleWorkflow:
    async def test_toggle_on_to_off(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        resp = await client.post(f"/api/workflows/{wf_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_toggle_off_to_on(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        await client.post(f"/api/workflows/{wf_id}/toggle")
        resp = await client.post(f"/api/workflows/{wf_id}/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    async def test_toggle_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.post("/api/workflows/nonexistent-id/toggle")
        assert resp.status_code == 404


class TestDuplicateWorkflow:
    async def test_duplicate(self, client: AsyncClient) -> None:
        created = await _create_interval_workflow(client, name="original")
        wf_id: str = created["id"]

        resp = await client.post(f"/api/workflows/{wf_id}/duplicate")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["id"] != wf_id

        get_resp = await client.get(f"/api/workflows/{data['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "original (Copy)"
        assert get_resp.json()["enabled"] is False

    async def test_duplicate_with_custom_name(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        resp = await client.post(
            f"/api/workflows/{wf_id}/duplicate",
            json={"name": "custom-copy"},
        )
        assert resp.status_code == 201

        get_resp = await client.get(f"/api/workflows/{resp.json()['id']}")
        assert get_resp.json()["name"] == "custom-copy"

    async def test_duplicate_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.post("/api/workflows/nonexistent-id/duplicate")
        assert resp.status_code == 404


class TestRunNow:
    async def test_run_now(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="dispatched-task-id",
        ):
            resp = await client.post(f"/api/workflows/{wf_id}/run-now")

        assert resp.status_code == 201
        data = resp.json()
        assert "runId" in data

    async def test_run_now_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.post("/api/workflows/nonexistent-id/run-now")
        assert resp.status_code == 404


class TestGetRuns:
    async def test_get_runs_empty(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        resp = await client.get(f"/api/workflows/{wf_id}/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_runs_after_run_now(self, client: AsyncClient) -> None:
        created = await _create_unscheduled_workflow(client)
        wf_id: str = created["id"]

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new_callable=AsyncMock,
            return_value="dispatched-task-id",
        ):
            await client.post(f"/api/workflows/{wf_id}/run-now")

        resp = await client.get(f"/api/workflows/{wf_id}/runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) >= 1
        assert runs[0]["status"] in ("running", "succeeded", "failed")
