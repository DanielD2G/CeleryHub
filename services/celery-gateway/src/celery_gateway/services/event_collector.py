from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

from sqlalchemy import update

from ..config import settings
from ..db import get_session
from ..db.models import TaskRun
from .kombu_parser import parse_kombu_message
from .redis_client import create_subscriber, get_db_number, get_redis

logger = logging.getLogger(__name__)

EVENTS_STREAM_KEY = "celeryhub:events:stream"

_TASK_META_KEY = "celeryhub:tasks"
_ACTIVE_SET_KEY = "celeryhub:active-tasks"
_COMPLETED_ZSET_KEY = "celeryhub:completed"
_PAYLOADS_KEY = "celeryhub:payloads"
_KNOWN_TASKS_KEY = "celeryhub:known-tasks"
_COMPLETED_MAX_SIZE = 2000

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


def _pipe_expire(pipe: Any, key: str) -> None:
    ttl = _get_task_ttl()
    if ttl > 0:
        pipe.expire(key, ttl)


def _pipe_index_completed(
    pipe: Any, task_id: str, timestamp: float | int
) -> None:
    score = float(timestamp) if timestamp else time.time()
    pipe.zadd(_COMPLETED_ZSET_KEY, {task_id: score})
    pipe.zremrangebyrank(_COMPLETED_ZSET_KEY, 0, -(_COMPLETED_MAX_SIZE + 1))


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
        pipe = redis.pipeline()
        pipe.hset(meta_key, mapping=mapping)
        _pipe_expire(pipe, meta_key)
        pipe.sadd(_KNOWN_TASKS_KEY, event["name"])
        pipe.sadd(_ACTIVE_SET_KEY, uuid)
        await pipe.execute()

    if event_type == "task-started":
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        pipe = redis.pipeline()
        pipe.hset(meta_key, mapping={
            "status": "STARTED",
            "worker": hostname,
            "started_at": str(event.get("timestamp", "")),
        })
        pipe.sadd(_ACTIVE_SET_KEY, uuid)
        await pipe.execute()

    if event_type == "task-sent" and event.get("name"):
        payload = json.dumps({
            "args": event.get("args", "[]"),
            "kwargs": event.get("kwargs", "{}"),
            "queue": event.get("queue", "celery"),
            "timestamp": event.get("timestamp"),
        })
        payload_key = f"{_PAYLOADS_KEY}:{event['name']}"
        pipe = redis.pipeline()
        pipe.lpush(payload_key, payload)
        pipe.ltrim(payload_key, 0, 9)
        _pipe_expire(pipe, payload_key)
        await pipe.execute()

    if event_type == "task-succeeded":
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        timestamp = event.get("timestamp") or 0
        fields: dict[str, str] = {
            "status": "SUCCESS",
            "completed_at": str(timestamp),
        }
        if event.get("runtime") is not None:
            fields["runtime"] = str(event["runtime"])
        if event.get("result") is not None:
            fields["result"] = str(event["result"])
        if hostname:
            fields["worker"] = hostname
        pipe = redis.pipeline()
        pipe.hset(meta_key, mapping=fields)
        _pipe_expire(pipe, meta_key)
        pipe.srem(_ACTIVE_SET_KEY, uuid)
        _pipe_index_completed(pipe, uuid, timestamp)
        await pipe.execute()
        await _update_run_status(uuid, "SUCCESS")

    if event_type == "task-failed":
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        timestamp = event.get("timestamp") or 0
        fields = {
            "status": "FAILURE",
            "completed_at": str(timestamp),
        }
        if event.get("exception"):
            fields["exception"] = event["exception"]
        if event.get("traceback"):
            fields["traceback"] = event["traceback"]
        if hostname:
            fields["worker"] = hostname
        pipe = redis.pipeline()
        pipe.hset(meta_key, mapping=fields)
        _pipe_expire(pipe, meta_key)
        pipe.srem(_ACTIVE_SET_KEY, uuid)
        _pipe_index_completed(pipe, uuid, timestamp)
        await pipe.execute()
        await _update_run_status(uuid, "FAILURE", error=event.get("exception"))

    if event_type == "task-revoked":
        timestamp = event.get("timestamp") or 0
        meta_key = f"{_TASK_META_KEY}:{uuid}"
        pipe = redis.pipeline()
        pipe.hset(meta_key, mapping={
            "status": "REVOKED",
            "completed_at": str(timestamp),
        })
        _pipe_expire(pipe, meta_key)
        pipe.srem(_ACTIVE_SET_KEY, uuid)
        _pipe_index_completed(pipe, uuid, timestamp)
        await pipe.execute()

    await _publish_to_stream(event)


async def _publish_to_stream(event: dict[str, Any]) -> None:
    redis = get_redis()
    try:
# MAXLEN is an approximate cap that bounds the buffer. Under a sustained
# Postgres/persister outage, once the un-persisted backlog exceeds the cap
# (~1M entries), the oldest un-persisted events are trimmed and permanently
# lost. At-least-once durability holds only within the buffer window.
        await redis.xadd(
            EVENTS_STREAM_KEY,
            {"data": json.dumps(event)},
            maxlen=settings.celeryhub_events_stream_maxlen,
            approximate=True,
        )
    except Exception:
        logger.warning("[CeleryHub EventCollector] Failed to enqueue event to stream")


async def _update_run_status(
    task_uuid: str, status: str, *, error: str | None = None
) -> None:
    """Update TaskRun status, then advance workflow."""
    _db_ok: bool = False
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
            _db_ok = True
    except Exception as exc:
        logger.warning(
            "[CeleryHub EventCollector] Failed to update TaskRun %s: %s",
            task_uuid,
            exc,
        )

    if not _db_ok:
        return

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
                            logger.warning(
                                "[CeleryHub EventCollector] Listener raised",
                                exc_info=True,
                            )
            except Exception:
                # A failed event must not kill the subscription, but a silent
                # drop hides serialization and engine bugs for entire releases.
                logger.warning(
                    "[CeleryHub EventCollector] Failed to process event",
                    exc_info=True,
                )
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
