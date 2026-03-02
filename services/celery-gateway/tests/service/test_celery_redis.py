from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from celery_gateway.services.celery_redis import (
    get_active_tasks,
    get_celery_task_status,
    get_known_task_names,
    get_pending_tasks,
    get_queue_lengths,
    get_task_payloads,
    send_celery_task,
)


class TestSendCeleryTask:
    async def test_pushes_to_queue(self, fake_redis: Any) -> None:
        task_id = await send_celery_task("tasks.add", args=[1, 2], queue="celery")
        assert task_id is not None

        length = await fake_redis.llen("celery")
        assert length == 1

    async def test_task_id_is_uuid(self, fake_redis: Any) -> None:
        task_id = await send_celery_task("tasks.add")
        parsed = uuid.UUID(task_id)
        assert parsed.version == 4

    async def test_message_structure(self, fake_redis: Any) -> None:
        task_id = await send_celery_task(
            "tasks.add", args=[1, 2], kwargs={"x": 1}, queue="myqueue"
        )

        raw = await fake_redis.lpop("myqueue")
        msg = json.loads(raw)

        assert "body" in msg
        assert msg["headers"]["task"] == "tasks.add"
        assert msg["headers"]["id"] == task_id
        assert msg["properties"]["delivery_info"]["routing_key"] == "myqueue"
        assert msg["properties"]["body_encoding"] == "base64"

    async def test_custom_queue(self, fake_redis: Any) -> None:
        await send_celery_task("tasks.add", queue="high-priority")
        length = await fake_redis.llen("high-priority")
        assert length == 1

    async def test_default_args_kwargs(self, fake_redis: Any) -> None:
        task_id = await send_celery_task("tasks.noop")
        raw = await fake_redis.lpop("celery")
        msg = json.loads(raw)
        assert msg["headers"]["argsrepr"] == "[]"
        assert msg["headers"]["kwargsrepr"] == "{}"


class TestGetCeleryTaskStatus:
    async def test_existing_task(self, fake_redis: Any) -> None:
        task_data = {
            "task_id": "abc-123",
            "status": "SUCCESS",
            "result": 42,
            "traceback": None,
            "date_done": "2025-01-01T00:00:00",
        }
        await fake_redis.set("celery-task-meta-abc-123", json.dumps(task_data))

        result = await get_celery_task_status("abc-123")
        assert result is not None
        assert result["taskId"] == "abc-123"
        assert result["status"] == "SUCCESS"
        assert result["result"] == 42

    async def test_nonexistent_task(self, fake_redis: Any) -> None:
        result = await get_celery_task_status("nonexistent")
        assert result is None

    async def test_invalid_json(self, fake_redis: Any) -> None:
        await fake_redis.set("celery-task-meta-bad", "not valid json")
        result = await get_celery_task_status("bad")
        assert result is None


class TestGetActiveTasks:
    async def test_with_data(self, fake_redis: Any) -> None:
        await fake_redis.sadd("celeryhub:active-tasks", "task1", "task2")
        await fake_redis.hset(
            "celeryhub:tasks:task1",
            mapping={
                "name": "add",
                "worker": "w1",
                "status": "STARTED",
                "started_at": "1234567890.0",
            },
        )
        await fake_redis.hset(
            "celeryhub:tasks:task2",
            mapping={
                "name": "mul",
                "worker": "w2",
                "status": "RECEIVED",
            },
        )

        tasks = await get_active_tasks()
        assert len(tasks) == 2
        names = {t["name"] for t in tasks}
        assert names == {"add", "mul"}

    async def test_empty(self, fake_redis: Any) -> None:
        tasks = await get_active_tasks()
        assert tasks == []

    async def test_cleans_stale(self, fake_redis: Any) -> None:
        await fake_redis.sadd("celeryhub:active-tasks", "done-task")
        await fake_redis.hset(
            "celeryhub:tasks:done-task",
            mapping={"name": "add", "status": "SUCCESS"},
        )

        tasks = await get_active_tasks()
        assert len(tasks) == 0

        # Stale UUID should have been removed from set
        members = await fake_redis.smembers("celeryhub:active-tasks")
        assert "done-task" not in members

    async def test_cleans_missing_meta(self, fake_redis: Any) -> None:
        await fake_redis.sadd("celeryhub:active-tasks", "ghost-task")

        tasks = await get_active_tasks()
        assert len(tasks) == 0

        members = await fake_redis.smembers("celeryhub:active-tasks")
        assert "ghost-task" not in members


class TestGetKnownTaskNames:
    async def test_returns_sorted(self, fake_redis: Any) -> None:
        await fake_redis.sadd("celeryhub:known-tasks", "z_task", "a_task", "m_task")
        names = await get_known_task_names()
        assert names == ["a_task", "m_task", "z_task"]

    async def test_empty(self, fake_redis: Any) -> None:
        names = await get_known_task_names()
        assert names == []


class TestGetQueueLengths:
    async def test_multiple_queues(self, fake_redis: Any) -> None:
        await fake_redis.lpush("celery", "msg1", "msg2")
        await fake_redis.lpush("high", "msg1")

        result = await get_queue_lengths(["celery", "high"])
        assert result["celery"] == 2
        assert result["high"] == 1

    async def test_empty_queues(self, fake_redis: Any) -> None:
        result = await get_queue_lengths(["celery"])
        assert result["celery"] == 0

    async def test_default_queue(self, fake_redis: Any) -> None:
        result = await get_queue_lengths()
        assert "celery" in result


class TestGetTaskPayloads:
    async def test_with_payloads(self, fake_redis: Any) -> None:
        payload = {"args": "[1,2]", "kwargs": "{}", "queue": "celery", "timestamp": 123.0}
        await fake_redis.lpush(
            "celeryhub:payloads:tasks.add", json.dumps(payload)
        )

        result = await get_task_payloads("tasks.add")
        assert len(result) == 1
        assert result[0]["args"] == "[1,2]"

    async def test_empty(self, fake_redis: Any) -> None:
        result = await get_task_payloads("nonexistent")
        assert result == []

    async def test_invalid_json_skipped(self, fake_redis: Any) -> None:
        await fake_redis.lpush("celeryhub:payloads:tasks.bad", "not json")
        await fake_redis.lpush(
            "celeryhub:payloads:tasks.bad",
            json.dumps({"args": "[]"}),
        )

        result = await get_task_payloads("tasks.bad")
        # At least one valid payload should be returned
        assert len(result) >= 1


class TestGetPendingTasks:
    async def test_with_messages(self, fake_redis: Any) -> None:
        msg = {
            "headers": {"id": "task-1", "task": "tasks.add"},
            "properties": {"correlation_id": "task-1"},
        }
        await fake_redis.lpush("celery", json.dumps(msg))

        result = await get_pending_tasks("celery")
        assert len(result) == 1
        assert result[0]["taskId"] == "task-1"
        assert result[0]["taskName"] == "tasks.add"

    async def test_invalid_json_skipped(self, fake_redis: Any) -> None:
        await fake_redis.lpush("celery", "not json")
        result = await get_pending_tasks("celery")
        assert result == []

    async def test_empty_queue(self, fake_redis: Any) -> None:
        result = await get_pending_tasks("empty-queue")
        assert result == []

    async def test_fallback_to_correlation_id(self, fake_redis: Any) -> None:
        msg = {
            "headers": {"task": "tasks.add"},
            "properties": {"correlation_id": "corr-id"},
        }
        await fake_redis.lpush("celery", json.dumps(msg))

        result = await get_pending_tasks("celery")
        assert result[0]["taskId"] == "corr-id"
