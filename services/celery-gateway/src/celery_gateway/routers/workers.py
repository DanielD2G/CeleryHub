from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..models.workers import WorkerInspectResponse

router = APIRouter(tags=["workers"])

_VALID_METHODS = {
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
) -> WorkerInspectResponse:
    cache = request.app.state.inspect_cache
    destination = workers.split(",") if workers else None
    requested = [m.strip() for m in methods.split(",") if m.strip() in _VALID_METHODS]

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
) -> dict[str, Any]:
    if method not in _VALID_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid method: {method}. Valid: {sorted(_VALID_METHODS)}",
        )

    cache = request.app.state.inspect_cache
    destination = workers.split(",") if workers else None
    data = await cache.get(method, force_refresh=refresh, destination=destination)

    return {
        method: data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cached": not refresh,
    }
