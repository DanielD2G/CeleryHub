# Workflow 1-node-1-task Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the multi-task `step` workflow model with a 1-node-1-task DAG: each node runs exactly one Celery task, `StepRun`+`TaskRun` collapse into a single `NodeRun`, and `depends_on`+`condition` become the sole composition mechanism — enabling per-task dependencies.

**Architecture:** Backend first (models + Alembic migration → Pydantic schemas + DAG validation → engine rewrite → event-collector wiring → router endpoints → backend tests), then frontend (types → node editor → form/dialogs → DAG view → detail/run pages). Clean break: an Alembic migration drops and recreates the workflow tables; no data migration.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL; React 19 + Vite + React Router v7 + shadcn/ui.

## Global Constraints

- Python `>=3.11`; type-annotate everything; `_` prefix for private vars/functions.
- API responses are camelCase via `CamelModel` (`alias_generator=to_camel`).
- Frontend: no `"use client"`/`"use server"`/`server-only`; `@/` alias for `./src/*`.
- Commit messages: do NOT include a `Co-Authored-By` trailer.
- Clean break: no data migration, no backward-compat with the old `steps`/`task_names` format (API or export/import).
- Domain naming: the DAG node is a `node` (`WorkflowNode`/`NodeRun`); the Celery task it runs is `taskName`. Each node runs exactly ONE task.
- `NodeRun.status` vocabulary: `pending | running | succeeded | failed | skipped`. Terminal: `succeeded | failed | skipped`.
- This change must NOT touch the event-persistence feature (`celery_events`, partitions, `event_persister`, retention) — those are independent.

---

### Task 1: Models + Alembic migration 0004

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/db/models.py`
- Create: `services/celery-gateway/migrations/versions/0004_node_model.py`

**Interfaces:**
- Produces ORM models:
  - `WorkflowNode` (table `workflow_nodes`): `id: str` PK, `workflow_id: str` FK→`workflows.id` CASCADE, `label: str`, `task_name: str`, `args: str|None`, `kwargs: str|None`, `queue: str|None`, `depends_on: str` (JSON), `condition: str`, `timeout_seconds: int|None`. Index `idx_workflow_nodes_workflow_id` on `workflow_id`.
  - `NodeRun` (table `node_runs`): `id: str` PK, `workflow_run_id: str` FK→`workflow_runs.id` CASCADE, `node_id: str`, `label: str`, `task_name: str`, `args: str|None`, `kwargs: str|None`, `queue: str|None`, `celery_task_id: str|None`, `status: str`, `error: str|None`, `started_at: datetime|None`, `finished_at: datetime|None`. Indexes `idx_node_runs_workflow_run_id` on `workflow_run_id`, `idx_node_runs_celery_task_id` on `celery_task_id`.
  - `Workflow.nodes` relationship (replaces `Workflow.steps`); `WorkflowRun.node_runs` relationship (replaces `WorkflowRun.step_runs`).
- Removes: `WorkflowStep`, `StepRun`, `TaskRun` classes.

- [ ] **Step 1: Replace the models**

In `models.py`: delete the `WorkflowStep`, `StepRun`, and `TaskRun` classes. In `Workflow`, replace the `steps` relationship with:

```python
    nodes: Mapped[list["WorkflowNode"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
```

In `WorkflowRun`, replace the `step_runs` relationship with:

```python
    node_runs: Mapped[list["NodeRun"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )
```

Add the two new classes:

```python
class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[str | None] = mapped_column(String, default="[]")
    kwargs: Mapped[str | None] = mapped_column(String, default="{}")
    queue: Mapped[str | None] = mapped_column(String, default="celery")
    depends_on: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    condition: Mapped[str] = mapped_column(
        String, nullable=False, default="all_succeeded"
    )
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, default=None)

    workflow: Mapped["Workflow"] = relationship(back_populates="nodes")

    __table_args__ = (Index("idx_workflow_nodes_workflow_id", "workflow_id"),)


class NodeRun(Base):
    __tablename__ = "node_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[str | None] = mapped_column(String, default=None)
    kwargs: Mapped[str | None] = mapped_column(String, default=None)
    queue: Mapped[str | None] = mapped_column(String, default=None)
    celery_task_id: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(String, default=None)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="node_runs")

    __table_args__ = (
        Index("idx_node_runs_workflow_run_id", "workflow_run_id"),
        Index("idx_node_runs_celery_task_id", "celery_task_id"),
    )
```

- [ ] **Step 2: Create migration `migrations/versions/0004_node_model.py`**

```python
"""1-node-1-task workflow model

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("task_runs")
    op.drop_table("step_runs")
    op.drop_table("workflow_steps")

    op.create_table(
        "workflow_nodes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.String(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("args", sa.String(), nullable=True, server_default="[]"),
        sa.Column("kwargs", sa.String(), nullable=True, server_default="{}"),
        sa.Column("queue", sa.String(), nullable=True, server_default="celery"),
        sa.Column("depends_on", sa.String(), nullable=False, server_default="[]"),
        sa.Column(
            "condition", sa.String(), nullable=False, server_default="all_succeeded"
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_workflow_nodes_workflow_id", "workflow_nodes", ["workflow_id"]
    )

    op.create_table(
        "node_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("args", sa.String(), nullable=True),
        sa.Column("kwargs", sa.String(), nullable=True),
        sa.Column("queue", sa.String(), nullable=True),
        sa.Column("celery_task_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_node_runs_workflow_run_id", "node_runs", ["workflow_run_id"])
    op.create_index("idx_node_runs_celery_task_id", "node_runs", ["celery_task_id"])


def downgrade() -> None:
    op.drop_table("node_runs")
    op.drop_table("workflow_nodes")
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.String(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("task_names", sa.String(), nullable=False, server_default="[]"),
        sa.Column("args", sa.String(), nullable=True, server_default="[]"),
        sa.Column("kwargs", sa.String(), nullable=True, server_default="{}"),
        sa.Column("queue", sa.String(), nullable=True, server_default="celery"),
        sa.Column("depends_on", sa.String(), nullable=False, server_default="[]"),
        sa.Column(
            "condition", sa.String(), nullable=False, server_default="all_succeeded"
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_workflow_steps_workflow_id", "workflow_steps", ["workflow_id"]
    )
    op.create_table(
        "step_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workflow_run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("step_label", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_step_runs_workflow_run_id", "step_runs", ["workflow_run_id"])
    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "step_run_id",
            sa.String(),
            sa.ForeignKey("step_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("args", sa.String(), nullable=True),
        sa.Column("kwargs", sa.String(), nullable=True),
        sa.Column("queue", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="SENT"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_task_runs_step_run_id", "task_runs", ["step_run_id"])
    op.create_index("idx_task_runs_task_id", "task_runs", ["task_id"])
```

- [ ] **Step 3: Apply and verify reversibility**

```bash
cd services/celery-gateway && source .venv/bin/activate
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub
alembic upgrade head && alembic downgrade 0003 && alembic upgrade head
```
Expected: all succeed, exit 0; final state at `0004`.

- [ ] **Step 4: Verify import**

Run: `python -c "from celery_gateway.db.models import WorkflowNode, NodeRun, Workflow, WorkflowRun; print('ok')"`
Expected: prints `ok`; `WorkflowStep`/`StepRun`/`TaskRun` no longer importable.

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/db/models.py services/celery-gateway/migrations/versions/0004_node_model.py
git commit -m "feat(workflows): node model (1 node = 1 task), migration 0004"
```

---

### Task 2: Pydantic schemas + DAG validation

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/models/workflows.py`
- Modify: `services/celery-gateway/src/celery_gateway/routers/workflows.py` (the `_validate_dag` and `_remap_step_ids` helpers + their call sites; full endpoint bodies are Task 5)
- Test: `services/celery-gateway/tests/api/test_workflows_router.py` (adjust existing fixtures' payloads to the new shape — see Task 6)

**Interfaces:**
- Produces:
  - `NodeInput(CamelModel)`: `id: str`, `label: str` (min_length 1), `task_name: str` (min_length 1), `args: str|None`, `kwargs: str|None`, `queue: str|None`, `depends_on: list[str]` (default empty), `condition: Literal["all_succeeded","all_completed","any_succeeded","any_failed"] = "all_succeeded"`, `timeout_seconds: int|None`. Keeps the args/kwargs JSON validators.
  - `CreateWorkflowInput.nodes: list[NodeInput]` (min_length 1) (replaces `steps`).
  - `UpdateWorkflowInput.nodes: list[NodeInput] | None` (replaces `steps`).
  - `NodeResponse(CamelModel)`: `id, label, task_name, args, kwargs, queue, depends_on, condition, timeout_seconds` (all str/optional as in the model).
  - `NodeRunResponse(CamelModel)`: `id, node_id, label, task_name, celery_task_id: str|None, status, error: str|None, started_at: datetime|None, finished_at: datetime|None`.
  - `WorkflowResponse.nodes: list[NodeResponse]` (replaces `steps`).
  - `WorkflowRunDetailResponse.node_runs: list[NodeRunResponse]` (replaces `step_runs`).
  - `WorkflowSummaryResponse.node_count: int` (replaces `step_count`).
  - `_validate_dag(nodes: list[NodeInput]) -> None` and `_remap_step_ids` renamed to `_remap_node_ids(nodes: list[NodeInput]) -> list[NodeInput]`, operating on `node.id`/`node.depends_on`.
- Removes: `StepInput`, `StepResponse`, `TaskRunResponse`, `StepRunResponse`.

- [ ] **Step 1: Rewrite the schemas in `models/workflows.py`**

Replace `StepInput` with `NodeInput`:

```python
class NodeInput(_JsonFieldMixin, CamelModel):
    id: str
    label: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    args: str | None = None
    kwargs: str | None = None
    queue: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    condition: Literal[
        "all_succeeded", "all_completed", "any_succeeded", "any_failed"
    ] = "all_succeeded"
    timeout_seconds: int | None = None
```

In `CreateWorkflowInput`: replace `steps: list[StepInput] = Field(min_length=1)` with `nodes: list[NodeInput] = Field(min_length=1)`.
In `UpdateWorkflowInput`: replace `steps: list[StepInput] | None = None` with `nodes: list[NodeInput] | None = None  # full replace if provided`.

Replace `StepResponse` with `NodeResponse`:

```python
class NodeResponse(CamelModel):
    id: str
    label: str
    task_name: str
    args: str | None
    kwargs: str | None
    queue: str | None
    depends_on: str
    condition: str
    timeout_seconds: int | None
```

In `WorkflowResponse`: replace `steps: list[StepResponse]` with `nodes: list[NodeResponse]`.
In `WorkflowSummaryResponse`: replace `step_count: int` with `node_count: int`.

Delete `TaskRunResponse` and `StepRunResponse`; replace with:

```python
class NodeRunResponse(CamelModel):
    id: str
    node_id: str
    label: str
    task_name: str
    celery_task_id: str | None
    status: str
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
```

In `WorkflowRunDetailResponse`: replace `step_runs: list[StepRunResponse]` with `node_runs: list[NodeRunResponse]`.

- [ ] **Step 2: Update `_validate_dag` and rename `_remap_step_ids` in `routers/workflows.py`**

Change `_validate_dag(steps: list[StepInput])` → `_validate_dag(nodes: list[NodeInput])`; inside, rename the local variable `steps`→`nodes` and `step`→`node` (the algorithm using `s.id`, `step.depends_on`, `step.id` becomes `n.id`, `node.depends_on`, `node.id`). Rename `_remap_step_ids(steps: list[StepInput]) -> list[StepInput]` → `_remap_node_ids(nodes: list[NodeInput]) -> list[NodeInput]` with the same id-remapping logic over `node.id`/`node.depends_on`. Update the import at the top of the router: `from ..models.workflows import (... NodeInput ...)` (drop `StepInput`).

- [ ] **Step 3: Verify schemas import and validate**

Run: `cd services/celery-gateway && source .venv/bin/activate && python -c "from celery_gateway.models.workflows import NodeInput, NodeResponse, NodeRunResponse, CreateWorkflowInput; CreateWorkflowInput(name='w', nodes=[{'id':'a','label':'A','taskName':'tasks.add'}]); print('ok')"`
Expected: prints `ok` (camelCase `taskName` accepted via alias).

- [ ] **Step 4: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/models/workflows.py services/celery-gateway/src/celery_gateway/routers/workflows.py
git commit -m "feat(workflows): node-based Pydantic schemas and DAG validation"
```

---

### Task 3: Engine rewrite

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/services/workflow_engine.py`
- Test: `services/celery-gateway/tests/service/test_workflow_engine.py` (or wherever engine tests live — search; create if absent — covered in Task 6)

**Interfaces:**
- Consumes: `WorkflowNode`, `NodeRun`, `Workflow`, `WorkflowRun` (Task 1); `dispatch_task` (unchanged).
- Produces:
  - `start_workflow_run(workflow_id, *, trigger="manual") -> str` — creates a `WorkflowRun` + one `NodeRun(status="pending")` per node (denormalizing `node_id`, `label`, `task_name`, `args`, `kwargs`, `queue`), then advances.
  - `on_task_completed(celery_uuid: str, status: str, *, error: str|None=None) -> None` — finds the `NodeRun` by `celery_task_id == celery_uuid`; if found and `running`, sets `status` to `succeeded` (Celery `SUCCESS`) or `failed` (Celery `FAILURE`), `finished_at`, `error`; cancels its timeout; advances the workflow.
  - `cancel_workflow_run(workflow_run_id) -> bool` — over `node_runs`.
  - `_advance_workflow`, `_evaluate_condition` (unchanged logic, over `NodeRun`/`WorkflowNode`), `_dispatch_node`, `_handle_node_timeout`, `_expire_node`.

- [ ] **Step 1: Rewrite `start_workflow_run`**

Replace the step-run creation loop. Load `Workflow` with `selectinload(Workflow.nodes)`, then for each node create a `NodeRun`:

```python
        for node in workflow.nodes:
            node_run = NodeRun(
                id=str(_uuid.uuid4()),
                workflow_run_id=run_id,
                node_id=node.id,
                label=node.label,
                task_name=node.task_name,
                args=node.args,
                kwargs=node.kwargs,
                queue=node.queue,
                status="pending",
            )
            session.add(node_run)
```

Update the import line to `from ..db.models import NodeRun, Workflow, WorkflowNode, WorkflowRun`.

- [ ] **Step 2: Rewrite `on_task_completed`** (no more two-level aggregation)

```python
async def on_task_completed(
    celery_uuid: str, status: str, *, error: str | None = None
) -> None:
    """Called by event_collector when a Celery task completes. Transition the
    matching NodeRun and advance the workflow."""
    workflow_run_id: str | None = None

    async with get_session() as session:
        result = await session.execute(
            select(NodeRun).where(NodeRun.celery_task_id == celery_uuid).limit(1)
        )
        node_run = result.scalar_one_or_none()
        if node_run is None or node_run.status != "running":
            return

        node_run.status = "succeeded" if status == "SUCCESS" else "failed"
        node_run.finished_at = datetime.now(timezone.utc)
        if error is not None:
            node_run.error = error
        workflow_run_id = node_run.workflow_run_id

        timeout_task = _timeout_tasks.pop(node_run.id, None)
        if timeout_task is not None:
            timeout_task.cancel()

        await session.commit()

    if workflow_run_id:
        await _advance_workflow(workflow_run_id)
```

- [ ] **Step 3: Rewrite `_advance_workflow`** to use `node_runs`/`WorkflowNode`

Mirror the existing structure but: load `selectinload(WorkflowRun.node_runs)` (no nested task_runs); load node defs via `select(WorkflowNode).where(WorkflowNode.workflow_id == wf_run.workflow_id)`; build `node_run_by_node_id = {nr.node_id: nr for nr in wf_run.node_runs}`; iterate `wf_run.node_runs` (variable `nr`), checking `nr.status == "pending"`, dependencies via `json.loads(node_def.depends_on or "[]")`, dependency terminality against `_TERMINAL_STEP_STATUSES` (rename constant to `_TERMINAL_NODE_STATUSES = frozenset({"succeeded","failed","skipped"})`), and dispatch via `_dispatch_node(session, nr, node_def)`. The completion check sets `wf_run.status` from `nr.status` over `node_runs`. Keep the `_get_run_lock`/`_cleanup_run_lock` machinery unchanged.

- [ ] **Step 4: Rewrite `_dispatch_step` → `_dispatch_node`** (one task per node)

```python
async def _dispatch_node(
    session: AsyncSession, node_run: NodeRun, node_def: WorkflowNode
) -> None:
    """Dispatch the single task for a node."""
    node_run.status = "running"
    node_run.started_at = datetime.now(timezone.utc)

    args: list[Any] = json.loads(node_def.args or "[]")
    kwargs: dict[str, Any] = json.loads(node_def.kwargs or "{}")
    queue: str = node_def.queue or "celery"

    try:
        celery_task_id = await dispatch_task(
            node_def.task_name, args, kwargs, queue
        )
        node_run.celery_task_id = celery_task_id
    except Exception as exc:
        node_run.status = "failed"
        node_run.error = str(exc)
        node_run.finished_at = datetime.now(timezone.utc)
        return

    if (
        node_def.timeout_seconds
        and node_def.timeout_seconds > 0
        and node_run.status == "running"
    ):
        _timeout_tasks[node_run.id] = asyncio.create_task(
            _handle_node_timeout(
                node_run.id, node_run.workflow_run_id, node_def.timeout_seconds
            )
        )
```

- [ ] **Step 5: Rewrite timeout + cancel helpers**

`_handle_step_timeout` → `_handle_node_timeout(node_run_id, workflow_run_id, timeout_seconds)` (same body, calls `_expire_node`). `_expire_step` → `_expire_node`: load `NodeRun` by id, if `status == "running"` set `status="failed"`, `error=f"Node timed out after {timeout_seconds}s"`, `finished_at`, commit, pop the timeout task, then `_advance_workflow`. In `cancel_workflow_run`: `selectinload(WorkflowRun.node_runs)`; iterate `wf_run.node_runs` (variable `nr`), set pending/running → `skipped` with `finished_at`, pop each `_timeout_tasks.get(nr.id)`. Rename the module constant `_TERMINAL_STEP_STATUSES` → `_TERMINAL_NODE_STATUSES` and delete `_TERMINAL_TASK_STATUSES` (no longer needed). `_evaluate_condition(condition, dep_node_runs)` keeps its body (status compares unchanged).

- [ ] **Step 6: Run engine tests**

Run: `cd services/celery-gateway && source .venv/bin/activate && pytest tests/service/test_workflow_engine.py -v` (after Task 6 updates them) — for now: `python -c "import celery_gateway.services.workflow_engine"` to confirm it imports.
Expected: import OK; full engine tests are validated in Task 6.

- [ ] **Step 7: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/workflow_engine.py
git commit -m "feat(workflows): rewrite engine for 1-node-1-task model"
```

---

### Task 4: Event-collector wiring

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/services/event_collector.py`

**Interfaces:**
- Consumes: `on_task_completed(celery_uuid, status, *, error=None)` (Task 3).
- Produces: `_update_run_status(task_uuid, status, *, error=None)` simplified to delegate to `on_task_completed` (the `NodeRun` transition + workflow advance now live entirely in the engine; the collector no longer writes `TaskRun` directly).

- [ ] **Step 1: Simplify `_update_run_status`**

Replace its body (which currently updates `TaskRun` then calls `on_task_completed`) with a thin delegation, preserving the existing call sites in `_persist_event` (`task-succeeded` → `_update_run_status(uuid, "SUCCESS")`, `task-failed` → `_update_run_status(uuid, "FAILURE", error=...)`):

```python
async def _update_run_status(
    task_uuid: str, status: str, *, error: str | None = None
) -> None:
    """Advance any workflow node waiting on this Celery task."""
    try:
        from .workflow_engine import on_task_completed

        await on_task_completed(task_uuid, status, error=error)
    except Exception as exc:
        logger.warning(
            "[CeleryHub EventCollector] Workflow engine error for %s: %s",
            task_uuid,
            exc,
        )
```

Remove the now-unused `from ..db.models import TaskRun` import and the `update`/`get_session` imports if they are no longer used elsewhere in the file (check: `get_session` may still be patched in tests but is no longer referenced here — remove the import if unused, and remove the corresponding `patch("celery_gateway.services.event_collector.get_session", ...)` line from conftest in Task 6 if it now patches a nonexistent attribute). The `sqlalchemy update` import: remove if unused.

- [ ] **Step 2: Verify import**

Run: `cd services/celery-gateway && source .venv/bin/activate && python -c "import celery_gateway.services.event_collector"`
Expected: imports cleanly (no reference to removed `TaskRun`).

- [ ] **Step 3: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/event_collector.py
git commit -m "feat(workflows): event collector advances node runs via engine"
```

---

### Task 5: Router endpoints

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/routers/workflows.py`

**Interfaces:**
- Consumes: `NodeInput`, response schemas, `_validate_dag`/`_remap_node_ids` (Task 2); `WorkflowNode`/`NodeRun` (Task 1).
- Produces: all workflow endpoints operating on nodes — `list_workflows` (nodeCount via `WorkflowNode`), `create_workflow`, `update_workflow`, `get_workflow_run_detail` (node_runs), and the import/export path.

- [ ] **Step 1: Update imports and `list_workflows`**

Top import: `from ..db.models import NodeRun, Workflow, WorkflowNode, WorkflowRun` (drop `StepRun`, `WorkflowStep`). In `list_workflows`: replace `func.count(WorkflowStep.id).label("step_count")` → `func.count(WorkflowNode.id).label("node_count")`, the `outerjoin(WorkflowStep, WorkflowStep.workflow_id == Workflow.id)` → `outerjoin(WorkflowNode, WorkflowNode.workflow_id == Workflow.id)`, and the response dict key `"step_count": step_count` → `"node_count": node_count` (rename the unpacked loop var accordingly).

- [ ] **Step 2: Update `create_workflow`**

`_validate_dag(body.nodes)`; `nodes = _remap_node_ids(body.nodes)`. Replace the `for step in steps` loop with:

```python
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
            )
            session.add(wn)
```

- [ ] **Step 3: Update `update_workflow`**

`selectinload(Workflow.nodes)`; `new_nodes = body.nodes if "nodes" in body.model_fields_set else None`; the empty-check message → `"At least one node is required"`; `_validate_dag(new_nodes)`; `new_nodes = _remap_node_ids(new_nodes)`. Replace the delete+recreate block:

```python
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
                )
                session.add(wn)
```

- [ ] **Step 4: Update `get_workflow_run_detail` and any import/export path**

`get_workflow_run_detail`: `selectinload(WorkflowRun.node_runs)` (drop the nested `.selectinload(StepRun.task_runs)`); the returned object now serializes via `WorkflowRunDetailResponse` (node_runs). For the workflow detail endpoint that returns `WorkflowResponse`, ensure it loads `selectinload(Workflow.nodes)` and serializes `nodes`. For the import path (around the old line 491 that read `step.task_names`), change it to construct `WorkflowNode(... task_name=node.task_name ...)` from the imported `NodeInput` list; the import payload now uses `nodes`/`taskName`.

- [ ] **Step 5: Verify the app imports and OpenAPI builds**

Run: `cd services/celery-gateway && source .venv/bin/activate && python -c "from celery_gateway.main import app; print(len(app.routes))"`
Expected: prints a number, no import error.

- [ ] **Step 6: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/routers/workflows.py
git commit -m "feat(workflows): node-based workflow endpoints"
```

---

### Task 6: Backend tests

**Files:**
- Modify: `services/celery-gateway/tests/conftest.py` (remove the `event_collector.get_session` patch only if Task 4 removed that import; keep `workflow_engine.get_session` patch)
- Modify: `services/celery-gateway/tests/api/test_workflows_router.py`
- Modify/Create: `services/celery-gateway/tests/service/test_workflow_engine.py`

**Interfaces:**
- Consumes: the new node API + engine.

- [ ] **Step 1: Update conftest patches**

If Task 4 removed `get_session` usage from `event_collector`, delete the line `patch("celery_gateway.services.event_collector.get_session", _override_get_session),` from the `db_session` fixture (patching a now-absent attribute raises). Keep `patch("celery_gateway.services.workflow_engine.get_session", _override_get_session),`. Run `pytest tests/api/test_workflows_router.py -q` after edits to confirm the fixture still imports.

- [ ] **Step 2: Update router tests to the node shape**

In `tests/api/test_workflows_router.py`, change every workflow-create payload from `"steps": [{"taskNames": [...], ...}]` to `"nodes": [{"taskName": "...", ...}]`, and every assertion reading `step_count`/`steps`/`stepRuns`/`taskRuns` to `nodeCount`/`nodes`/`nodeRuns`. Add a test asserting a node depends on another node (per-node dependency):

```python
@pytest.mark.asyncio
async def test_create_workflow_with_node_dependency(client):
    payload = {
        "name": "wf",
        "nodes": [
            {"id": "a", "label": "A", "taskName": "tasks.a"},
            {"id": "b", "label": "B", "taskName": "tasks.b", "dependsOn": ["a"]},
        ],
    }
    resp = await client.post("/api/workflows", json=payload)
    assert resp.status_code == 201
```

Keep the existing DAG-validation tests (cycle, self-dep, unknown dep) but with the `nodes`/`taskName` shape.

- [ ] **Step 3: Engine tests (TDD-style, real Postgres via `db_session`)**

Write `tests/service/test_workflow_engine.py` covering: (a) `start_workflow_run` creates one `NodeRun` per node in `pending`; (b) a root node (no deps) is dispatched (`running`, `celery_task_id` set) — patch `dispatch_task` to return a fake id; (c) `on_task_completed(fake_id, "SUCCESS")` transitions the node to `succeeded` and dispatches its dependent; (d) `condition="any_failed"` gating; (e) a node whose dependency failed under `all_succeeded` is `skipped`; (f) workflow run reaches `succeeded`/`failed` terminal correctly. Patch `dispatch_task` via `patch("celery_gateway.services.workflow_engine.dispatch_task", AsyncMock(return_value="celery-uuid-1"))`. Example skeleton for (a)+(b):

```python
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from celery_gateway.db import get_session
from celery_gateway.db.models import Workflow, WorkflowNode, NodeRun
from celery_gateway.services.workflow_engine import start_workflow_run


async def _make_workflow(node_specs):
    import uuid as u
    from datetime import datetime, timezone
    wid = str(u.uuid4())
    async with get_session() as s:
        s.add(Workflow(id=wid, name="w", schedule_type="none", enabled=True,
                       total_run_count=0, created_at=datetime.now(timezone.utc),
                       updated_at=datetime.now(timezone.utc)))
        for spec in node_specs:
            s.add(WorkflowNode(id=spec["id"], workflow_id=wid, label=spec["id"],
                               task_name=spec["task_name"], depends_on=spec.get("depends_on", "[]"),
                               condition=spec.get("condition", "all_succeeded")))
        await s.commit()
    return wid


@pytest.mark.asyncio
async def test_root_node_dispatched(db_session):
    wid = await _make_workflow([{"id": "a", "task_name": "tasks.a"}])
    with patch("celery_gateway.services.workflow_engine.dispatch_task",
               AsyncMock(return_value="celery-1")):
        run_id = await start_workflow_run(wid)
    async with get_session() as s:
        nr = (await s.execute(select(NodeRun).where(NodeRun.workflow_run_id == run_id))).scalar_one()
    assert nr.status == "running"
    assert nr.celery_task_id == "celery-1"
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd services/celery-gateway && source .venv/bin/activate && pytest -q`
Expected: all green. Fix any remaining `step`-era references surfaced by failures (do not weaken assertions).

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/tests
git commit -m "test(workflows): node-model engine and router tests"
```

---

### Task 7: Frontend types + API client

**Files:**
- Modify: `packages/web/src/lib/workflow-utils.tsx`
- Modify: any API client/types module the workflow pages import (search for `taskNames`, `stepRuns`, `stepCount`, `steps` under `packages/web/src`)

**Interfaces:**
- Produces: TS types `WorkflowNode` (`{ id, label, taskName, args, kwargs, queue, dependsOn, condition, timeoutSeconds }`), `NodeRun` (`{ id, nodeId, label, taskName, celeryTaskId, status, error, startedAt, finishedAt }`), `Workflow.nodes`, `WorkflowRunDetail.nodeRuns`, `WorkflowSummary.nodeCount`. Replaces `Step`/`StepRun`/`taskNames`/`stepCount`.

- [ ] **Step 1: Find every reference**

Run: `cd packages/web && grep -rn "taskNames\|stepRuns\|stepCount\|step_runs\|\.steps\b\|StepRun\|StepEditorState" src`
Record the list — these are the edit sites for Tasks 7–11.

- [ ] **Step 2: Update the type definitions**

In `workflow-utils.tsx` (and any shared types module), rename the `Step` type to `WorkflowNode` with `taskName: string` (was `taskNames: string[]`), rename `stepRuns`→`nodeRuns`, `stepCount`→`nodeCount`, `steps`→`nodes`, and the run type to `NodeRun` with `nodeId`, `celeryTaskId`. Update any helper functions (e.g. DAG layout, status color) that read these fields.

- [ ] **Step 3: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit`
Expected: errors only in the component files updated in Tasks 8–11 (expected until those are done). Confirm `workflow-utils.tsx` itself has no errors.

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/lib/workflow-utils.tsx
git commit -m "feat(web): node-based workflow types"
```

---

### Task 8: Node editor (single task)

**Files:**
- Modify: `packages/web/src/components/workflows/workflow-step-editor.tsx` (rename to `workflow-node-editor.tsx`)

**Interfaces:**
- Consumes: `WorkflowNode` type (Task 7).
- Produces: a node editor whose state holds a single `taskName: string` (replacing `taskNames: string[]`), exposing `NodeEditorState`.

- [ ] **Step 1: Convert multi-select to single select**

Rename the file to `workflow-node-editor.tsx` and the exported component to `WorkflowNodeEditor`. Change `StepEditorState` → `NodeEditorState` with `taskName: string` instead of `taskNames: string[]`. Replace the multi-add task UI (the `availableTasks` add/remove badge list) with a single task autocomplete/select that sets `taskName`. Keep the `dependsOn`, `condition`, `queue`, args/kwargs, and `timeoutSeconds` controls unchanged. Update the props type name (`WorkflowNodeEditorProps`) and `otherSteps`→`otherNodes`.

- [ ] **Step 2: Typecheck the file**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep node-editor || echo "node-editor clean"`
Expected: no errors originating in `workflow-node-editor.tsx`.

- [ ] **Step 3: Commit**

```bash
git add packages/web/src/components/workflows/
git commit -m "feat(web): single-task node editor"
```

---

### Task 9: Workflow form + create/import dialogs

**Files:**
- Modify: `packages/web/src/components/workflows/workflow-form.tsx`
- Modify: `packages/web/src/components/workflows/create-workflow-dialog.tsx`
- Modify: `packages/web/src/components/workflows/import-workflow-dialog.tsx`

**Interfaces:**
- Consumes: `WorkflowNodeEditor` + `NodeEditorState` (Task 8), node types (Task 7).

- [ ] **Step 1: Update the form to manage nodes**

In `workflow-form.tsx`: the list of editors now manages `NodeEditorState[]` (each with one `taskName`); the "add step" action adds a node; the submit payload sends `nodes: [{ id, label, taskName, args, kwargs, queue, dependsOn, condition, timeoutSeconds }]` (was `steps`/`taskNames`). Update create/import dialogs to the same payload shape; the import dialog parses JSON with `nodes`/`taskName` (reject the old `steps`/`taskNames` format with a clear validation message).

- [ ] **Step 2: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep -E "workflow-form|create-workflow|import-workflow" || echo "forms clean"`
Expected: no errors in these three files.

- [ ] **Step 3: Commit**

```bash
git add packages/web/src/components/workflows/
git commit -m "feat(web): node-based workflow form and dialogs"
```

---

### Task 10: DAG visualization

**Files:**
- Modify: `packages/web/src/components/workflows/workflow-dag.tsx`
- Modify: `packages/web/src/components/workflows/workflow-dag-node.tsx`
- Modify: `packages/web/src/components/workflows/workflow-dag-edge.tsx`

**Interfaces:**
- Consumes: node types (Task 7).

- [ ] **Step 1: Render one task per node**

In the DAG components: each node now displays a single `taskName` (remove any rendering that iterated `taskNames`). Edges are built from `dependsOn` (unchanged). Node status coloring reads the `NodeRun.status` vocabulary (`pending|running|succeeded|failed|skipped`). Update field accesses `steps`→`nodes`, `stepRuns`→`nodeRuns`.

- [ ] **Step 2: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep dag || echo "dag clean"`
Expected: no errors in the DAG files.

- [ ] **Step 3: Commit**

```bash
git add packages/web/src/components/workflows/
git commit -m "feat(web): node-based DAG visualization"
```

---

### Task 11: Detail/run pages + build

**Files:**
- Modify: `packages/web/src/pages/WorkflowDetailPage.tsx`
- Modify: `packages/web/src/pages/WorkflowRunPage.tsx`
- Modify: `packages/web/src/components/workflows/workflow-run-history.tsx`
- Modify: `packages/web/src/components/workflows/workflow-detail-client.tsx`, `workflow-table.tsx` (if they read `stepCount`/`steps`)

**Interfaces:**
- Consumes: node types (Task 7).

- [ ] **Step 1: Update pages to nodeRuns**

Replace the two-level step→tasks rendering with a single `nodeRuns` list (one status row per node): each row shows `label`, `taskName`, `status`, `celeryTaskId`, timings. `workflow-table.tsx` shows `nodeCount`. Remove any rendering that expanded a step into its task runs.

- [ ] **Step 2: Full typecheck + build**

Run: `cd packages/web && npx tsc -b --noEmit && npx vite build`
Expected: typecheck clean (zero errors), build succeeds.

- [ ] **Step 3: Commit**

```bash
git add packages/web/src
git commit -m "feat(web): node-based workflow detail and run pages"
```

---

## Verification (end of plan)

- [ ] Backend: `cd services/celery-gateway && pytest -q` green; `alembic upgrade head` reaches `0004`; `alembic downgrade 0003 && alembic upgrade head` works.
- [ ] `grep -rn "WorkflowStep\|StepRun\|TaskRun\|task_names" services/celery-gateway/src` returns nothing (event-persistence `celery_events`/`CeleryEvent` untouched and unrelated).
- [ ] Frontend: `cd packages/web && npx tsc -b --noEmit && npx vite build` clean.
- [ ] `grep -rn "taskNames\|stepRuns\|stepCount" packages/web/src` returns nothing.
- [ ] Manual smoke (optional): create a workflow with node B depending on node A, run it, observe A runs, completes, then B dispatches — one status row per node.
