from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ..celery_app import app as celery_app
from ..middleware.auth import require_auth
from ..models.tasks import (
    FrontendActiveTask,
    FrontendRegisteredTasksResult,
    FrontendSendTaskRequest,
    FrontendSendTaskResponse,
    FrontendTaskHistoryItem,
    FrontendTaskPayload,
    FrontendTaskStatusResponse,
    RevokeRequest,
    RevokeResponse,
)
from ..services.celery_redis import (
    get_celery_task_status,
    get_task_payloads,
    send_celery_task,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


# ------------------------------------------------------------------
# Frontend-facing endpoints (previously in Hono server)
# ------------------------------------------------------------------


@router.get("/active", response_model=list[FrontendActiveTask])
async def frontend_active_tasks(request: Request) -> Any:
    cache = request.app.state.celery_cache
    return await cache.get("active-tasks")


@router.get("/history", response_model=list[FrontendTaskHistoryItem])
async def frontend_task_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    cache = request.app.state.celery_cache
    tasks: list[dict[str, Any]] = await cache.get("task-history")
    return tasks[:limit]


@router.get("/registered", response_model=FrontendRegisteredTasksResult)
async def frontend_registered_tasks(request: Request) -> Any:
    cache = request.app.state.celery_cache
    return await cache.get("registered-tasks")


@router.get("/payloads", response_model=list[FrontendTaskPayload])
async def frontend_task_payloads(
    name: str = Query(..., description="Task name"),
) -> list[dict[str, Any]]:
    return await get_task_payloads(name)


@router.post(
    "/send",
    response_model=FrontendSendTaskResponse,
    dependencies=[Depends(require_auth)],
)
async def frontend_send_task(body: FrontendSendTaskRequest) -> JSONResponse:
    args: list[Any] = json.loads(body.args)
    kwargs: dict[str, Any] = json.loads(body.kwargs)
    queue = body.queue or "celery"

    # Try Celery app first, fall back to direct Redis
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: celery_app.send_task(
                body.task_name,
                args=args,
                kwargs=kwargs,
                queue=queue,
                countdown=body.countdown,
                eta=body.eta,
                priority=body.priority,
            ),
        )
        return JSONResponse({"taskId": result.id})
    except Exception:
        try:
            task_id = await send_celery_task(body.task_name, args, kwargs, queue)
            return JSONResponse({"taskId": task_id})
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to send task: {exc}"}, status_code=500
            )


@router.post(
    "/{task_id}/revoke",
    response_model=RevokeResponse,
    dependencies=[Depends(require_auth)],
)
async def frontend_revoke_task(
    task_id: str,
    body: RevokeRequest | None = None,
) -> JSONResponse:
    revoke_opts = body or RevokeRequest()
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: celery_app.control.revoke(
                task_id,
                terminate=revoke_opts.terminate,
                signal=revoke_opts.signal,
            ),
        )
        return JSONResponse({"task_id": task_id, "revoked": True})
    except Exception:
        return JSONResponse({"error": "Failed to revoke task"}, status_code=503)


@router.get("/{task_id}/status", response_model=FrontendTaskStatusResponse)
async def frontend_task_status(task_id: str) -> Any:
    # Try Celery backend first, fall back to Redis
    try:
        loop = asyncio.get_running_loop()
        result: AsyncResult = await loop.run_in_executor(
            None, lambda: AsyncResult(task_id, app=celery_app)
        )

        return {
            "status": result.status,
            "result": result.result if result.status != "PENDING" else None,
        }
    except Exception:
        try:
            redis_result = await get_celery_task_status(task_id)
            if not redis_result:
                raise HTTPException(status_code=404, detail="Task not found")
            return {
                "status": redis_result["status"],
                "result": redis_result.get("result"),
            }
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=404, detail="Task not found")
