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
from ..db.models import NodeRun, Workflow, WorkflowNode, WorkflowRun
from ..middleware.auth import require_auth
from ..models.base import CamelModel

from ..models.workflows import (
    CreateWorkflowInput,
    NodeInput,
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


def _validate_dag(nodes: list[NodeInput]) -> None:
    """Validate that nodes form a valid DAG using Kahn's algorithm."""
    node_ids: set[str] = {n.id for n in nodes}

    # Check for duplicates
    if len(node_ids) != len(nodes):
        raise HTTPException(status_code=400, detail="Duplicate node IDs found")

    # Build adjacency and in-degree
    in_degree: dict[str, int] = {n.id: 0 for n in nodes}
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}

    for node in nodes:
        for dep_id in node.depends_on:
            if dep_id == node.id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Node '{node.id}' cannot depend on itself",
                )
            if dep_id not in node_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Node '{node.id}' depends on unknown node '{dep_id}'",
                )
            adjacency[dep_id].append(node.id)
            in_degree[node.id] += 1

    # At least one root node
    roots: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
    if not roots:
        raise HTTPException(
            status_code=400, detail="At least one root node (no dependencies) required"
        )

    # Kahn's algorithm
    queue: deque[str] = deque(roots)
    visited: int = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in adjacency[current]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if visited < len(nodes):
        raise HTTPException(status_code=400, detail="Cycle detected in node dependencies")


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


def _build_node_id_map(node_ids: list[str]) -> dict[str, str]:
    """Map client-provided node IDs to server-generated UUIDs."""
    return {nid: str(uuid.uuid4()) for nid in node_ids}


def _remap_node_ids(nodes: list[NodeInput]) -> list[NodeInput]:
    """Replace client-provided node IDs with server-generated UUIDs."""
    id_map = _build_node_id_map([n.id for n in nodes])
    return [
        node.model_copy(update={
            "id": id_map[node.id],
            "depends_on": [id_map.get(d, d) for d in node.depends_on],
        })
        for node in nodes
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
                func.count(WorkflowNode.id).label("node_count"),
            )
            .outerjoin(WorkflowNode, WorkflowNode.workflow_id == Workflow.id)
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
                    "node_count": node_count,
                }
            )
            for wf, node_count in rows
        ]


@router.post("", response_model=None, dependencies=[Depends(require_auth)])
async def create_workflow(body: CreateWorkflowInput) -> JSONResponse:
    _validate_dag(body.nodes)
    nodes = _remap_node_ids(body.nodes)

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

        for node in nodes:
            wn = WorkflowNode(
                id=node.id,
                workflow_id=workflow_id,
                label=node.label,
                task_name=node.task_name,
                args=node.args or "[]",
                kwargs=node.kwargs or "{}",
                queue=node.queue or "celery",
                depends_on=json.dumps(node.depends_on),
                condition=node.condition,
                timeout_seconds=node.timeout_seconds,
                position_x=node.position_x,
                position_y=node.position_y,
            )
            session.add(wn)

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
                selectinload(WorkflowRun.node_runs)
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
            .options(selectinload(Workflow.nodes))
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
            .options(selectinload(Workflow.nodes))
            .where(Workflow.id == workflow_id)
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Validate and replace nodes if provided
        new_nodes: list[NodeInput] | None = (
            body.nodes if "nodes" in body.model_fields_set else None
        )
        if new_nodes is not None:
            if len(new_nodes) == 0:
                raise HTTPException(
                    status_code=400, detail="At least one node is required"
                )
            _validate_dag(new_nodes)
            new_nodes = _remap_node_ids(new_nodes)

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

        # Replace nodes if provided
        if new_nodes is not None:
            await session.execute(
                delete(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id)
            )
            for node in new_nodes:
                wn = WorkflowNode(
                    id=node.id,
                    workflow_id=workflow_id,
                    label=node.label,
                    task_name=node.task_name,
                    args=node.args or "[]",
                    kwargs=node.kwargs or "{}",
                    queue=node.queue or "celery",
                    depends_on=json.dumps(node.depends_on),
                    condition=node.condition,
                    timeout_seconds=node.timeout_seconds,
                    position_x=node.position_x,
                    position_y=node.position_y,
                )
                session.add(wn)

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
            .options(selectinload(Workflow.nodes))
            .where(Workflow.id == workflow_id)
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        new_workflow_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Remap node IDs so the copy is fully independent
        _id_map: dict[str, str] = _build_node_id_map(
            [node.id for node in existing.nodes]
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

        for node in existing.nodes:
            old_deps: list[str] = json.loads(node.depends_on or "[]")
            new_deps: list[str] = [_id_map.get(d, d) for d in old_deps]
            wn = WorkflowNode(
                id=_id_map[node.id],
                workflow_id=new_workflow_id,
                label=node.label,
                task_name=node.task_name,
                args=node.args,
                kwargs=node.kwargs,
                queue=node.queue,
                depends_on=json.dumps(new_deps),
                condition=node.condition,
                timeout_seconds=node.timeout_seconds,
            )
            session.add(wn)

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
