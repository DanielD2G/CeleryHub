from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter

from ..celery_app import app as celery_app
from ..models.control import (
    ConsumerRequest,
    ControlResponse,
    PoolResizeRequest,
    RateLimitRequest,
    ShutdownRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/control", tags=["control"])


async def _run_control(
    action: str,
    fn,
    *args: Any,
    **kwargs: Any,
) -> ControlResponse:
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
        responses: dict[str, Any] = {}
        if isinstance(result, list):
            for entry in result:
                if isinstance(entry, dict):
                    responses.update(entry)
        elif isinstance(result, dict):
            responses = result
        return ControlResponse(action=action, success=True, responses=responses)
    except Exception as e:
        logger.exception("Control action %s failed", action)
        return ControlResponse(
            action=action, success=False, errors={"error": str(e)}
        )


@router.post("/pool-grow", response_model=ControlResponse)
async def pool_grow(req: PoolResizeRequest):
    return await _run_control(
        "pool_grow",
        celery_app.control.pool_grow,
        req.n,
        destination=req.workers,
    )


@router.post("/pool-shrink", response_model=ControlResponse)
async def pool_shrink(req: PoolResizeRequest):
    return await _run_control(
        "pool_shrink",
        celery_app.control.pool_shrink,
        req.n,
        destination=req.workers,
    )


@router.post("/rate-limit", response_model=ControlResponse)
async def rate_limit(req: RateLimitRequest):
    return await _run_control(
        "rate_limit",
        celery_app.control.rate_limit,
        req.task_name,
        req.rate,
        destination=req.workers,
    )


@router.post("/add-consumer", response_model=ControlResponse)
async def add_consumer(req: ConsumerRequest):
    return await _run_control(
        "add_consumer",
        celery_app.control.add_consumer,
        req.queue,
        destination=req.workers,
    )


@router.post("/cancel-consumer", response_model=ControlResponse)
async def cancel_consumer(req: ConsumerRequest):
    return await _run_control(
        "cancel_consumer",
        celery_app.control.cancel_consumer,
        req.queue,
        destination=req.workers,
    )


@router.post("/shutdown", response_model=ControlResponse)
async def shutdown_workers(req: ShutdownRequest):
    return await _run_control(
        "shutdown",
        celery_app.control.shutdown,
        destination=req.workers,
    )


@router.post("/purge", response_model=ControlResponse)
async def purge():
    loop = asyncio.get_running_loop()
    try:
        count = await loop.run_in_executor(None, celery_app.control.purge)
        return ControlResponse(
            action="purge",
            success=True,
            responses={"purged": count},
        )
    except Exception as e:
        logger.exception("Purge failed")
        return ControlResponse(
            action="purge", success=False, errors={"error": str(e)}
        )
