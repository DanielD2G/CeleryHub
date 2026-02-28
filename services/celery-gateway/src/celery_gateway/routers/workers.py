from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request

from ..models.workers import QueueInfo, QueuesResponse, WorkerInspectResponse

router = APIRouter(tags=["workers"])

VALID_METHODS = {
    "active",
    "registered",
    "reserved",
    "scheduled",
    "stats",
    "conf",
    "active_queues",
}


@router.get("/workers/inspect", response_model=WorkerInspectResponse)
async def inspect_workers(
    request: Request,
    methods: str = Query("active,registered,stats,active_queues"),
    refresh: bool = Query(False),
    workers: str | None = Query(None),
):
    cache = request.app.state.inspect_cache
    destination = workers.split(",") if workers else None
    requested = [m.strip() for m in methods.split(",") if m.strip() in VALID_METHODS]

    if not requested:
        requested = ["active", "registered", "stats", "active_queues"]

    results = await asyncio.gather(
        *[
            cache.get(method, force_refresh=refresh, destination=destination)
            for method in requested
        ]
    )

    response_data: dict[str, Any] = {}
    for method, result in zip(requested, results):
        response_data[method] = result

    cached = not refresh
    return WorkerInspectResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        cached=cached,
        **response_data,
    )


@router.get("/workers/{method}")
async def inspect_single_method(
    method: str,
    request: Request,
    refresh: bool = Query(False),
    workers: str | None = Query(None),
):
    if method not in VALID_METHODS:
        return {"error": f"Invalid method: {method}. Valid: {sorted(VALID_METHODS)}"}

    cache = request.app.state.inspect_cache
    destination = workers.split(",") if workers else None
    data = await cache.get(method, force_refresh=refresh, destination=destination)

    return {
        method: data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cached": not refresh,
    }


@router.get("/queues", response_model=QueuesResponse)
async def get_queues(
    request: Request,
    refresh: bool = Query(False),
):
    cache = request.app.state.inspect_cache
    data = await cache.get("active_queues", force_refresh=refresh)

    # Build queue -> consumers mapping
    queue_consumers: dict[str, set[str]] = {}
    for worker_name, queues_list in data.items():
        for q in queues_list:
            name = q.get("name", q) if isinstance(q, dict) else str(q)
            if name not in queue_consumers:
                queue_consumers[name] = set()
            queue_consumers[name].add(worker_name)

    # Get queue depths from Redis
    from ..celery_app import app as celery_app

    queue_names = list(queue_consumers.keys())
    depths: dict[str, int] = {}

    if queue_names:
        try:
            broker_url = celery_app.conf.broker_url
            import redis as redis_lib

            r = redis_lib.Redis.from_url(broker_url)
            pipe = r.pipeline()
            for name in queue_names:
                pipe.llen(name)
            results = pipe.execute()
            r.close()
            for name, length in zip(queue_names, results):
                depths[name] = int(length) if isinstance(length, int) else 0
        except Exception:
            for name in queue_names:
                depths[name] = 0

    queues = [
        QueueInfo(
            name=name,
            depth=depths.get(name, 0),
            consumers=sorted(consumers),
        )
        for name, consumers in sorted(queue_consumers.items())
    ]

    return QueuesResponse(queues=queues)
