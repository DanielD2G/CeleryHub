from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..celery_app import app as celery_app
from ..models.tasks import (
    ActiveTaskInfo,
    ActiveTasksResponse,
    RegisteredTasksResponse,
    RevokeRequest,
    RevokeResponse,
    SendTaskRequest,
    SendTaskResponse,
    TaskStatusResponse,
)
from ..services.celery_redis import (
    get_celery_task_status,
    get_task_payloads,
    send_celery_task,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])

_TASK_NAME_RE = re.compile(r"^[\w.]+$")
_ALLOWED_SIGNALS = {"SIGTERM", "SIGKILL"}


# ------------------------------------------------------------------
# Frontend-facing endpoints (previously in Hono server)
# ------------------------------------------------------------------


@router.get("/active")
async def frontend_active_tasks(request: Request) -> list[dict[str, Any]]:
    cache = request.app.state.celery_cache
    tasks: list[dict[str, Any]] = await cache.get("active-tasks")
    return tasks


@router.get("/history")
async def frontend_task_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    cache = request.app.state.celery_cache
    tasks: list[dict[str, Any]] = await cache.get("task-history")
    return tasks[:limit]


@router.get("/registered")
async def frontend_registered_tasks(request: Request) -> dict[str, Any]:
    cache = request.app.state.celery_cache
    data: dict[str, Any] = await cache.get("registered-tasks")
    return data


@router.get("/payloads", response_model=None)
async def frontend_task_payloads(
    name: str = Query(..., description="Task name"),
) -> list[dict[str, Any]] | JSONResponse:
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    try:
        payloads = await get_task_payloads(name)
        return payloads
    except Exception as exc:
        return JSONResponse(
            {"error": f"Failed to fetch payloads: {exc}"}, status_code=500
        )


@router.post("/send", response_model=None)
async def frontend_send_task(request: Request) -> JSONResponse:
    body = await request.json()
    task_name: str = body.get("taskName", "")
    queue: str = body.get("queue", "celery") or "celery"
    args_raw: str = body.get("args", "[]") or "[]"
    kwargs_raw: str = body.get("kwargs", "{}") or "{}"
    countdown = body.get("countdown")
    eta = body.get("eta")
    priority = body.get("priority")

    if not task_name:
        return JSONResponse({"error": "Task name is required"}, status_code=400)

    if not _TASK_NAME_RE.match(task_name):
        return JSONResponse({"error": "Invalid task name format"}, status_code=400)

    try:
        args = json.loads(args_raw)
        if not isinstance(args, list):
            return JSONResponse({"error": "Args must be a JSON array"}, status_code=400)
    except (json.JSONDecodeError, TypeError):
        return JSONResponse({"error": "Invalid JSON for args"}, status_code=400)

    try:
        kwargs = json.loads(kwargs_raw)
        if not isinstance(kwargs, dict):
            return JSONResponse(
                {"error": "Kwargs must be a JSON object"}, status_code=400
            )
    except (json.JSONDecodeError, TypeError):
        return JSONResponse({"error": "Invalid JSON for kwargs"}, status_code=400)

    # Try Celery app first, fall back to direct Redis
    try:
        loop = asyncio.get_running_loop()
        countdown_f = float(countdown) if countdown is not None else None
        priority_i = int(priority) if priority is not None else None
        result = await loop.run_in_executor(
            None,
            lambda: celery_app.send_task(
                task_name,
                args=args,
                kwargs=kwargs,
                queue=queue,
                countdown=countdown_f,
                eta=eta,
                priority=priority_i,
            ),
        )
        return JSONResponse({"taskId": result.id})
    except Exception:
        try:
            task_id = await send_celery_task(task_name, args, kwargs, queue)
            return JSONResponse({"taskId": task_id})
        except Exception as exc:
            return JSONResponse(
                {"error": f"Failed to send task: {exc}"}, status_code=500
            )


@router.post("/{task_id}/revoke", response_model=None)
async def frontend_revoke_task(task_id: str, request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}

    terminate: bool = body.get("terminate", False)
    signal: str = body.get("signal", "SIGTERM")
    if signal not in _ALLOWED_SIGNALS:
        signal = "SIGTERM"

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: celery_app.control.revoke(
                task_id, terminate=terminate, signal=signal
            ),
        )
        return JSONResponse({"task_id": task_id, "revoked": True})
    except Exception:
        return JSONResponse({"error": "Failed to revoke task"}, status_code=503)


@router.get("/{task_id}/status", response_model=None)
async def frontend_task_status(task_id: str) -> JSONResponse:
    # Try Celery backend first, fall back to Redis
    try:
        loop = asyncio.get_running_loop()
        result: AsyncResult = await loop.run_in_executor(
            None, lambda: AsyncResult(task_id, app=celery_app)
        )

        info: dict[str, Any] = {}
        try:
            backend_meta = await loop.run_in_executor(
                None, lambda: result.backend.get_task_meta(task_id)
            )
            info = backend_meta if isinstance(backend_meta, dict) else {}
        except Exception:
            pass

        return JSONResponse({
            "status": result.status,
            "result": result.result if result.status != "PENDING" else None,
        })
    except Exception:
        try:
            redis_result = await get_celery_task_status(task_id)
            if not redis_result:
                return JSONResponse(None)
            return JSONResponse({
                "status": redis_result["status"],
                "result": redis_result.get("result"),
            })
        except Exception:
            return JSONResponse(None)
