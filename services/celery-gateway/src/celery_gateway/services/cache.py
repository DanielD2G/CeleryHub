from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, TypeVar

from .inspect_cache import InspectCache
from .redis_client import get_redis

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _CacheEntry:
    __slots__ = ("data", "updated_at", "ttl_s", "task", "inflight", "refresh_fn")

    def __init__(
        self,
        ttl_s: float,
        refresh_fn: Callable[[], Coroutine[Any, Any, Any]],
    ) -> None:
        self.data: Any = None
        self.updated_at: float = 0.0
        self.ttl_s = ttl_s
        self.task: asyncio.Task[None] | None = None
        self.inflight: asyncio.Task[Any] | None = None
        self.refresh_fn = refresh_fn


class CeleryCache:
    def __init__(self, inspect_cache: InspectCache) -> None:
        self._inspect_cache = inspect_cache
        self._entries: dict[str, _CacheEntry] = {}

        self._register("active-tasks", 2.0, self._refresh_active_tasks)
        self._register("queue-depths", 30.0, self._refresh_queue_depths)
        self._register("task-history", 10.0, self._refresh_task_history)
        self._register("worker-inspect", 15.0, self._refresh_worker_inspect)
        self._register("registered-tasks", 60.0, self._refresh_registered_tasks)
        self._register("queue-details", 5.0, self._refresh_queue_details)

    def _register(
        self,
        key: str,
        ttl_s: float,
        refresh_fn: Callable[[], Coroutine[Any, Any, Any]],
    ) -> None:
        self._entries[key] = _CacheEntry(ttl_s, refresh_fn)

    async def get(self, key: str) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            raise KeyError(f"Unknown cache key: {key}")

        if entry.updated_at == 0.0:
            await self._refresh(key)
            self._start_timer(key)

        if entry.data is None:
            return {}
        return entry.data

    async def _refresh(self, key: str) -> None:
        entry = self._entries[key]

        if entry.inflight is not None:
            try:
                await entry.inflight
            except Exception:
                pass
            return

        task = asyncio.create_task(entry.refresh_fn())
        entry.inflight = task

        try:
            data = await task
            entry.data = data
            entry.updated_at = time.monotonic()
        except Exception:
            logger.warning("Cache refresh failed for %r", key, exc_info=True)
        finally:
            entry.inflight = None

    def _start_timer(self, key: str) -> None:
        entry = self._entries[key]
        if entry.task is not None:
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(entry.ttl_s)
                try:
                    await self._refresh(key)
                except Exception:
                    logger.warning(
                        "Background refresh timer failed for %r", key, exc_info=True
                    )

        entry.task = asyncio.create_task(_loop())

    def stop(self) -> None:
        for entry in self._entries.values():
            if entry.task is not None:
                entry.task.cancel()
                entry.task = None

    # ------------------------------------------------------------------
    # Refresh functions
    # ------------------------------------------------------------------

    async def _refresh_active_tasks(self) -> list[dict[str, Any]]:
        try:
            active_data, reserved_data = await asyncio.gather(
                self._inspect_cache.get("active"),
                self._inspect_cache.get("reserved"),
            )
            tasks: list[dict[str, Any]] = []
            seen_ids: set[str] = set()

            # Active tasks (currently executing)
            for worker_name, task_list in active_data.items():
                for t in task_list:
                    task_id = t.get("id", "")
                    if task_id:
                        seen_ids.add(task_id)
                    tasks.append({
                        "taskId": task_id,
                        "name": t.get("name", "unknown"),
                        "worker": worker_name,
                        "startedAt": t.get("time_start") or time.time(),
                        "status": "started" if t.get("acknowledged") else "received",
                        "args": str(t.get("args")) if t.get("args") is not None else None,
                        "kwargs": str(t.get("kwargs")) if t.get("kwargs") is not None else None,
                    })

            # Reserved tasks (received by worker, waiting to execute)
            for worker_name, task_list in reserved_data.items():
                for t in task_list:
                    task_id = t.get("id", "")
                    if task_id in seen_ids:
                        continue
                    seen_ids.add(task_id)
                    tasks.append({
                        "taskId": task_id,
                        "name": t.get("name", "unknown"),
                        "worker": worker_name,
                        "startedAt": t.get("time_start") or time.time(),
                        "status": "received",
                        "args": str(t.get("args")) if t.get("args") is not None else None,
                        "kwargs": str(t.get("kwargs")) if t.get("kwargs") is not None else None,
                    })

            return tasks
        except Exception:
            try:
                from .celery_redis import get_active_tasks
                return await get_active_tasks()
            except Exception:
                return []

    async def _refresh_queue_depths(self) -> dict[str, int]:
        try:
            data = await self._inspect_cache.get("active_queues")
            queue_names: set[str] = set()
            for _worker, queues_list in data.items():
                for q in queues_list:
                    name = q.get("name", q) if isinstance(q, dict) else str(q)
                    queue_names.add(name)
            if not queue_names:
                return {"celery": 0}
            from .celery_redis import get_queue_lengths
            return await get_queue_lengths(list(queue_names))
        except Exception:
            try:
                from .celery_redis import get_queue_lengths
                return await get_queue_lengths(["celery"])
            except Exception:
                return {"celery": 0}

    async def _refresh_task_history(self) -> list[dict[str, Any]]:
        try:
            from .celery_redis import get_historical_tasks
            tasks = await get_historical_tasks(50)

            names = [t["name"] for t in tasks if t.get("name") and t["name"] != "unknown"]
            if names:
                try:
                    redis = get_redis()
                    await redis.sadd("celeryhub:known-tasks", *names)
                except Exception:
                    pass

            return tasks
        except Exception:
            return []

    async def _refresh_worker_inspect(self) -> dict[str, Any] | None:
        try:
            methods = ["active", "registered", "stats", "active_queues"]
            results = await asyncio.gather(
                *[self._inspect_cache.get(m) for m in methods]
            )
            data: dict[str, Any] = {}
            for method, result in zip(methods, results):
                data[method] = result

            import datetime
            data["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            data["cached"] = True
            return data
        except Exception:
            return None

    async def _refresh_registered_tasks(self) -> dict[str, Any]:
        try:
            from .celery_redis import get_known_task_names
            known_names = await get_known_task_names()

            by_worker: dict[str, list[str]] = {}
            try:
                registered = await self._inspect_cache.get("registered")
                if registered:
                    for worker_name, task_list in registered.items():
                        by_worker[worker_name] = sorted(task_list)
                    # Seed the known-tasks set with what workers actually
                    # register, so newly deployed tasks appear everywhere
                    # without waiting for their first event.
                    fresh = {
                        t for tasks in registered.values() for t in tasks
                        if t and not t.startswith("celery.")
                    }
                    new_names = fresh - set(known_names)
                    if new_names:
                        from .redis_client import get_redis

                        await get_redis().sadd(
                            "celeryhub:known-tasks", *new_names
                        )
                        known_names = sorted(set(known_names) | new_names)
            except Exception:
                pass

            all_tasks: set[str] = set(known_names)
            for tasks in by_worker.values():
                all_tasks.update(tasks)

            return {"byWorker": by_worker, "tasks": sorted(all_tasks)}
        except Exception:
            return {"byWorker": {}, "tasks": []}

    async def _refresh_queue_details(self) -> dict[str, Any]:
        try:
            depths = await self.get("queue-depths")
        except Exception:
            depths = {"celery": 0}

        queue_names = list(depths.keys())
        pending: dict[str, list[dict[str, str]]] = {}

        from .celery_redis import get_pending_tasks

        results = await asyncio.gather(
            *[get_pending_tasks(q, 200) for q in queue_names],
            return_exceptions=True,
        )

        for i, q in enumerate(queue_names):
            result = results[i]
            pending[q] = result if isinstance(result, list) else []

        return {
            "queueNames": queue_names,
            "depths": depths,
            "pending": pending,
        }
