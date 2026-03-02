"""Test Celery tasks for integration testing."""

import time

from celery import Celery

app = Celery("integration")
app.config_from_object(
    {
        "broker_url": "redis://redis:6379/0",
        "result_backend": "redis://redis:6379/0",
        "task_send_sent_event": True,
        "worker_send_task_events": True,
        "task_track_started": True,
    }
)


@app.task(name="integration.add")
def add(x: int, y: int) -> int:
    """Simple addition — fast task for basic tests."""
    return x + y


@app.task(name="integration.slow_task")
def slow_task(seconds: int = 30) -> str:
    """Long-running task — for revoke/cancel tests."""
    time.sleep(seconds)
    return f"slept {seconds}s"


@app.task(name="integration.fail_task")
def fail_task() -> None:
    """Always fails — for failure-condition tests."""
    raise ValueError("intentional failure for testing")
