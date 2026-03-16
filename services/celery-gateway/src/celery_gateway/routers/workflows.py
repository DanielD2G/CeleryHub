from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.orm import selectinload

from ..db import get_session
from ..db.models import StepRun, Workflow, WorkflowRun, WorkflowStep
from ..middleware.auth import require_auth
from ..models.base import CamelModel

from ..models.workflows import (
    CreateWorkflowInput,
    StepInput,
    UpdateWorkflowInput,
    WorkflowResponse,
    WorkflowRunDetailResponse,
    WorkflowRunResponse,
    WorkflowSummaryResponse,
)
from ..services.scheduler import compute_next_run_at, validate_cron_expression

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# DAG validation
# ---------------------------------------------------------------------------


def _validate_dag(steps: list[StepInput]) -> None:
    """Validate that steps form a valid DAG using Kahn's algorithm."""
    step_ids: set[str] = {s.id for s in steps}

    # Check for duplicates
    if len(step_ids) != len(steps):
        raise HTTPException(status_code=400, detail="Duplicate step IDs found")

    # Build adjacency and in-degree
    in_degree: dict[str, int] = {s.id: 0 for s in steps}
    adjacency: dict[str, list[str]] = {s.id: [] for s in steps}

    for step in steps:
        for dep_id in step.depends_on:
            if dep_id == step.id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Step '{step.id}' cannot depend on itself",
                )
            if dep_id not in step_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Step '{step.id}' depends on unknown step '{dep_id}'",
                )
            adjacency[dep_id].append(step.id)
            in_degree[step.id] += 1

    # At least one root step
    roots: list[str] = [sid for sid, deg in in_degree.items() if deg == 0]
    if not roots:
        raise HTTPException(
            status_code=400, detail="At least one root step (no dependencies) required"
        )

    # Kahn's algorithm
    queue: deque[str] = deque(roots)
    visited: int = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for child in adjacency[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if visited < len(steps):
        raise HTTPException(status_code=400, detail="Cycle detected in step dependencies")


def _validate_schedule_fields(
    schedule_type: str,
    interval_seconds: int | None,
    cron_expression: str | None,
) -> None:
    """Validate schedule-type-specific fields."""
    if schedule_type == "interval":
        if not interval_seconds or interval_seconds <= 0:
            raise HTTPException(
                status_code=400,
                detail="Interval seconds must be a positive number",
            )
    elif schedule_type == "cron":
        if not cron_expression:
            raise HTTPException(
                status_code=400, detail="Cron expression is required"
            )
        cron_error = validate_cron_expression(cron_expression)
        if cron_error:
            raise HTTPException(
                status_code=400, detail=f"Invalid cron: {cron_error}"
            )


# ---------------------------------------------------------------------------
# Step ID remapping
# ---------------------------------------------------------------------------


def _build_step_id_map(step_ids: list[str]) -> dict[str, str]:
    """Map client-provided step IDs to server-generated UUIDs."""
    return {sid: str(uuid.uuid4()) for sid in step_ids}


def _remap_step_ids(steps: list[StepInput]) -> list[StepInput]:
    """Replace client-provided step IDs with server-generated UUIDs."""
    id_map = _build_step_id_map([s.id for s in steps])
    return [
        step.model_copy(update={
            "id": id_map[step.id],
            "depends_on": [id_map.get(d, d) for d in step.depends_on],
        })
        for step in steps
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[WorkflowSummaryResponse])
async def list_workflows() -> Any:
    async with get_session() as session:
        stmt = (
            select(
                Workflow,
                func.count(WorkflowStep.id).label("step_count"),
            )
            .outerjoin(WorkflowStep, WorkflowStep.workflow_id == Workflow.id)
            .group_by(Workflow.id)
            .order_by(desc(Workflow.created_at))
        )
        result = await session.execute(stmt)
        rows: list[Any] = result.all()

        return [
            WorkflowSummaryResponse.model_validate(
                {
                    **{
                        c.key: getattr(wf, c.key)
                        for c in Workflow.__table__.columns
                    },
                    "step_count": step_count,
                }
            )
            for wf, step_count in rows
        ]


@router.post("", response_model=None, dependencies=[Depends(require_auth)])
async def create_workflow(body: CreateWorkflowInput) -> JSONResponse:
    _validate_dag(body.steps)
    steps = _remap_step_ids(body.steps)

    schedule_type = body.schedule_type
    if schedule_type != "none":
        _validate_schedule_fields(
            schedule_type, body.interval_seconds, body.cron_expression
        )

    workflow_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    next_run_at: datetime | None = None
    if body.enabled and schedule_type != "none":
        try:
            next_run_at = compute_next_run_at(
                schedule_type, body.interval_seconds, body.cron_expression
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"Failed to compute next run: {exc}"
            ) from exc

    async with get_session() as session:
        workflow = Workflow(
            id=workflow_id,
            name=body.name,
            description=body.description,
            schedule_type=schedule_type,
            interval_seconds=body.interval_seconds,
            cron_expression=body.cron_expression,
            enabled=body.enabled,
            max_run_count=body.max_run_count,
            total_run_count=0,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        )
        session.add(workflow)

        for step in steps:
            ws = WorkflowStep(
                id=step.id,
                workflow_id=workflow_id,
                label=step.label,
                task_names=json.dumps(step.task_names),
                args=step.args or "[]",
                kwargs=step.kwargs or "{}",
                queue=step.queue or "celery",
                depends_on=json.dumps(step.depends_on),
                condition=step.condition,
                timeout_seconds=step.timeout_seconds,
            )
            session.add(ws)

        await session.commit()

    return JSONResponse({"id": workflow_id}, status_code=201)


@router.get(
    "/runs/{run_id}", response_model=WorkflowRunDetailResponse
)
async def get_workflow_run_detail(run_id: str) -> Any:
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRun)
            .options(
                selectinload(WorkflowRun.step_runs).selectinload(StepRun.task_runs)
            )
            .where(WorkflowRun.id == run_id)
            .limit(1)
        )
        wf_run = result.scalar_one_or_none()
        if not wf_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        return wf_run


@router.post(
    "/runs/{run_id}/cancel",
    response_model=None,
    dependencies=[Depends(require_auth)],
)
async def cancel_run(run_id: str) -> JSONResponse:
    from ..services.workflow_engine import cancel_workflow_run

    cancelled: bool = await cancel_workflow_run(run_id)
    if not cancelled:
        raise HTTPException(
            status_code=404, detail="Workflow run not found or not running"
        )
    return JSONResponse({"ok": True})


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str) -> Any:
    async with get_session() as session:
        result = await session.execute(
            select(Workflow)
            .options(selectinload(Workflow.steps))
            .where(Workflow.id == workflow_id)
            .limit(1)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow


@router.put(
    "/{workflow_id}", response_model=None, dependencies=[Depends(require_auth)]
)
async def update_workflow(
    workflow_id: str, body: UpdateWorkflowInput
) -> JSONResponse:
    updates = body.model_dump(exclude_unset=True)

    async with get_session() as session:
        result = await session.execute(
            select(Workflow)
            .options(selectinload(Workflow.steps))
            .where(Workflow.id == workflow_id)
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Validate and replace steps if provided
        # Keep typed StepInput objects for DAG validation and persistence.
        # `model_dump()` turns nested models into dicts.
        new_steps: list[StepInput] | None = (
            body.steps if "steps" in body.model_fields_set else None
        )
        if new_steps is not None:
            if len(new_steps) == 0:
                raise HTTPException(
                    status_code=400, detail="At least one step is required"
                )
            _validate_dag(new_steps)
            new_steps = _remap_step_ids(new_steps)

        schedule_type = updates.get("schedule_type", existing.schedule_type)
        interval_seconds = updates.get("interval_seconds", existing.interval_seconds)
        cron_expression = updates.get("cron_expression", existing.cron_expression)

        if schedule_type != "none":
            _validate_schedule_fields(schedule_type, interval_seconds, cron_expression)

        enabled = updates.get("enabled", existing.enabled)
        now = datetime.now(timezone.utc)

        next_run_at = existing.next_run_at
        if any(
            k in updates
            for k in ("schedule_type", "interval_seconds", "cron_expression")
        ):
            if enabled and schedule_type != "none":
                try:
                    next_run_at = compute_next_run_at(
                        schedule_type, interval_seconds, cron_expression
                    )
                except (ValueError, TypeError):
                    next_run_at = None
            else:
                next_run_at = None

        values: dict[str, Any] = {
            "name": updates.get("name", existing.name),
            "description": updates.get("description", existing.description),
            "schedule_type": schedule_type,
            "interval_seconds": interval_seconds,
            "cron_expression": cron_expression,
            "enabled": enabled,
            "max_run_count": updates.get("max_run_count", existing.max_run_count),
            "next_run_at": next_run_at,
            "updated_at": now,
        }

        await session.execute(
            update(Workflow).where(Workflow.id == workflow_id).values(**values)
        )

        # Replace steps if provided
        if new_steps is not None:
            await session.execute(
                delete(WorkflowStep).where(
                    WorkflowStep.workflow_id == workflow_id
                )
            )
            for step in new_steps:
                ws = WorkflowStep(
                    id=step.id,
                    workflow_id=workflow_id,
                    label=step.label,
                    task_names=json.dumps(step.task_names),
                    args=step.args or "[]",
                    kwargs=step.kwargs or "{}",
                    queue=step.queue or "celery",
                    depends_on=json.dumps(step.depends_on),
                    condition=step.condition,
                    timeout_seconds=step.timeout_seconds,
                )
                session.add(ws)

        await session.commit()

    return JSONResponse({"ok": True})


@router.delete(
    "/{workflow_id}", response_model=None, dependencies=[Depends(require_auth)]
)
async def delete_workflow(workflow_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(Workflow).where(Workflow.id == workflow_id).limit(1)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Workflow not found")
        await session.execute(
            delete(Workflow).where(Workflow.id == workflow_id)
        )
        await session.commit()
    return JSONResponse({"ok": True})


@router.post(
    "/{workflow_id}/toggle",
    response_model=None,
    dependencies=[Depends(require_auth)],
)
async def toggle_workflow(workflow_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(Workflow).where(Workflow.id == workflow_id).limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        new_enabled: bool = not existing.enabled
        now = datetime.now(timezone.utc)

        next_run_at = existing.next_run_at
        if new_enabled and existing.schedule_type != "none" and not next_run_at:
            try:
                next_run_at = compute_next_run_at(
                    existing.schedule_type,
                    existing.interval_seconds,
                    existing.cron_expression,
                )
            except (ValueError, TypeError):
                pass

        await session.execute(
            update(Workflow)
            .where(Workflow.id == workflow_id)
            .values(
                enabled=new_enabled,
                next_run_at=next_run_at if new_enabled else None,
                updated_at=now,
            )
        )
        await session.commit()

    return JSONResponse({"enabled": new_enabled})


class _DuplicateInput(CamelModel):
    name: str | None = None


@router.post(
    "/{workflow_id}/duplicate",
    response_model=None,
    dependencies=[Depends(require_auth)],
)
async def duplicate_workflow(
    workflow_id: str, body: _DuplicateInput | None = None
) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(Workflow)
            .options(selectinload(Workflow.steps))
            .where(Workflow.id == workflow_id)
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        new_workflow_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Remap step IDs so the copy is fully independent
        _id_map: dict[str, str] = _build_step_id_map(
            [step.id for step in existing.steps]
        )

        workflow = Workflow(
            id=new_workflow_id,
            name=(body.name if body and body.name else f"{existing.name} (Copy)"),
            description=existing.description,
            schedule_type=existing.schedule_type,
            interval_seconds=existing.interval_seconds,
            cron_expression=existing.cron_expression,
            enabled=False,
            max_run_count=existing.max_run_count,
            total_run_count=0,
            next_run_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(workflow)

        for step in existing.steps:
            old_deps: list[str] = json.loads(step.depends_on or "[]")
            new_deps: list[str] = [_id_map.get(d, d) for d in old_deps]
            ws = WorkflowStep(
                id=_id_map[step.id],
                workflow_id=new_workflow_id,
                label=step.label,
                task_names=step.task_names,
                args=step.args,
                kwargs=step.kwargs,
                queue=step.queue,
                depends_on=json.dumps(new_deps),
                condition=step.condition,
                timeout_seconds=step.timeout_seconds,
            )
            session.add(ws)

        await session.commit()

    return JSONResponse({"id": new_workflow_id}, status_code=201)


@router.post(
    "/{workflow_id}/run-now",
    response_model=None,
    dependencies=[Depends(require_auth)],
)
async def run_workflow_now(workflow_id: str) -> JSONResponse:
    async with get_session() as session:
        result = await session.execute(
            select(Workflow).where(Workflow.id == workflow_id).limit(1)
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

    from ..services.workflow_engine import start_workflow_run

    try:
        run_id: str = await start_workflow_run(workflow_id, trigger="manual")
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to start workflow: {exc}"
        ) from exc

    return JSONResponse({"runId": run_id}, status_code=201)


@router.get(
    "/{workflow_id}/runs", response_model=list[WorkflowRunResponse]
)
async def get_workflow_runs(
    workflow_id: str,
    limit: int = Query(50, ge=1, le=200),
) -> Any:
    async with get_session() as session:
        result = await session.execute(
            select(WorkflowRun)
            .where(WorkflowRun.workflow_id == workflow_id)
            .order_by(desc(WorkflowRun.started_at))
            .limit(limit)
        )
        return result.scalars().all()
