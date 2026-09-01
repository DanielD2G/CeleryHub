from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


def _make_step(
    label: str = "Step 1",
    task_names: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "label": label,
        "taskNames": task_names or ["tasks.add"],
    }


async def _create_interval_workflow(
    client: AsyncClient,
    name: str = "test-workflow",
    steps: list[dict[str, Any]] | None = None,
    interval_seconds: int = 60,
) -> dict[str, Any]:
    resp = await client.post(
        "/api/workflows",
        json={
            "name": name,
            "scheduleType": "interval",
            "intervalSeconds": interval_seconds,
            "steps": steps or [_make_step()],
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
            "steps": [_make_step()],
        },
    )
    return resp.json()


async def _create_unscheduled_workflow(
    client: AsyncClient,
    name: str = "manual-workflow",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resp = await client.post(
        "/api/workflows",
        json={
            "name": name,
            "steps": steps or [_make_step()],
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
                "steps": [_make_step()],
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
                "steps": [_make_step()],
            },
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_unscheduled(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "manual",
                "steps": [_make_step()],
            },
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_without_name(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "",
                "steps": [_make_step()],
            },
        )
        assert resp.status_code == 422

    async def test_create_empty_steps(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "steps": [],
            },
        )
        assert resp.status_code == 422

    async def test_create_invalid_schedule_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "scheduleType": "weekly",
                "steps": [_make_step()],
            },
        )
        assert resp.status_code == 422

    async def test_create_interval_without_seconds(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "scheduleType": "interval",
                "steps": [_make_step()],
            },
        )
        assert resp.status_code == 400

    async def test_create_cron_without_expression(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "scheduleType": "cron",
                "steps": [_make_step()],
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
                "steps": [_make_step()],
            },
        )
        assert resp.status_code == 400

    async def test_create_with_step_invalid_args_json(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "test",
                "steps": [
                    {
                        "id": str(uuid.uuid4()),
                        "label": "Step 1",
                        "taskNames": ["tasks.add"],
                        "args": "not valid json",
                    }
                ],
            },
        )
        assert resp.status_code == 422

    async def test_create_multi_step_dag(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "dag-workflow",
                "steps": [
                    {"id": "s1", "label": "Extract", "taskNames": ["tasks.extract"]},
                    {
                        "id": "s2",
                        "label": "Transform",
                        "taskNames": ["tasks.transform"],
                        "dependsOn": ["s1"],
                    },
                    {
                        "id": "s3",
                        "label": "Load",
                        "taskNames": ["tasks.load"],
                        "dependsOn": ["s2"],
                    },
                ],
            },
        )
        assert resp.status_code == 201

    async def test_create_cycle_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/workflows",
            json={
                "name": "cycle",
                "steps": [
                    {
                        "id": "s1",
                        "label": "A",
                        "taskNames": ["a"],
                        "dependsOn": ["s2"],
                    },
                    {
                        "id": "s2",
                        "label": "B",
                        "taskNames": ["b"],
                        "dependsOn": ["s1"],
                    },
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
        assert "steps" in data
        assert len(data["steps"]) == 1

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


class TestRunDurations:
    async def test_empty_when_no_runs(self, client: AsyncClient) -> None:
        wf = await _create_interval_workflow(client, name="durations-empty")
        resp = await client.get(f"/api/workflows/{wf['id']}/run-durations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["workflowId"] == wf["id"]
        assert body["items"] == []

    async def test_durations_with_finished_run(
        self, client: AsyncClient, db_session
    ) -> None:
        from datetime import datetime, timedelta, timezone

        from celery_gateway.db.models import StepRun, WorkflowRun

        wf = await _create_interval_workflow(client, name="durations-run")
        t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
        run = WorkflowRun(
            id="run-dur-1", workflow_id=wf["id"], status="succeeded",
            trigger="manual", started_at=t0,
            finished_at=t0 + timedelta(seconds=90),
        )
        db_session.add(run)
        db_session.add(StepRun(
            id="sr-dur-1", workflow_run_id="run-dur-1", step_id="s1",
            step_label="Only Step", status="succeeded",
            started_at=t0, finished_at=t0 + timedelta(seconds=90),
        ))
        await db_session.commit()

        resp = await client.get(f"/api/workflows/{wf['id']}/run-durations")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["durationSeconds"] == pytest.approx(90.0)
        assert item["steps"][0]["stepLabel"] == "Only Step"
        assert item["steps"][0]["durationSeconds"] == pytest.approx(90.0)

    async def test_running_run_has_null_duration(
        self, client: AsyncClient, db_session
    ) -> None:
        from datetime import datetime, timezone

        from celery_gateway.db.models import WorkflowRun

        wf = await _create_interval_workflow(client, name="durations-running")
        db_session.add(WorkflowRun(
            id="run-dur-2", workflow_id=wf["id"], status="running",
            trigger="scheduled", started_at=datetime.now(timezone.utc),
        ))
        await db_session.commit()

        resp = await client.get(f"/api/workflows/{wf['id']}/run-durations")
        items = resp.json()["items"]
        assert items[0]["durationSeconds"] is None
