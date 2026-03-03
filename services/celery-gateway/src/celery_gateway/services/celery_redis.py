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


_COMPLETED_ZSET_KEY = "celeryhub:completed"


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

    task_ids: list[str] = await redis.zrevrange(
        _COMPLETED_ZSET_KEY, 0, limit - 1,
    )
    if not task_ids:
        return []

    pipe = redis.pipeline()
    for tid in task_ids:
        pipe.hgetall(f"celeryhub:tasks:{tid}")
    meta_values: list[dict[str, str]] = await pipe.execute()

    tasks: list[dict[str, Any]] = []
    for i, tid in enumerate(task_ids):
        meta = meta_values[i] if meta_values[i] else {}
        if not meta or meta.get("status") not in _TERMINAL_STATES:
            continue

        runtime: float | None = None
        if meta.get("runtime"):
            try:
                runtime = float(meta["runtime"])
            except (ValueError, TypeError):
                pass

        completed_at: float
        if meta.get("completed_at"):
            try:
                completed_at = float(meta["completed_at"])
            except (ValueError, TypeError):
                completed_at = time.time()
        else:
            completed_at = time.time()

        tasks.append({
            "taskId": tid,
            "name": meta.get("name", "unknown"),
            "worker": meta.get("worker", ""),
            "status": meta["status"],
            "runtime": runtime,
            "result": meta.get("result"),
            "traceback": meta.get("traceback"),
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
    queue: str = "celery", limit: int = 200
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
