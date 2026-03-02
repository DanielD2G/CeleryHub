from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from sqlalchemy import update

from ..config import settings
from ..db import get_session
from ..db.models import TaskRun
from .kombu_parser import parse_kombu_message
from .redis_client import create_subscriber, get_db_number, get_redis

logger = logging.getLogger(__name__)

_TASK_META_KEY = "celeryhub:tasks"
_ACTIVE_SET_KEY = "celeryhub:active-tasks"
_PAYLOADS_KEY = "celeryhub:payloads"
_KNOWN_TASKS_KEY = "celeryhub:known-tasks"

EventListener = Callable[[dict[str, Any]], None]

_started: bool = False
_listeners: set[EventListener] = set()


def _get_task_ttl() -> int:
    ttl: int = settings.celeryhub_task_ttl
    return ttl if ttl > 0 else 0


def on_celery_event(fn: EventListener) -> Callable[[], None]:
    _listeners.add(fn)

    def _unsubscribe() -> None:
        _listeners.discard(fn)

    return _unsubscribe


async def _expire_if_needed(key: str) -> None:
    ttl = _get_task_ttl()
    if ttl > 0:
        redis = get_redis()
        try:
            await redis.expire(key, ttl)
        except Exception:
            pass


async def _persist_event(event: dict[str, Any]) -> None:
    redis = get_redis()
    uuid: str | None = event.get("uuid")
    if not uuid:
        return

    event_type: str = event.get("type", "")
    hostname: str = event.get("hostname", "")

    if event_type in ("task-sent", "task-received") and event.get("name"):
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        mapping: dict[str, str] = {
            "name": event["name"],
            "worker": hostname,
            "started_at": str(event.get("timestamp", "")),
        }
        if event.get("args") is not None:
            mapping["args"] = str(event["args"])
        if event.get("kwargs") is not None:
            mapping["kwargs"] = str(event["kwargs"])
        await redis.hset(meta_key, mapping=mapping)
        await _expire_if_needed(meta_key)
        await redis.sadd(_KNOWN_TASKS_KEY, event["name"])
        await redis.sadd(_ACTIVE_SET_KEY, uuid)

    if event_type == "task-started":
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        await redis.hset(meta_key, mapping={
            "status": "STARTED",
            "worker": hostname,
            "started_at": str(event.get("timestamp", "")),
        })
        await redis.sadd(_ACTIVE_SET_KEY, uuid)

    if event_type == "task-sent" and event.get("name"):
        payload = json.dumps({
            "args": event.get("args", "[]"),
            "kwargs": event.get("kwargs", "{}"),
            "queue": event.get("queue", "celery"),
            "timestamp": event.get("timestamp"),
        })
        payload_key = f"{_PAYLOADS_KEY}:{event['name']}"
        await redis.lpush(payload_key, payload)
        await redis.ltrim(payload_key, 0, 9)
        await _expire_if_needed(payload_key)

    if event_type == "task-succeeded":
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        fields: dict[str, str] = {"status": "SUCCESS"}
        if event.get("runtime") is not None:
            fields["runtime"] = str(event["runtime"])
        if hostname:
            fields["worker"] = hostname
        await redis.hset(meta_key, mapping=fields)
        await redis.srem(_ACTIVE_SET_KEY, uuid)
        await _update_run_status(uuid, "SUCCESS")

    if event_type == "task-failed":
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        fields = {"status": "FAILURE"}
        if event.get("exception"):
            fields["exception"] = event["exception"]
        if hostname:
            fields["worker"] = hostname
        await redis.hset(meta_key, mapping=fields)
        await redis.srem(_ACTIVE_SET_KEY, uuid)
        await _update_run_status(uuid, "FAILURE", error=event.get("exception"))

    if event_type == "task-revoked":
        await redis.srem(_ACTIVE_SET_KEY, uuid)


async def _update_run_status(
    task_uuid: str, status: str, *, error: str | None = None
) -> None:
    """Update TaskRun status, then advance workflow."""
    try:
        async with get_session() as session:
            values: dict[str, Any] = {"status": status}
            if error is not None:
                values["error"] = error
            await session.execute(
                update(TaskRun)
                .where(TaskRun.task_id == task_uuid)
                .values(**values)
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "[CeleryHub EventCollector] Failed to update TaskRun %s: %s",
            task_uuid,
            exc,
        )

    try:
        from .workflow_engine import on_task_completed

        await on_task_completed(task_uuid, status, error=error)
    except Exception as exc:
        logger.warning(
            "[CeleryHub EventCollector] Workflow engine error for %s: %s",
            task_uuid,
            exc,
        )


_BACKOFF_BASE: float = 1.0
_BACKOFF_MAX: float = 30.0


async def _subscriber_loop() -> None:
    backoff: float = _BACKOFF_BASE

    while True:
        try:
            await _subscribe_once()
            backoff = _BACKOFF_BASE
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "[CeleryHub EventCollector] Disconnected, retrying in %.1fs",
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)


async def _subscribe_once() -> None:
    db_number = get_db_number()
    pattern = f"/{db_number}.celeryev/*"
    subscriber = create_subscriber()
    pubsub = subscriber.pubsub()

    try:
        await pubsub.psubscribe(pattern)
        logger.info("[CeleryHub EventCollector] Subscribed to %s", pattern)

        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue

            try:
                channel: str = message["channel"]
                data: str = message["data"]
                parts = channel.split("/")
                raw_event_type = parts[-1] if parts else None
                event = parse_kombu_message(data, raw_event_type)
                if event is not None:
                    await _persist_event(event)
                    for fn in list(_listeners):
                        try:
                            fn(event)
                        except Exception:
                            pass
            except Exception:
                pass
    finally:
        try:
            await pubsub.punsubscribe(pattern)
            await pubsub.aclose()
            await subscriber.aclose()
        except Exception:
            pass


def start_event_collector() -> asyncio.Task[None] | None:
    global _started
    if _started:
        return None
    if not settings.celery_broker_url:
        logger.info("[CeleryHub EventCollector] Skipped — celery_broker_url not set")
        return None
    _started = True
    return asyncio.create_task(_subscriber_loop())


async def stop_event_collector(task: asyncio.Task[None]) -> None:
    global _started
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    _started = False
