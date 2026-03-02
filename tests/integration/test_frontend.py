"""Frontend integration tests for CeleryHub using Playwright."""

from __future__ import annotations

import time

import httpx
from playwright.sync_api import Page, expect

from conftest import AUTH_HEADERS, simple_workflow

_BASE_URL = "http://localhost:3099"
_EXPECT_TIMEOUT = 15_000


# ===================================================================
# A. Pages Render Data
# ===================================================================


class TestPagesRender:
    def test_dashboard_renders(self, page: Page) -> None:
        page.goto("/")
        expect(page.locator("body")).to_contain_text(
            "CeleryHub", timeout=_EXPECT_TIMEOUT
        )

    def test_workers_page_shows_worker(self, page: Page) -> None:
        page.goto("/workers")
        expect(page.locator("body")).to_contain_text(
            "celery@", timeout=_EXPECT_TIMEOUT
        )

    def test_tasks_page_shows_tasks(self, page: Page) -> None:
        page.goto("/tasks")
        expect(page.locator("body")).to_contain_text(
            "integration.add", timeout=_EXPECT_TIMEOUT
        )

    def test_queues_page_renders(self, page: Page) -> None:
        page.goto("/queues")
        expect(page.locator("body")).to_contain_text(
            "celery", timeout=_EXPECT_TIMEOUT
        )

    def test_history_page_shows_tasks(self, page: Page) -> None:
        # Send a task via API so there's something in history
        with httpx.Client(
            base_url=_BASE_URL, headers=AUTH_HEADERS, timeout=10
        ) as client:
            client.post(
                "/api/tasks/send",
                json={"taskName": "integration.add", "args": "[5, 5]"},
            )

        time.sleep(3)

        page.goto("/history")
        expect(page.locator("body")).to_contain_text(
            "integration.add", timeout=_EXPECT_TIMEOUT
        )

    def test_send_page_renders(self, page: Page) -> None:
        page.goto("/send")
        expect(page.locator("body")).to_contain_text(
            "Send", timeout=_EXPECT_TIMEOUT
        )


# ===================================================================
# B. Workflow Frontend
# ===================================================================


class TestWorkflowFrontend:
    def test_workflows_list_page(self, page: Page) -> None:
        with httpx.Client(
            base_url=_BASE_URL, headers=AUTH_HEADERS, timeout=10
        ) as client:
            client.post(
                "/api/workflows",
                json=simple_workflow("fe-list-test"),
            )

        page.goto("/workflows")
        expect(page.locator("body")).to_contain_text(
            "fe-list-test", timeout=_EXPECT_TIMEOUT
        )

    def test_workflow_detail_page(self, page: Page) -> None:
        with httpx.Client(
            base_url=_BASE_URL, headers=AUTH_HEADERS, timeout=10
        ) as client:
            resp = client.post(
                "/api/workflows",
                json=simple_workflow("fe-detail-test"),
            )
            wf_id: str = resp.json()["id"]

        page.goto(f"/workflows/{wf_id}")
        expect(page.locator("body")).to_contain_text(
            "fe-detail-test", timeout=_EXPECT_TIMEOUT
        )

    def test_workflow_run_detail_page(self, page: Page) -> None:
        with httpx.Client(
            base_url=_BASE_URL, headers=AUTH_HEADERS, timeout=10
        ) as client:
            create_resp = client.post(
                "/api/workflows",
                json=simple_workflow("fe-run-test"),
            )
            wf_id: str = create_resp.json()["id"]

            run_resp = client.post(f"/api/workflows/{wf_id}/run-now")
            run_id: str = run_resp.json()["runId"]

        time.sleep(5)

        page.goto(f"/workflows/{wf_id}/runs/{run_id}")
        expect(page.locator("body")).to_contain_text(
            "Step A", timeout=_EXPECT_TIMEOUT
        )
