"""API integration tests for CeleryHub."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _poll_until(
    client: httpx.AsyncClient,
    url: str,
    predicate: Any,
    *,
    timeout: float = 30,
    interval: float = 1,
) -> Any:
    """Poll *url* until *predicate(json)* is truthy; return final json."""
    deadline = asyncio.get_event_loop().time() + timeout
    last: Any = None
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(url)
        if resp.status_code == 200:
            last = resp.json()
            if predicate(last):
                return last
        await asyncio.sleep(interval)
    raise TimeoutError(f"Predicate not met within {timeout}s — last: {last}")


def _uid() -> str:
    """Generate a short unique id for step IDs."""
    return uuid.uuid4().hex[:8]


def _simple_workflow(
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


# ===================================================================
# A. Health & Infrastructure
# ===================================================================


class TestHealthInfrastructure:
    async def test_health(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["broker_connected"] is True
        assert body["workers_reachable"] >= 1

    async def test_worker_inspect(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.get(
            "/api/workers/inspect", params={"methods": "registered"}
        )
        assert resp.status_code == 200
        data = resp.json()
        registered: dict[str, list[str]] = data.get("registered", {})
        assert len(registered) >= 1
        all_tasks: list[str] = [
            t for tasks in registered.values() for t in tasks
        ]
        for expected in (
            "integration.add",
            "integration.slow_task",
            "integration.fail_task",
        ):
            assert expected in all_tasks

    async def test_queues(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.get("/api/queues")
        assert resp.status_code == 200
        data = resp.json()
        assert "queueNames" in data


# ===================================================================
# B. Tasks
# ===================================================================


class TestTasks:
    async def test_registered_tasks(
        self, api_client: httpx.AsyncClient
    ) -> None:
        resp = await api_client.get("/api/tasks/registered")
        assert resp.status_code == 200
        tasks: list[str] = resp.json()["tasks"]
        for name in (
            "integration.add",
            "integration.slow_task",
            "integration.fail_task",
        ):
            assert name in tasks

    async def test_send_task(self, api_client: httpx.AsyncClient) -> None:
        resp = await api_client.post(
            "/api/tasks/send",
            json={
                "taskName": "integration.add",
                "args": "[2, 3]",
            },
        )
        assert resp.status_code == 200
        assert "taskId" in resp.json()

    async def test_task_in_history(
        self, api_client: httpx.AsyncClient
    ) -> None:
        # Send a task
        send_resp = await api_client.post(
            "/api/tasks/send",
            json={"taskName": "integration.add", "args": "[10, 20]"},
        )
        task_id: str = send_resp.json()["taskId"]

        # Poll history until the task shows up as SUCCESS
        def _has_task(data: list[dict[str, Any]]) -> bool:
            return any(
                item["taskId"] == task_id and item["status"] == "SUCCESS"
                for item in data
            )

        resp = await _poll_until(
            api_client,
            "/api/tasks/history",
            _has_task,
            timeout=30,
        )
        match = [item for item in resp if item["taskId"] == task_id]
        assert len(match) == 1
        assert match[0]["status"] == "SUCCESS"

    async def test_send_and_revoke(
        self, api_client: httpx.AsyncClient
    ) -> None:
        # Send a slow task
        send_resp = await api_client.post(
            "/api/tasks/send",
            json={"taskName": "integration.slow_task", "args": "[60]"},
        )
        task_id: str = send_resp.json()["taskId"]

        # Wait a moment for the task to be received
        await asyncio.sleep(2)

        # Revoke it
        revoke_resp = await api_client.post(
            f"/api/tasks/{task_id}/revoke",
            json={"terminate": True, "signal": "SIGTERM"},
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["revoked"] is True

    async def test_task_status(self, api_client: httpx.AsyncClient) -> None:
        send_resp = await api_client.post(
            "/api/tasks/send",
            json={"taskName": "integration.add", "args": "[1, 1]"},
        )
        task_id: str = send_resp.json()["taskId"]

        _terminal = {"SUCCESS", "FAILURE", "REVOKED", "RETRY"}

        async def _check() -> dict[str, Any]:
            deadline = asyncio.get_event_loop().time() + 30
            while asyncio.get_event_loop().time() < deadline:
                r = await api_client.get(f"/api/tasks/{task_id}/status")
                if r.status_code == 200:
                    data = r.json()
                    if data.get("status") in _terminal:
                        return data
                await asyncio.sleep(1)
            return {}

        result = await _check()
        assert result.get("status") == "SUCCESS"


# ===================================================================
# C. Workflow CRUD
# ===================================================================


class TestWorkflowCRUD:
    async def test_create_workflow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        resp = await api_client.post(
            "/api/workflows", json=_simple_workflow("crud-create")
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_get_workflow(self, api_client: httpx.AsyncClient) -> None:
        create_resp = await api_client.post(
            "/api/workflows", json=_simple_workflow("crud-get")
        )
        wf_id: str = create_resp.json()["id"]

        resp = await api_client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "crud-get"
        assert len(data["steps"]) == 1

    async def test_list_workflows(
        self, api_client: httpx.AsyncClient
    ) -> None:
        await api_client.post(
            "/api/workflows", json=_simple_workflow("crud-list")
        )
        resp = await api_client.get("/api/workflows")
        assert resp.status_code == 200
        names = [w["name"] for w in resp.json()]
        assert "crud-list" in names

    async def test_update_workflow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        create_resp = await api_client.post(
            "/api/workflows", json=_simple_workflow("crud-update-old")
        )
        wf_id: str = create_resp.json()["id"]

        update_resp = await api_client.put(
            f"/api/workflows/{wf_id}",
            json={"name": "crud-update-new"},
        )
        assert update_resp.status_code == 200

        get_resp = await api_client.get(f"/api/workflows/{wf_id}")
        assert get_resp.json()["name"] == "crud-update-new"

    async def test_delete_workflow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        create_resp = await api_client.post(
            "/api/workflows", json=_simple_workflow("crud-delete")
        )
        wf_id: str = create_resp.json()["id"]

        del_resp = await api_client.delete(f"/api/workflows/{wf_id}")
        assert del_resp.status_code == 200

        get_resp = await api_client.get(f"/api/workflows/{wf_id}")
        assert get_resp.status_code == 404

    async def test_toggle_workflow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        payload = _simple_workflow("crud-toggle")
        payload["enabled"] = True
        create_resp = await api_client.post("/api/workflows", json=payload)
        wf_id: str = create_resp.json()["id"]

        # Toggle off
        toggle_resp = await api_client.post(
            f"/api/workflows/{wf_id}/toggle"
        )
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["enabled"] is False

        # Toggle on
        toggle_resp2 = await api_client.post(
            f"/api/workflows/{wf_id}/toggle"
        )
        assert toggle_resp2.json()["enabled"] is True


# ===================================================================
# D. Workflow Duplicate & Import
# ===================================================================


class TestWorkflowDuplicateImport:
    async def test_duplicate_workflow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        create_resp = await api_client.post(
            "/api/workflows", json=_simple_workflow("dup-original")
        )
        wf_id: str = create_resp.json()["id"]

        dup_resp = await api_client.post(
            f"/api/workflows/{wf_id}/duplicate",
            json={"name": "dup-custom-name"},
        )
        assert dup_resp.status_code == 201
        dup_id: str = dup_resp.json()["id"]
        assert dup_id != wf_id

        get_resp = await api_client.get(f"/api/workflows/{dup_id}")
        assert get_resp.json()["name"] == "dup-custom-name"
        assert len(get_resp.json()["steps"]) == 1

    async def test_duplicate_default_name(
        self, api_client: httpx.AsyncClient
    ) -> None:
        create_resp = await api_client.post(
            "/api/workflows", json=_simple_workflow("dup-default")
        )
        wf_id: str = create_resp.json()["id"]

        dup_resp = await api_client.post(
            f"/api/workflows/{wf_id}/duplicate", json={}
        )
        assert dup_resp.status_code == 201
        dup_id: str = dup_resp.json()["id"]

        get_resp = await api_client.get(f"/api/workflows/{dup_id}")
        assert get_resp.json()["name"] == "dup-default (Copy)"

    async def test_import_workflow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        payload: dict[str, Any] = {
            "name": "imported-workflow",
            "description": "Imported via API",
            "scheduleType": "none",
            "enabled": False,
            "steps": [
                {
                    "id": f"import-{_uid()}",
                    "label": "Imported Step",
                    "taskNames": ["integration.add"],
                    "args": "[1, 2]",
                },
            ],
        }
        resp = await api_client.post("/api/workflows", json=payload)
        assert resp.status_code == 201

        wf_id: str = resp.json()["id"]
        get_resp = await api_client.get(f"/api/workflows/{wf_id}")
        data = get_resp.json()
        assert data["name"] == "imported-workflow"
        assert data["description"] == "Imported via API"


# ===================================================================
# E. Workflow Execution
# ===================================================================


class TestWorkflowExecution:
    async def test_run_single_step(
        self, api_client: httpx.AsyncClient
    ) -> None:
        create_resp = await api_client.post(
            "/api/workflows", json=_simple_workflow("exec-single")
        )
        wf_id: str = create_resp.json()["id"]

        run_resp = await api_client.post(
            f"/api/workflows/{wf_id}/run-now"
        )
        assert run_resp.status_code == 201
        run_id: str = run_resp.json()["runId"]

        # Poll run detail until succeeded
        detail = await _poll_until(
            api_client,
            f"/api/workflows/runs/{run_id}",
            lambda d: d.get("status") in ("succeeded", "failed"),
            timeout=30,
        )
        assert detail["status"] == "succeeded"

    async def test_run_multistep_linear(
        self, api_client: httpx.AsyncClient
    ) -> None:
        sa, sb = f"step-{_uid()}", f"step-{_uid()}"
        payload: dict[str, Any] = {
            "name": "exec-linear",
            "steps": [
                {
                    "id": sa,
                    "label": "Step A",
                    "taskNames": ["integration.add"],
                    "args": "[1, 2]",
                },
                {
                    "id": sb,
                    "label": "Step B",
                    "taskNames": ["integration.add"],
                    "args": "[3, 4]",
                    "dependsOn": [sa],
                    "condition": "all_succeeded",
                },
            ],
        }
        create_resp = await api_client.post(
            "/api/workflows", json=payload
        )
        wf_id: str = create_resp.json()["id"]

        run_resp = await api_client.post(
            f"/api/workflows/{wf_id}/run-now"
        )
        run_id: str = run_resp.json()["runId"]

        detail = await _poll_until(
            api_client,
            f"/api/workflows/runs/{run_id}",
            lambda d: d.get("status") in ("succeeded", "failed"),
            timeout=45,
        )
        assert detail["status"] == "succeeded"
        assert len(detail["stepRuns"]) == 2

    async def test_run_diamond_dag(
        self, api_client: httpx.AsyncClient
    ) -> None:
        s_root, s_left, s_right, s_join = (
            f"root-{_uid()}", f"left-{_uid()}",
            f"right-{_uid()}", f"join-{_uid()}",
        )
        payload: dict[str, Any] = {
            "name": "exec-diamond",
            "steps": [
                {
                    "id": s_root,
                    "label": "Root",
                    "taskNames": ["integration.add"],
                    "args": "[1, 1]",
                },
                {
                    "id": s_left,
                    "label": "Left",
                    "taskNames": ["integration.add"],
                    "args": "[2, 2]",
                    "dependsOn": [s_root],
                },
                {
                    "id": s_right,
                    "label": "Right",
                    "taskNames": ["integration.add"],
                    "args": "[3, 3]",
                    "dependsOn": [s_root],
                },
                {
                    "id": s_join,
                    "label": "Join",
                    "taskNames": ["integration.add"],
                    "args": "[4, 4]",
                    "dependsOn": [s_left, s_right],
                },
            ],
        }
        create_resp = await api_client.post(
            "/api/workflows", json=payload
        )
        wf_id: str = create_resp.json()["id"]

        run_resp = await api_client.post(
            f"/api/workflows/{wf_id}/run-now"
        )
        run_id: str = run_resp.json()["runId"]

        detail = await _poll_until(
            api_client,
            f"/api/workflows/runs/{run_id}",
            lambda d: d.get("status") in ("succeeded", "failed"),
            timeout=60,
        )
        assert detail["status"] == "succeeded"
        assert len(detail["stepRuns"]) == 4

    async def test_run_with_failure_condition(
        self, api_client: httpx.AsyncClient
    ) -> None:
        sa, sb = f"step-{_uid()}", f"step-{_uid()}"
        payload: dict[str, Any] = {
            "name": "exec-fail-cond",
            "steps": [
                {
                    "id": sa,
                    "label": "Failing Step",
                    "taskNames": ["integration.fail_task"],
                },
                {
                    "id": sb,
                    "label": "Recovery Step",
                    "taskNames": ["integration.add"],
                    "args": "[1, 1]",
                    "dependsOn": [sa],
                    "condition": "any_failed",
                },
            ],
        }
        create_resp = await api_client.post(
            "/api/workflows", json=payload
        )
        wf_id: str = create_resp.json()["id"]

        run_resp = await api_client.post(
            f"/api/workflows/{wf_id}/run-now"
        )
        run_id: str = run_resp.json()["runId"]

        detail = await _poll_until(
            api_client,
            f"/api/workflows/runs/{run_id}",
            lambda d: d.get("status") in ("succeeded", "failed"),
            timeout=45,
        )
        # step-b should have executed because step-a failed (any_failed)
        step_b_runs = [
            sr for sr in detail["stepRuns"] if sr["stepLabel"] == "Recovery Step"
        ]
        assert len(step_b_runs) == 1
        assert step_b_runs[0]["status"] == "succeeded"

    async def test_scheduled_workflow(
        self, api_client: httpx.AsyncClient
    ) -> None:
        payload: dict[str, Any] = {
            "name": "exec-scheduled",
            "scheduleType": "interval",
            "intervalSeconds": 3,
            "enabled": True,
            "steps": [
                {
                    "id": f"step-{_uid()}",
                    "label": "Scheduled Step",
                    "taskNames": ["integration.add"],
                    "args": "[1, 1]",
                },
            ],
        }
        create_resp = await api_client.post(
            "/api/workflows", json=payload
        )
        wf_id: str = create_resp.json()["id"]

        try:
            # Wait for at least one scheduled run
            await asyncio.sleep(8)

            runs_resp = await api_client.get(
                f"/api/workflows/{wf_id}/runs"
            )
            assert runs_resp.status_code == 200
            runs: list[dict[str, Any]] = runs_resp.json()
            scheduled_runs = [r for r in runs if r["trigger"] == "scheduled"]
            assert len(scheduled_runs) >= 1
        finally:
            # Disable to stop further scheduled runs
            await api_client.post(f"/api/workflows/{wf_id}/toggle")

    async def test_cancel_workflow_run(
        self, api_client: httpx.AsyncClient
    ) -> None:
        payload: dict[str, Any] = {
            "name": "exec-cancel",
            "steps": [
                {
                    "id": f"step-{_uid()}",
                    "label": "Slow Step",
                    "taskNames": ["integration.slow_task"],
                    "args": "[60]",
                },
            ],
        }
        create_resp = await api_client.post(
            "/api/workflows", json=payload
        )
        wf_id: str = create_resp.json()["id"]

        run_resp = await api_client.post(
            f"/api/workflows/{wf_id}/run-now"
        )
        run_id: str = run_resp.json()["runId"]

        # Wait a moment for the run to start
        await asyncio.sleep(3)

        cancel_resp = await api_client.post(
            f"/api/workflows/runs/{run_id}/cancel"
        )
        assert cancel_resp.status_code == 200

        # Verify the run is cancelled
        detail = await _poll_until(
            api_client,
            f"/api/workflows/runs/{run_id}",
            lambda d: d.get("status") == "cancelled",
            timeout=15,
        )
        assert detail["status"] == "cancelled"


# ===================================================================
# F. Auth
# ===================================================================


class TestAuth:
    async def test_auth_required(
        self, anon_client: httpx.AsyncClient
    ) -> None:
        resp = await anon_client.post(
            "/api/workflows", json=_simple_workflow("no-auth")
        )
        assert resp.status_code == 401

    async def test_auth_invalid_token(
        self, anon_client: httpx.AsyncClient
    ) -> None:
        resp = await anon_client.post(
            "/api/workflows",
            json=_simple_workflow("bad-auth"),
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401


# ===================================================================
# G. Validation
# ===================================================================


class TestValidation:
    async def test_dag_cycle_rejected(
        self, api_client: httpx.AsyncClient
    ) -> None:
        sa, sb = f"cyc-{_uid()}", f"cyc-{_uid()}"
        payload: dict[str, Any] = {
            "name": "cycle-test",
            "steps": [
                {
                    "id": sa,
                    "label": "A",
                    "taskNames": ["integration.add"],
                    "dependsOn": [sb],
                },
                {
                    "id": sb,
                    "label": "B",
                    "taskNames": ["integration.add"],
                    "dependsOn": [sa],
                },
            ],
        }
        resp = await api_client.post("/api/workflows", json=payload)
        assert resp.status_code == 400

    async def test_invalid_cron_rejected(
        self, api_client: httpx.AsyncClient
    ) -> None:
        payload: dict[str, Any] = {
            "name": "bad-cron",
            "scheduleType": "cron",
            "cronExpression": "not-a-cron",
            "steps": [
                {
                    "id": f"cron-{_uid()}",
                    "label": "A",
                    "taskNames": ["integration.add"],
                },
            ],
        }
        resp = await api_client.post("/api/workflows", json=payload)
        assert resp.status_code == 400
