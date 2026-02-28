from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Query, Request

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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/send", response_model=SendTaskResponse)
async def send_task(req: SendTaskRequest):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: celery_app.send_task(
            req.task_name,
            args=req.args,
            kwargs=req.kwargs,
            queue=req.queue,
            countdown=req.countdown,
            eta=req.eta,
            expires=req.expires,
            priority=req.priority,
            task_id=req.task_id,
        ),
    )
    return SendTaskResponse(task_id=result.id)


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def task_status(task_id: str):
    loop = asyncio.get_running_loop()
    result: AsyncResult = await loop.run_in_executor(
        None, lambda: AsyncResult(task_id, app=celery_app)
    )

    info: dict[str, Any] = {}
    try:
        backend_meta = await loop.run_in_executor(None, lambda: result.backend.get_task_meta(task_id))
        info = backend_meta if isinstance(backend_meta, dict) else {}
    except Exception:
        pass

    return TaskStatusResponse(
        task_id=task_id,
        status=result.status,
        result=result.result if result.status != "PENDING" else None,
        traceback=str(result.traceback) if result.traceback else None,
        date_done=info.get("date_done"),
        name=info.get("name"),
        worker=info.get("worker"),
        runtime=info.get("runtime"),
    )


@router.post("/{task_id}/revoke", response_model=RevokeResponse)
async def revoke_task(task_id: str, req: RevokeRequest):
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            lambda: celery_app.control.revoke(
                task_id, terminate=req.terminate, signal=req.signal
            ),
        )
        return RevokeResponse(task_id=task_id, revoked=True)
    except Exception:
        logger.exception("Failed to revoke task %s", task_id)
        return RevokeResponse(task_id=task_id, revoked=False)


@router.get("/active", response_model=ActiveTasksResponse)
async def active_tasks(
    request: Request,
    refresh: bool = Query(False),
    workers: str | None = Query(None),
):
    cache = request.app.state.inspect_cache
    destination = workers.split(",") if workers else None
    data = await cache.get("active", force_refresh=refresh, destination=destination)

    all_tasks: list[ActiveTaskInfo] = []
    by_worker: dict[str, list[ActiveTaskInfo]] = {}

    for worker_name, task_list in data.items():
        worker_tasks = []
        for t in task_list:
            info = ActiveTaskInfo(
                id=t.get("id", ""),
                name=t.get("name", "unknown"),
                args=str(t.get("args")),
                kwargs=str(t.get("kwargs")),
                worker=worker_name,
                time_start=t.get("time_start"),
                acknowledged=t.get("acknowledged", False),
            )
            worker_tasks.append(info)
            all_tasks.append(info)
        by_worker[worker_name] = worker_tasks

    return ActiveTasksResponse(tasks=all_tasks, by_worker=by_worker)


@router.get("/registered", response_model=RegisteredTasksResponse)
async def registered_tasks(
    request: Request,
    refresh: bool = Query(False),
    workers: str | None = Query(None),
):
    cache = request.app.state.inspect_cache
    destination = workers.split(",") if workers else None
    data = await cache.get("registered", force_refresh=refresh, destination=destination)

    all_tasks: set[str] = set()
    by_worker: dict[str, list[str]] = {}

    for worker_name, task_list in data.items():
        by_worker[worker_name] = sorted(task_list)
        all_tasks.update(task_list)

    return RegisteredTasksResponse(tasks=sorted(all_tasks), by_worker=by_worker)
