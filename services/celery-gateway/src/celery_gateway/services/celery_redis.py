from __future__ import annotations

import json
import logging
import time
import uuid
from base64 import b64encode
from typing import Any

from .redis_client import get_redis

logger = logging.getLogger(__name__)

_TERMINAL_STATES = frozenset({"SUCCESS", "FAILURE", "REVOKED"})


async def send_celery_task(
    task_name: str,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    queue: str = "celery",
) -> str:
    redis = get_redis()
    task_id = str(uuid.uuid4())
    args = args or []
    kwargs = kwargs or {}

    body = b64encode(
        json.dumps(
            [args, kwargs, {"callbacks": None, "errbacks": None, "chain": None, "chord": None}]
        ).encode()
    ).decode()

    message = {
        "body": body,
        "content-encoding": "utf-8",
        "content-type": "application/json",
        "headers": {
            "lang": "py",
            "task": task_name,
            "id": task_id,
            "root_id": task_id,
            "parent_id": None,
            "group": None,
            "meth": None,
            "shadow": None,
            "eta": None,
            "expires": None,
            "retries": 0,
            "timelimit": [None, None],
            "argsrepr": json.dumps(args),
            "kwargsrepr": json.dumps(kwargs),
            "origin": "CeleryHub",
        },
        "properties": {
            "correlation_id": task_id,
            "reply_to": "",
            "delivery_mode": 2,
            "delivery_info": {
                "exchange": "",
                "routing_key": queue,
            },
            "priority": 0,
            "body_encoding": "base64",
            "delivery_tag": str(uuid.uuid4()),
        },
    }

    await redis.lpush(queue, json.dumps(message))
    return task_id


class _TaskResult:
    __slots__ = (
        "task_id", "status", "result", "traceback",
        "date_done", "name", "worker", "runtime",
    )

    def __init__(
        self,
        *,
        task_id: str,
        status: str,
        result: Any = None,
        traceback: str | None = None,
        date_done: str = "",
        name: str | None = None,
        worker: str | None = None,
        runtime: float | None = None,
    ) -> None:
        self.task_id = task_id
        self.status = status
        self.result = result
        self.traceback = traceback
        self.date_done = date_done
        self.name = name
        self.worker = worker
        self.runtime = runtime


async def get_celery_task_status(task_id: str) -> dict[str, Any] | None:
    redis = get_redis()
    raw = await redis.get(f"celery-task-meta-{task_id}")
    if not raw:
        return None

    try:
        data = json.loads(raw)
        return {
            "taskId": data.get("task_id", task_id),
            "status": data.get("status", "UNKNOWN"),
            "result": data.get("result"),
            "traceback": data.get("traceback"),
            "dateDone": data.get("date_done", ""),
            "name": data.get("name"),
            "worker": data.get("worker"),
            "runtime": data.get("runtime"),
        }
    except Exception:
        return None


async def get_recent_results(limit: int = 50) -> list[_TaskResult]:
    redis = get_redis()
    results: list[_TaskResult] = []
    cursor: int | bytes = 0

    while True:
        cursor, keys = await redis.scan(
            cursor=cursor, match="celery-task-meta-*", count=100
        )

        if keys:
            pipe = redis.pipeline()
            for key in keys:
                pipe.get(key)
            values = await pipe.execute()

            for val in values:
                if not val:
                    continue
                try:
                    data = json.loads(val)
                    results.append(
                        _TaskResult(
                            task_id=data.get("task_id", ""),
                            status=data.get("status", "UNKNOWN"),
                            result=data.get("result"),
                            traceback=data.get("traceback"),
                            date_done=data.get("date_done", ""),
                            name=data.get("name"),
                            worker=data.get("worker"),
                            runtime=data.get("runtime"),
                        )
                    )
                except Exception:
                    continue

        if len(results) >= limit * 2:
            break
        if cursor == 0:
            break

    results.sort(key=lambda r: r.date_done or "", reverse=True)
    return results[:limit]


async def get_active_tasks() -> list[dict[str, Any]]:
    redis = get_redis()
    uuids = await redis.smembers("celeryhub:active-tasks")
    if not uuids:
        return []

    uuid_list = list(uuids)

    pipe = redis.pipeline()
    for uid in uuid_list:
        pipe.hgetall(f"celeryhub:tasks:{uid}")
    values = await pipe.execute()

    tasks: list[dict[str, Any]] = []
    stale_uuids: list[str] = []

    status_map = {"STARTED": "started", "RECEIVED": "received"}

    for i, uid in enumerate(uuid_list):
        meta: dict[str, str] = values[i] if values[i] else {}

        if not meta or meta.get("status") in ("SUCCESS", "FAILURE"):
            stale_uuids.append(uid)
            continue

        tasks.append({
            "taskId": uid,
            "name": meta.get("name", "unknown"),
            "worker": meta.get("worker", ""),
            "startedAt": float(meta["started_at"]) if meta.get("started_at") else time.time(),
            "status": status_map.get(meta.get("status", ""), "received"),
            "args": meta.get("args"),
            "kwargs": meta.get("kwargs"),
        })

    if stale_uuids:
        try:
            await redis.srem("celeryhub:active-tasks", *stale_uuids)
        except Exception:
            pass

    return tasks


async def get_historical_tasks(limit: int = 50) -> list[dict[str, Any]]:
    redis = get_redis()
    results = await get_recent_results(limit)

    terminal = [r for r in results if r.status in _TERMINAL_STATES]
    if not terminal:
        return []

    pipe = redis.pipeline()
    for r in terminal:
        pipe.hgetall(f"celeryhub:tasks:{r.task_id}")
    meta_values = await pipe.execute()

    tasks: list[dict[str, Any]] = []
    for i, r in enumerate(terminal):
        meta: dict[str, str] = meta_values[i] if meta_values[i] else {}

        runtime = r.runtime
        if runtime is None and meta.get("runtime"):
            try:
                runtime = float(meta["runtime"])
            except (ValueError, TypeError):
                pass

        result_str: str | None = None
        if r.result is not None:
            result_str = str(r.result)

        completed_at: float
        if r.date_done:
            try:
                from datetime import datetime, timezone

                dt = datetime.fromisoformat(r.date_done.replace("Z", "+00:00"))
                completed_at = dt.timestamp()
            except Exception:
                completed_at = time.time()
        else:
            completed_at = time.time()

        tasks.append({
            "taskId": r.task_id,
            "name": r.name or meta.get("name", "unknown"),
            "worker": r.worker or meta.get("worker", ""),
            "status": r.status,
            "runtime": runtime,
            "result": result_str,
            "traceback": r.traceback or None,
            "args": meta.get("args"),
            "kwargs": meta.get("kwargs"),
            "completedAt": completed_at,
        })

    return tasks


async def get_known_task_names() -> list[str]:
    redis = get_redis()
    names = await redis.smembers("celeryhub:known-tasks")
    return sorted(names)


async def get_queue_lengths(queues: list[str] | None = None) -> dict[str, int]:
    queues = queues or ["celery"]
    redis = get_redis()
    result: dict[str, int] = {}

    pipe = redis.pipeline()
    for q in queues:
        pipe.llen(q)
    values = await pipe.execute()

    for i, q in enumerate(queues):
        try:
            result[q] = int(values[i])
        except (TypeError, ValueError):
            result[q] = 0

    return result


async def get_task_payloads(
    task_name: str, limit: int = 10
) -> list[dict[str, Any]]:
    redis = get_redis()
    raw_items = await redis.lrange(f"celeryhub:payloads:{task_name}", 0, limit - 1)
    payloads: list[dict[str, Any]] = []

    for item in raw_items:
        try:
            payloads.append(json.loads(item))
        except Exception:
            continue

    return payloads


async def get_pending_tasks(
    queue: str = "celery", limit: int = 20
) -> list[dict[str, str]]:
    redis = get_redis()
    raw_items = await redis.lrange(queue, 0, limit - 1)
    tasks: list[dict[str, str]] = []

    for item in raw_items:
        try:
            msg = json.loads(item)
            task_id = (
                (msg.get("headers") or {}).get("id")
                or (msg.get("properties") or {}).get("correlation_id")
                or ""
            )
            task_name = (msg.get("headers") or {}).get("task", "unknown")
            from datetime import datetime, timezone

            tasks.append({
                "taskId": task_id,
                "taskName": task_name,
                "enqueuedAt": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            continue

    return tasks
