# Workflows como secuencia de pasos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la edición de un DAG arbitrario por una lista ordenada de pasos, generando `depends_on` automáticamente en el backend.

**Architecture:** El modelo de autoría pasa a ser `stage: int` por nodo. El backend deriva `depends_on` al guardar (cada nodo depende de todos los del paso anterior) y lo persiste, así que el engine no se toca. El frontend cambia el canvas editable por una lista de pasos, y deja el canvas como vista de sólo lectura generada con dagre.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + pytest (backend); React 19 + Vite + @xyflow/react + vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-07-30-workflow-linear-stages-design.md`

## Global Constraints

- Python: tipar todo; prefijo `_` para funciones y variables privadas.
- Python: respuestas de API en camelCase vía Pydantic `alias_generator=to_camel` (usar `CamelModel`).
- Frontend: alias `@/` para `./src/*`. Sin `"use client"` / `"use server"` / `import "server-only"`.
- Commits: **sin** línea `Co-Authored-By`.
- Backend tests: `cd services/celery-gateway && .venv/bin/pytest tests/ -v` (o `make test` desde la raíz).
- Frontend tests: `cd packages/web && npx vitest run`.
- El engine (`services/workflow_engine.py`) **no se modifica en ninguna tarea**. Si una tarea parece pedirlo, está mal entendida.

---

## Fase 1 — Backend

### Task 1: Funciones puras de stages

Módulo nuevo, sin dependencias de DB ni de FastAPI. Es el corazón de todo el cambio.

**Files:**
- Create: `services/celery-gateway/src/celery_gateway/services/workflow_stages.py`
- Test: `services/celery-gateway/tests/unit/test_workflow_stages.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `normalize_stages(stages: list[int]) -> list[int]`
  - `depends_on_from_stages(node_ids: list[str], stages: list[int]) -> list[list[str]]`
  - `stages_from_depends_on(node_ids: list[str], depends_on: list[list[str]]) -> list[int]`

- [ ] **Step 1: Write the failing tests**

Crear `services/celery-gateway/tests/unit/test_workflow_stages.py`:

```python
from __future__ import annotations

from celery_gateway.services.workflow_stages import (
    depends_on_from_stages,
    normalize_stages,
    stages_from_depends_on,
)


def test_normalize_stages_reindexes_to_contiguous() -> None:
    assert normalize_stages([0, 5, 5, 9]) == [0, 1, 1, 2]


def test_normalize_stages_leaves_contiguous_untouched() -> None:
    assert normalize_stages([0, 1, 1, 2]) == [0, 1, 1, 2]


def test_normalize_stages_handles_empty() -> None:
    assert normalize_stages([]) == []


def test_depends_on_stage_zero_has_no_dependencies() -> None:
    assert depends_on_from_stages(["a"], [0]) == [[]]


def test_depends_on_chains_sequential_stages() -> None:
    result = depends_on_from_stages(["a", "b", "c"], [0, 1, 2])
    assert result == [[], ["a"], ["b"]]


def test_depends_on_fans_in_from_a_parallel_stage() -> None:
    # a en el paso 0; b y c en paralelo en el 1; d espera a los dos
    result = depends_on_from_stages(["a", "b", "c", "d"], [0, 1, 1, 2])
    assert result == [[], ["a"], ["a"], ["b", "c"]]


def test_depends_on_normalizes_gaps_in_stage_numbers() -> None:
    # los pasos 0 y 7 son consecutivos una vez normalizados
    result = depends_on_from_stages(["a", "b"], [0, 7])
    assert result == [[], ["a"]]


def test_depends_on_handles_empty_workflow() -> None:
    assert depends_on_from_stages([], []) == []


def test_stages_from_depends_on_linear_chain() -> None:
    assert stages_from_depends_on(["a", "b", "c"], [[], ["a"], ["b"]]) == [0, 1, 2]


def test_stages_from_depends_on_parallel_nodes_share_a_stage() -> None:
    assert stages_from_depends_on(["a", "b", "c"], [[], ["a"], ["a"]]) == [0, 1, 1]


def test_stages_from_depends_on_uses_longest_path() -> None:
    # d depende de a (nivel 0) y de c (nivel 2) -> d cae en el nivel 3
    node_ids = ["a", "b", "c", "d"]
    depends_on = [[], ["a"], ["b"], ["a", "c"]]
    assert stages_from_depends_on(node_ids, depends_on) == [0, 1, 2, 3]


def test_stages_from_depends_on_ignores_unknown_dependencies() -> None:
    assert stages_from_depends_on(["a"], [["ghost"]]) == [0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/celery-gateway && .venv/bin/pytest tests/unit/test_workflow_stages.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'celery_gateway.services.workflow_stages'`

- [ ] **Step 3: Write the implementation**

Crear `services/celery-gateway/src/celery_gateway/services/workflow_stages.py`:

```python
"""Derivación entre la lista de pasos (autoría) y depends_on (ejecución).

El usuario edita una secuencia de pasos; el engine sólo entiende depends_on.
Este módulo traduce en ambas direcciones y no toca DB ni HTTP.
"""

from __future__ import annotations


def normalize_stages(stages: list[int]) -> list[int]:
    """Reindexa números de paso arbitrarios a 0..N-1 contiguos.

    Permite que el cliente mande huecos (0, 7, 9) sin que los nodos del paso 7
    queden sin dependencias por no existir el paso 6.
    """
    ordered: list[int] = sorted(set(stages))
    remap: dict[int, int] = {stage: index for index, stage in enumerate(ordered)}
    return [remap[stage] for stage in stages]


def depends_on_from_stages(
    node_ids: list[str], stages: list[int]
) -> list[list[str]]:
    """depends_on de cada nodo = todos los nodos del paso anterior.

    Devuelve una lista paralela a node_ids. Los nodos del primer paso quedan
    con lista vacía, o sea raíces que se despachan de entrada.
    """
    normalized: list[int] = normalize_stages(stages)

    by_stage: dict[int, list[str]] = {}
    for node_id, stage in zip(node_ids, normalized):
        by_stage.setdefault(stage, []).append(node_id)

    return [by_stage.get(stage - 1, []) for stage in normalized]


def stages_from_depends_on(
    node_ids: list[str], depends_on: list[list[str]]
) -> list[int]:
    """Nivel topológico de cada nodo: el camino más largo desde una raíz.

    Se usa para migrar DAGs existentes y para importar JSON del formato viejo.
    Un DAG que ya es por capas da el mismo grafo; uno que no lo es hace que
    algún nodo espere de más — nunca de menos.
    """
    deps_by_id: dict[str, list[str]] = dict(zip(node_ids, depends_on))
    known: set[str] = set(node_ids)
    level_by_id: dict[str, int] = {}

    def _level(node_id: str, seen: frozenset[str]) -> int:
        if node_id in level_by_id:
            return level_by_id[node_id]
        if node_id in seen:
            # Ciclo: no debería existir (la API valida el DAG), pero no colgamos
            return 0
        deps: list[str] = [d for d in deps_by_id.get(node_id, []) if d in known]
        level: int = (
            0
            if not deps
            else 1 + max(_level(dep, seen | {node_id}) for dep in deps)
        )
        level_by_id[node_id] = level
        return level

    return [_level(node_id, frozenset()) for node_id in node_ids]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/celery-gateway && .venv/bin/pytest tests/unit/test_workflow_stages.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/services/workflow_stages.py services/celery-gateway/tests/unit/test_workflow_stages.py
git commit -m "feat(gateway): pure stage <-> depends_on derivation"
```

---

### Task 2: Columna `stage` en el modelo y migración

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/db/models.py:58-70` (clase `WorkflowNode`)
- Create: `services/celery-gateway/migrations/versions/0006_node_stages.py`

**Interfaces:**
- Consumes: `stages_from_depends_on` de Task 1 (para poblar el valor inicial).
- Produces: `WorkflowNode.stage: int` y `WorkflowNode.stage_label: str | None`.

- [ ] **Step 1: Add the columns to the SQLAlchemy model**

En `services/celery-gateway/src/celery_gateway/db/models.py`, dentro de `WorkflowNode`, justo después de la línea `timeout_seconds: Mapped[int | None] = mapped_column(Integer, default=None)`:

```python
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage_label: Mapped[str | None] = mapped_column(String, default=None)
```

- [ ] **Step 2: Write the migration**

Crear `services/celery-gateway/migrations/versions/0006_node_stages.py`:

```python
"""node stages

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30
"""
import json

from alembic import op
import sqlalchemy as sa

from celery_gateway.services.workflow_stages import stages_from_depends_on

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_nodes",
        sa.Column("stage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "workflow_nodes", sa.Column("stage_label", sa.String(), nullable=True)
    )

    # Derivar el stage de los workflows existentes por nivel topológico
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, workflow_id, depends_on FROM workflow_nodes")
    ).fetchall()

    by_workflow: dict[str, list[tuple[str, list[str]]]] = {}
    for node_id, workflow_id, raw_depends_on in rows:
        deps = json.loads(raw_depends_on or "[]")
        by_workflow.setdefault(workflow_id, []).append((node_id, deps))

    for nodes in by_workflow.values():
        node_ids = [node_id for node_id, _ in nodes]
        depends = [deps for _, deps in nodes]
        for node_id, stage in zip(node_ids, stages_from_depends_on(node_ids, depends)):
            conn.execute(
                sa.text("UPDATE workflow_nodes SET stage = :stage WHERE id = :id"),
                {"stage": stage, "id": node_id},
            )


def downgrade() -> None:
    op.drop_column("workflow_nodes", "stage_label")
    op.drop_column("workflow_nodes", "stage")
```

- [ ] **Step 3: Run the existing test suite to verify nothing broke**

Run: `cd services/celery-gateway && .venv/bin/pytest tests/ -v`
Expected: PASS — las suites existentes crean las tablas desde los modelos, así que la columna nueva con default 0 no rompe nada.

- [ ] **Step 4: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/db/models.py services/celery-gateway/migrations/versions/0006_node_stages.py
git commit -m "feat(gateway): add stage columns to workflow_nodes"
```

---

### Task 3: API — aceptar `stage`, rechazar `dependsOn`, generar al guardar

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/models/workflows.py:30-44` (`NodeInput`), `:73-85` (`NodeResponse`)
- Modify: `services/celery-gateway/src/celery_gateway/routers/workflows.py:123-132` (`_remap_node_ids`), `:171-172` y el bloque de persistencia de nodos en create y update
- Test: `services/celery-gateway/tests/api/test_workflows_router.py`

**Interfaces:**
- Consumes: `depends_on_from_stages` de Task 1; `WorkflowNode.stage` / `.stage_label` de Task 2.
- Produces: `NodeInput.stage: int`, `NodeInput.stage_label: str | None`; `NodeResponse.stage`, `.stage_label`; helper `_apply_generated_depends_on(nodes: list[NodeInput]) -> list[NodeInput]` en el router.

- [ ] **Step 1: Write the failing tests**

Agregar al final de `services/celery-gateway/tests/api/test_workflows_router.py`:

```python
def _staged_node(
    label: str,
    task_name: str,
    stage: int,
    stage_label: str | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "label": label,
        "taskName": task_name,
        "stage": stage,
    }
    if stage_label is not None:
        node["stageLabel"] = stage_label
    return node


@pytest.mark.asyncio
async def test_create_generates_depends_on_from_stages(client: AsyncClient) -> None:
    nodes = [
        _staged_node("uno", "tasks.a", 0),
        _staged_node("dos", "tasks.b", 1, stage_label="Scrapers"),
        _staged_node("tres", "tasks.c", 1, stage_label="Scrapers"),
        _staged_node("cuatro", "tasks.d", 2),
    ]
    created = await _create_interval_workflow(client, nodes=nodes)

    resp = await client.get(f"/api/workflows/{created['id']}")
    body = resp.json()
    by_label = {n["label"]: n for n in body["nodes"]}

    assert json.loads(by_label["uno"]["dependsOn"]) == []
    assert json.loads(by_label["dos"]["dependsOn"]) == [by_label["uno"]["id"]]
    assert json.loads(by_label["tres"]["dependsOn"]) == [by_label["uno"]["id"]]
    assert sorted(json.loads(by_label["cuatro"]["dependsOn"])) == sorted(
        [by_label["dos"]["id"], by_label["tres"]["id"]]
    )


@pytest.mark.asyncio
async def test_create_round_trips_stage_and_label(client: AsyncClient) -> None:
    nodes = [
        _staged_node("uno", "tasks.a", 0),
        _staged_node("dos", "tasks.b", 1, stage_label="Scrapers"),
    ]
    created = await _create_interval_workflow(client, nodes=nodes)

    body = (await client.get(f"/api/workflows/{created['id']}")).json()
    by_label = {n["label"]: n for n in body["nodes"]}

    assert by_label["uno"]["stage"] == 0
    assert by_label["uno"]["stageLabel"] is None
    assert by_label["dos"]["stage"] == 1
    assert by_label["dos"]["stageLabel"] == "Scrapers"


@pytest.mark.asyncio
async def test_create_rejects_client_supplied_depends_on(client: AsyncClient) -> None:
    node = _staged_node("uno", "tasks.a", 0)
    node["dependsOn"] = ["otro-id"]

    resp = await client.post(
        "/api/workflows",
        json={
            "name": "rechazo",
            "scheduleType": "interval",
            "intervalSeconds": 60,
            "nodes": [node],
        },
    )

    assert resp.status_code == 422
    assert "dependsOn" in resp.text
```

Agregar `import json` arriba del archivo si no está.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/celery-gateway && .venv/bin/pytest tests/api/test_workflows_router.py -k "stage or depends_on" -v`
Expected: FAIL — los nodos se crean sin `stage`, la respuesta no trae el campo, y `dependsOn` se acepta en silencio.

- [ ] **Step 3: Update the Pydantic models**

En `services/celery-gateway/src/celery_gateway/models/workflows.py`, reemplazar el campo `depends_on` de `NodeInput` y agregar los nuevos. `NodeInput` queda:

```python
class NodeInput(_JsonFieldMixin, CamelModel):
    id: str
    label: str = Field(min_length=1)
    task_name: str = Field(min_length=1)
    args: str | None = None
    kwargs: str | None = None
    queue: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    stage: int = Field(default=0, ge=0)
    stage_label: str | None = None
    condition: Literal[
        "all_succeeded", "all_completed", "any_succeeded", "any_failed"
    ] = "all_succeeded"
    timeout_seconds: int | None = None
    position_x: float | None = None
    position_y: float | None = None

    @field_validator("depends_on")
    @classmethod
    def _reject_client_depends_on(cls, v: list[str]) -> list[str]:
        if v:
            raise ValueError(
                "dependsOn es derivado del campo stage y no se acepta en el input"
            )
        return v
```

Verificar que `field_validator` esté importado desde `pydantic` al principio del archivo; si no, agregarlo.

En `NodeResponse`, agregar después de `condition`:

```python
    stage: int
    stage_label: str | None
```

- [ ] **Step 4: Generate depends_on in the router**

En `services/celery-gateway/src/celery_gateway/routers/workflows.py`:

Agregar el import junto a los otros de services:

```python
from celery_gateway.services.workflow_stages import depends_on_from_stages
```

Agregar el helper justo después de `_remap_node_ids` (línea ~132):

```python
def _apply_generated_depends_on(nodes: list[NodeInput]) -> list[NodeInput]:
    """Deriva depends_on de los stages. El input del cliente nunca lo trae."""
    generated = depends_on_from_stages(
        [n.id for n in nodes], [n.stage for n in nodes]
    )
    return [
        node.model_copy(update={"depends_on": deps})
        for node, deps in zip(nodes, generated)
    ]
```

En `create_workflow`, reemplazar las dos líneas del orden actual:

```python
    _validate_dag(body.nodes)
    nodes = _remap_node_ids(body.nodes)
```

por:

```python
    nodes = _apply_generated_depends_on(_remap_node_ids(body.nodes))
    _validate_dag(nodes)
```

El orden importa: se remapean los ids, después se genera `depends_on` con los ids
definitivos, y recién ahí se valida el DAG ya concreto.

Aplicar el mismo reemplazo en `update_workflow`.

En los dos bloques que construyen `WorkflowNode(...)` (create y update), agregar dentro de la
llamada, después de `timeout_seconds=node.timeout_seconds,`:

```python
                stage=node.stage,
                stage_label=node.stage_label,
```

- [ ] **Step 5: Run the full backend suite**

Run: `cd services/celery-gateway && .venv/bin/pytest tests/ -v`
Expected: PASS. Los tests viejos que mandaban `dependsOn` explícito ahora fallan a propósito — actualizarlos para usar `stage` en su lugar, que es el cambio de contrato que este plan introduce.

- [ ] **Step 6: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/models/workflows.py services/celery-gateway/src/celery_gateway/routers/workflows.py services/celery-gateway/tests/api/test_workflows_router.py
git commit -m "feat(gateway): derive depends_on from node stages"
```

---

### Task 4: Test de regresión del engine

Confirma la premisa central del spec: un workflow por pasos produce exactamente los mismos
`NodeRun` que el equivalente con `depends_on` escrito a mano.

**Files:**
- Test: `services/celery-gateway/tests/service/test_workflow_engine.py`

**Interfaces:**
- Consumes: el contrato de API de Task 3.
- Produces: nada.

- [ ] **Step 1: Let `_seed_workflow` carry the stage**

En `services/celery-gateway/tests/service/test_workflow_engine.py`, dentro de `_seed_workflow`,
agregar a la construcción de `WorkflowNode(...)`, después de `timeout_seconds=None,`:

```python
            stage=int(node_spec.get("stage", 0)),  # type: ignore[arg-type]
```

- [ ] **Step 2: Write the regression test**

Agregar al final del mismo archivo. Los imports nuevos que hacen falta arriba: `json` y
`depends_on_from_stages`.

```python
class TestStagedWorkflows:
    async def test_staged_fan_in_dispatches_like_a_handwritten_dag(
        self, db_session: AsyncSession
    ) -> None:
        """Paso 0: una task. Paso 1: dos en paralelo. Paso 2: espera a las dos."""
        node_ids = ["n1", "n2", "n3", "n4"]
        stages = [0, 1, 1, 2]
        generated = depends_on_from_stages(node_ids, stages)

        wf_id = await _seed_workflow(
            db_session,
            [
                {
                    "id": node_id,
                    "label": node_id.upper(),
                    "task_name": f"tasks.{node_id}",
                    "depends_on": json.dumps(deps),
                    "stage": stage,
                }
                for node_id, deps, stage in zip(node_ids, generated, stages)
            ],
        )

        counter: list[int] = [0]

        async def _fake_dispatch(*args: object, **kwargs: object) -> str:
            counter[0] += 1
            return f"celery-{counter[0]}"

        async def _runs(run_id: str) -> dict[str, NodeRun]:
            db_session.expire_all()
            result = await db_session.execute(
                select(NodeRun).where(NodeRun.workflow_run_id == run_id)
            )
            return {nr.node_id: nr for nr in result.scalars().all()}

        with patch(
            "celery_gateway.services.workflow_engine.dispatch_task",
            new=AsyncMock(side_effect=_fake_dispatch),
        ):
            run_id = await start_workflow_run(wf_id)

            runs = await _runs(run_id)
            # Sólo el paso 0 arranca
            assert runs["n1"].status == "running"
            assert runs["n2"].status == "pending"
            assert runs["n3"].status == "pending"
            assert runs["n4"].status == "pending"

            await on_task_completed(str(runs["n1"].celery_task_id), "succeeded")

            runs = await _runs(run_id)
            # El paso 1 arranca completo; el paso 2 sigue esperando
            assert runs["n2"].status == "running"
            assert runs["n3"].status == "running"
            assert runs["n4"].status == "pending"

            await on_task_completed(str(runs["n2"].celery_task_id), "succeeded")

            runs = await _runs(run_id)
            # Falta n3, así que n4 no puede arrancar
            assert runs["n4"].status == "pending"

            await on_task_completed(str(runs["n3"].celery_task_id), "succeeded")

            runs = await _runs(run_id)
            assert runs["n4"].status == "running"
```

- [ ] **Step 3: Run the test**

Run: `cd services/celery-gateway && .venv/bin/pytest tests/service/test_workflow_engine.py -v`
Expected: PASS sin tocar una línea del engine. Si falla, el problema está en la generación de
Task 3, no en el engine.

- [ ] **Step 4: Commit**

```bash
git add services/celery-gateway/tests/service/test_workflow_engine.py
git commit -m "test(gateway): staged workflows dispatch like handwritten DAGs"
```

---

## Fase 2 — Frontend

### Task 5: Helpers puros de pasos

**Files:**
- Create: `packages/web/src/lib/workflow-stages.ts`
- Test: `packages/web/src/lib/workflow-stages.test.ts`

**Interfaces:**
- Consumes: el tipo `WorkflowNode` de `@/lib/types`.
- Produces:
  - `export interface Stage { index: number; label: string | null; nodes: WorkflowNode[] }`
  - `groupByStage(nodes: WorkflowNode[]): Stage[]`
  - `stagesToNodes(stages: Stage[]): WorkflowNode[]`
  - `moveStage(stages: Stage[], from: number, to: number): Stage[]`
  - `extractToOwnStage(stages: Stage[], nodeId: string): Stage[]`
  - `stagesFromDependsOn(nodeIds: string[], dependsOn: string[][]): number[]`

- [ ] **Step 1: Write the failing tests**

Crear `packages/web/src/lib/workflow-stages.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import {
  groupByStage,
  stagesToNodes,
  moveStage,
  extractToOwnStage,
  stagesFromDependsOn,
} from "./workflow-stages";
import type { WorkflowNode } from "@/lib/types";

const node = (id: string, stage: number, stageLabel: string | null = null): WorkflowNode => ({
  id, label: "", taskName: "tasks." + id,
  args: null, kwargs: null, queue: null,
  dependsOn: "[]", condition: "all_succeeded",
  timeoutSeconds: null, positionX: null, positionY: null, position: null,
  stage, stageLabel,
});

describe("groupByStage", () => {
  it("agrupa los nodos que comparten stage", () => {
    const stages = groupByStage([node("a", 0), node("b", 1), node("c", 1)]);
    expect(stages).toHaveLength(2);
    expect(stages[0].nodes.map((n) => n.id)).toEqual(["a"]);
    expect(stages[1].nodes.map((n) => n.id)).toEqual(["b", "c"]);
  });

  it("reindexa a contiguo cuando hay huecos", () => {
    const stages = groupByStage([node("a", 0), node("b", 7)]);
    expect(stages.map((s) => s.index)).toEqual([0, 1]);
  });

  it("toma el label del primer nodo del paso", () => {
    const stages = groupByStage([node("a", 0, "Scrapers"), node("b", 0, "Scrapers")]);
    expect(stages[0].label).toBe("Scrapers");
  });

  it("devuelve vacío sin nodos", () => {
    expect(groupByStage([])).toEqual([]);
  });
});

describe("stagesToNodes", () => {
  it("aplana reasignando stage y stageLabel", () => {
    const stages = groupByStage([node("a", 0), node("b", 5, "Grupo")]);
    const flat = stagesToNodes(stages);
    expect(flat.map((n) => [n.id, n.stage, n.stageLabel])).toEqual([
      ["a", 0, null],
      ["b", 1, "Grupo"],
    ]);
  });

  it("es la inversa de groupByStage", () => {
    const original = [node("a", 0), node("b", 1), node("c", 1)];
    expect(stagesToNodes(groupByStage(original)).map((n) => n.id)).toEqual([
      "a", "b", "c",
    ]);
  });
});

describe("moveStage", () => {
  it("mueve un paso hacia abajo y reindexa", () => {
    const stages = groupByStage([node("a", 0), node("b", 1), node("c", 2)]);
    const moved = moveStage(stages, 0, 2);
    expect(moved.map((s) => s.nodes[0].id)).toEqual(["b", "c", "a"]);
    expect(moved.map((s) => s.index)).toEqual([0, 1, 2]);
  });

  it("mueve un paso hacia arriba", () => {
    const stages = groupByStage([node("a", 0), node("b", 1), node("c", 2)]);
    expect(moveStage(stages, 2, 0).map((s) => s.nodes[0].id)).toEqual([
      "c", "a", "b",
    ]);
  });

  it("no muta el array de entrada", () => {
    const stages = groupByStage([node("a", 0), node("b", 1)]);
    moveStage(stages, 0, 1);
    expect(stages.map((s) => s.nodes[0].id)).toEqual(["a", "b"]);
  });
});

describe("stagesFromDependsOn", () => {
  it("deriva una cadena lineal", () => {
    expect(stagesFromDependsOn(["a", "b", "c"], [[], ["a"], ["b"]])).toEqual([0, 1, 2]);
  });

  it("pone en el mismo paso a los nodos paralelos", () => {
    expect(stagesFromDependsOn(["a", "b", "c"], [[], ["a"], ["a"]])).toEqual([0, 1, 1]);
  });

  it("usa el camino más largo", () => {
    expect(
      stagesFromDependsOn(["a", "b", "c", "d"], [[], ["a"], ["b"], ["a", "c"]]),
    ).toEqual([0, 1, 2, 3]);
  });

  it("ignora dependencias desconocidas", () => {
    expect(stagesFromDependsOn(["a"], [["fantasma"]])).toEqual([0]);
  });
});

describe("extractToOwnStage", () => {
  it("saca una task de un grupo a su propio paso, justo después", () => {
    const stages = groupByStage([node("a", 0, "G"), node("b", 0, "G"), node("c", 1)]);
    const result = extractToOwnStage(stages, "b");
    expect(result.map((s) => s.nodes.map((n) => n.id))).toEqual([
      ["a"], ["b"], ["c"],
    ]);
  });

  it("deja el paso sin label cuando queda un solo nodo", () => {
    const stages = groupByStage([node("a", 0, "G"), node("b", 0, "G")]);
    const result = extractToOwnStage(stages, "b");
    expect(result[1].label).toBeNull();
  });

  it("no hace nada si el nodo ya está solo en su paso", () => {
    const stages = groupByStage([node("a", 0), node("b", 1)]);
    expect(extractToOwnStage(stages, "a")).toEqual(stages);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/web && npx vitest run src/lib/workflow-stages.test.ts`
Expected: FAIL — el módulo no existe.

- [ ] **Step 3: Write the implementation**

Crear `packages/web/src/lib/workflow-stages.ts`:

```typescript
import type { WorkflowNode } from "@/lib/types";

/** Un paso del workflow: una o más tasks que corren en paralelo. */
export interface Stage {
  index: number;
  label: string | null;
  nodes: WorkflowNode[];
}

/** Agrupa nodos por stage, reindexando a 0..N-1 contiguos. */
export function groupByStage(nodes: WorkflowNode[]): Stage[] {
  const byStage = new Map<number, WorkflowNode[]>();
  for (const n of nodes) {
    const list = byStage.get(n.stage) ?? [];
    list.push(n);
    byStage.set(n.stage, list);
  }
  return [...byStage.keys()]
    .sort((a, b) => a - b)
    .map((key, index) => {
      const stageNodes = byStage.get(key)!;
      return {
        index,
        label: stageNodes[0].stageLabel ?? null,
        nodes: stageNodes,
      };
    });
}

/** Aplana los pasos a nodos, reasignando stage y stageLabel según la posición. */
export function stagesToNodes(stages: Stage[]): WorkflowNode[] {
  return stages.flatMap((stage, index) =>
    stage.nodes.map((n) => ({ ...n, stage: index, stageLabel: stage.label })),
  );
}

function _reindex(stages: Stage[]): Stage[] {
  return stages.map((s, index) => ({ ...s, index }));
}

/** Mueve un paso de una posición a otra. No muta la entrada. */
export function moveStage(stages: Stage[], from: number, to: number): Stage[] {
  const next = [...stages];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return _reindex(next);
}

/**
 * Nivel topológico de cada nodo: el camino más largo desde una raíz.
 * Se usa para importar JSON del formato viejo, que trae dependsOn y no stage.
 */
export function stagesFromDependsOn(
  nodeIds: string[],
  dependsOn: string[][],
): number[] {
  const depsById = new Map(nodeIds.map((id, i) => [id, dependsOn[i] ?? []]));
  const known = new Set(nodeIds);
  const levels = new Map<string, number>();

  const level = (id: string, seen: Set<string>): number => {
    const cached = levels.get(id);
    if (cached !== undefined) return cached;
    if (seen.has(id)) return 0; // ciclo: no debería pasar, pero no colgamos
    const deps = (depsById.get(id) ?? []).filter((d) => known.has(d));
    const next = new Set(seen).add(id);
    const value = deps.length === 0
      ? 0
      : 1 + Math.max(...deps.map((d) => level(d, next)));
    levels.set(id, value);
    return value;
  };

  return nodeIds.map((id) => level(id, new Set()));
}

/** Saca una task de su grupo y la deja en su propio paso, justo después. */
export function extractToOwnStage(stages: Stage[], nodeId: string): Stage[] {
  const stageIndex = stages.findIndex((s) => s.nodes.some((n) => n.id === nodeId));
  if (stageIndex < 0) return stages;

  const source = stages[stageIndex];
  if (source.nodes.length === 1) return stages;

  const extracted = source.nodes.find((n) => n.id === nodeId)!;
  const remaining = source.nodes.filter((n) => n.id !== nodeId);

  const next = [...stages];
  next[stageIndex] = {
    ...source,
    label: remaining.length === 1 ? null : source.label,
    nodes: remaining,
  };
  next.splice(stageIndex + 1, 0, {
    index: 0,
    label: null,
    nodes: [extracted],
  });
  return _reindex(next);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/web && npx vitest run src/lib/workflow-stages.test.ts`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/web/src/lib/workflow-stages.ts packages/web/src/lib/workflow-stages.test.ts
git commit -m "feat(web): pure stage grouping and reordering helpers"
```

---

### Task 6: Tipos y payload

**Files:**
- Modify: `packages/web/src/lib/types.ts:149-164` (`WorkflowNode`)
- Modify: `packages/web/src/pages/WorkflowEditorPage.tsx:30-42` (`_buildPayload`)

**Interfaces:**
- Consumes: `Stage` de Task 5; el contrato de API de Task 3.
- Produces: `WorkflowNode.stage: number` y `WorkflowNode.stageLabel: string | null`.

- [ ] **Step 1: Add the fields to the type**

En `packages/web/src/lib/types.ts`, dentro de `interface WorkflowNode`, después de `timeoutSeconds`:

```typescript
  /** Índice del paso al que pertenece el nodo; el DAG se deriva de esto */
  stage: number;
  /** Nombre del grupo cuando el paso tiene varias tasks */
  stageLabel: string | null;
```

- [ ] **Step 2: Send stage instead of dependsOn**

En `packages/web/src/pages/WorkflowEditorPage.tsx`, dentro de `_buildPayload`, en el `nodes.map`,
borrar la línea `dependsOn: JSON.parse(n.dependsOn),` y agregar en su lugar:

```typescript
      stage: n.stage,
      stageLabel: n.stageLabel,
```

Las líneas `positionX` / `positionY` se dejan como están: el backend las sigue aceptando y
quedarán sin uso hasta que se limpien aparte.

- [ ] **Step 3: Typecheck**

Run: `cd packages/web && npx tsc -b`
Expected: FALLA con errores en los lugares que construyen un `WorkflowNode` sin `stage`
(`workflow-editor.tsx` `_blankNode`, y el helper `node()` de `workflow-graph.test.ts`).
Arreglarlos agregando `stage: 0, stageLabel: null` en `_blankNode` y en el helper del test.

- [ ] **Step 4: Run both test suites**

Run: `cd packages/web && npx tsc -b && npx vitest run`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/web/src/lib/types.ts packages/web/src/pages/WorkflowEditorPage.tsx packages/web/src/components/workflows/workflow-editor.tsx packages/web/src/lib/workflow-graph.test.ts
git commit -m "feat(web): send node stage instead of dependsOn"
```

---

### Task 7: Lista de pasos en el editor

Reemplaza el canvas editable por la lista. Es la tarea más grande del plan.

**Files:**
- Create: `packages/web/src/components/workflows/stage-list.tsx`
- Modify: `packages/web/src/components/workflows/workflow-editor.tsx`

**Interfaces:**
- Consumes: `groupByStage`, `stagesToNodes`, `moveStage`, `extractToOwnStage` de Task 5.
- Produces: componente `StageList` con props
  `{ nodes: WorkflowNode[]; selectedNodeId: string | null; onChange(nodes: WorkflowNode[]): void; onSelectNode(id: string): void }`.

- [ ] **Step 1: Build the StageList component**

Crear `packages/web/src/components/workflows/stage-list.tsx`. El componente:

- deriva `const stages = groupByStage(nodes)` en cada render (no guarda estado propio de pasos)
- por cada paso renderiza una fila numerada; si tiene más de una task, la fila es un
  encabezado colapsable con `label ?? "Grupo"` y el contador `(N)`, y debajo las tasks
- el colapso vive en un `useState<Set<number>>` local: es de la lista, no se persiste
- cada task muestra `nodeDisplayLabel(node)` (ya existe en `@/lib/workflow-graph`) y se
  selecciona al click, llamando `onSelectNode(node.id)`
- botones por paso: subir, bajar (llaman `onChange(stagesToNodes(moveStage(...)))`), y por
  task: "sacar del grupo" (`extractToOwnStage`) y borrar
- el estado siempre se emite como nodos vía `stagesToNodes`, nunca como pasos
- un `Select` de `condition` por paso, con las cuatro opciones que ya usa el drawer
  (`all_succeeded`, `all_completed`, `any_succeeded`, `any_failed`). Al cambiarlo, escribe el
  valor en **todas** las tasks del paso:
  `onChange(stagesToNodes(stages.map((s, i) => i === stageIndex ? { ...s, nodes: s.nodes.map((n) => ({ ...n, condition: value })) } : s)))`.
  El spec es explícito en que `condition` vive en la task y no se crea un campo por paso:
  editarlo a nivel paso es sólo la forma de escribirlo en las N a la vez

- [ ] **Step 2: Swap the canvas for the list in the editor**

En `packages/web/src/components/workflows/workflow-editor.tsx`:

- reemplazar el bloque `<WorkflowCanvas ... />` por `<StageList ... />`
- `handleAddNode` pasa a agregar un nodo en un paso nuevo al final:
  `stage: Math.max(-1, ...nodes.map(n => n.stage)) + 1`
- borrar `handleAutoLayout`, `handleInsertNode` y el botón `Auto-ordenar` del topbar: el layout
  ya no es una decisión del usuario
- agregar un botón `+ Grupo` que cree un paso nuevo vacío

- [ ] **Step 3: Typecheck and run tests**

Run: `cd packages/web && npx tsc -b && npx vitest run`
Expected: PASS

- [ ] **Step 4: Verify in the running app**

Run: `make dev` desde la raíz, abrir `http://localhost:5173`, crear un workflow con un paso
suelto y un grupo de tres tasks, guardar, recargar.
Expected: la lista se reconstruye igual, y el detalle del workflow muestra el DAG con las tres
tasks en paralelo.

- [ ] **Step 5: Commit**

```bash
git add packages/web/src/components/workflows/stage-list.tsx packages/web/src/components/workflows/workflow-editor.tsx
git commit -m "feat(web): edit workflows as an ordered list of stages"
```

---

### Task 8: Canvas de sólo lectura y limpieza

**Files:**
- Modify: `packages/web/src/components/workflows/workflow-canvas.tsx`
- Modify: `packages/web/src/lib/workflow-graph.ts`
- Modify: `packages/web/src/lib/workflow-graph.test.ts`
- Delete: `packages/web/src/components/workflows/canvas-edge.tsx` (si el insert-on-edge era su única razón de ser; verificarlo antes de borrar)

**Interfaces:**
- Consumes: `nodesToFlow` y `autoLayout` ya existentes.
- Produces: `WorkflowCanvas` con props reducidas a `{ nodes, runs?, className? }`.

- [ ] **Step 1: Strip the canvas down to read-only**

En `workflow-canvas.tsx`:

- borrar `onChange`, `onSelectNode`, `onInsertNode`, `flowToWorkflowNodes`, `handleNodesChange`,
  `handleEdgesChange`, `onConnect`, `onNodeDragStop`, `pendingEmit` y el efecto que emite
- las posiciones salen siempre de `autoLayout(flowNodes, flowEdges)`, nunca de las guardadas
- `nodesDraggable={false}`, `nodesConnectable={false}`, `elementsSelectable={false}`
- el efecto de reconciliación se simplifica a recalcular todo cuando cambian `nodes` o `runs`:
  sin posiciones que preservar, no hay nada que mergear

Esto elimina de raíz el bug de arrastre que quedó sin verificar.

- [ ] **Step 2: Remove the now-dead graph helpers**

En `workflow-graph.ts`, borrar `wouldCreateCycle` y `nextNodePosition`: sin edición de grafo no
tienen consumidores. Borrar sus `describe` de `workflow-graph.test.ts`.

Conservar `nodesToFlow`, `nodeDisplayLabel` y `autoLayout`, que siguen alimentando el canvas.

- [ ] **Step 3: Update every WorkflowCanvas call site**

Run: `cd packages/web && grep -rn "WorkflowCanvas" src/`
Sacar de cada uso las props que ya no existen.

- [ ] **Step 4: Typecheck and run tests**

Run: `cd packages/web && npx tsc -b && npx vitest run`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/web/src
git commit -m "refactor(web): make the workflow canvas read-only"
```

---

### Task 9: Diálogo de selección múltiple

Lo que sobrevive del spec de bulk-add, simplificado: agrega N tasks a un paso, sin cableado.

**Files:**
- Create: `packages/web/src/components/workflows/add-tasks-dialog.tsx`
- Modify: `packages/web/src/components/workflows/workflow-editor.tsx`

**Interfaces:**
- Consumes: `useCelery()` para `knownTaskNames`.
- Produces: componente `AddTasksDialog` con props
  `{ open: boolean; onClose(): void; onAdd(taskNames: string[]): void }`.

- [ ] **Step 1: Build the dialog**

Crear `packages/web/src/components/workflows/add-tasks-dialog.tsx` sobre `@/components/ui/dialog`:

- input de búsqueda con autofocus, filtrando `knownTaskNames`
- lista scrolleable de filas clickeables que togglean, con un icono `Check` a la izquierda
  (no usar `checkbox` de shadcn: no está instalado)
- `Enter` agrega la primera coincidencia y limpia la búsqueda — es lo que permite cargar 20
  tipeando `frav`⏎ `garb`⏎ sin tocar el mouse
- chips arriba con lo seleccionado, con X para sacar
- si la búsqueda no matchea, botón `+ Usar «X» como task custom`
- confirmar con `Agregar (N)` o `⌘Enter`; deshabilitado con N=0; resetea al cerrar

- [ ] **Step 2: Wire it into the editor**

En `workflow-editor.tsx`, el botón `+ Tarea` abre el diálogo. `onAdd(taskNames)` crea un nodo
por nombre, todos con el mismo `stage` nuevo al final, y selecciona el primero.

Para agregar tasks a un grupo existente, `StageList` expone un `+` por paso que abre el mismo
diálogo con el `stage` de ese paso.

- [ ] **Step 3: Typecheck and verify in the app**

Run: `cd packages/web && npx tsc -b` y probar en `make dev`: agregar 5 tasks de una a un grupo.
Expected: aparecen las 5 en el mismo paso.

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/components/workflows/add-tasks-dialog.tsx packages/web/src/components/workflows/workflow-editor.tsx packages/web/src/components/workflows/stage-list.tsx
git commit -m "feat(web): multi-select dialog to add several tasks to a stage"
```

---

### Task 10: Pager del drawer

Permite cargar los args de 20 tasks sin cerrar el drawer.

**Files:**
- Modify: `packages/web/src/components/workflows/node-config-drawer.tsx`
- Modify: `packages/web/src/components/workflows/workflow-editor.tsx`

**Interfaces:**
- Consumes: `nodes` y `selectedNodeId` del editor.
- Produces: props nuevas en `NodeConfigDrawer`: `{ position: { index: number; total: number }; onNavigate(delta: number): void }`.

- [ ] **Step 1: Add the pager to the drawer header**

En `node-config-drawer.tsx`, junto al `SheetTitle`, renderizar `‹ {index + 1}/{total} ›` con dos
botones que llamen `onNavigate(-1)` y `onNavigate(1)`, deshabilitados en los extremos (sin wrap).

Agregar un listener de teclado sobre el contenido del `Sheet` (no sobre `window`, para no
capturar teclas con el drawer cerrado): `⌘↓` llama `onNavigate(1)` y `⌘↑` llama `onNavigate(-1)`.
Se eligió `⌘` y no `Tab` porque `Tab` navega los campos del form, y no `Alt+flecha` porque en
macOS eso mueve el cursor por palabras dentro de los inputs.

- [ ] **Step 2: Wire it into the editor**

En `workflow-editor.tsx`, calcular el índice del nodo seleccionado dentro de `nodes` y pasar
`onNavigate={(delta) => setSelectedNodeId(nodes[index + delta]?.id ?? selectedNodeId)}`.

- [ ] **Step 3: Typecheck and verify in the app**

Run: `cd packages/web && npx tsc -b` y probar en `make dev`: agregar 5 tasks y recorrerlas con
`⌘↓` cargando args en cada una.
Expected: el drawer no se cierra y los args de cada una se conservan.

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/components/workflows/node-config-drawer.tsx packages/web/src/components/workflows/workflow-editor.tsx
git commit -m "feat(web): pager to walk through nodes inside the config drawer"
```

---

### Task 11: Importar JSON del formato viejo

El diálogo de import manda los nodos tal cual vienen del JSON. Con el contrato nuevo, un JSON
con `dependsOn` recibe 422. Se convierte en el cliente derivando el `stage`.

**Files:**
- Modify: `packages/web/src/components/workflows/import-workflow-dialog.tsx`

**Interfaces:**
- Consumes: `stagesFromDependsOn` de Task 5.
- Produces: nada.

- [ ] **Step 1: Derive stage before posting**

En `import-workflow-dialog.tsx`, después de validar que `obj.nodes` es un array y antes del
`apiPost`, convertir los nodos:

```typescript
import { stagesFromDependsOn } from "@/lib/workflow-stages";

// ...

const rawNodes = obj.nodes as Record<string, unknown>[];
const nodeIds = rawNodes.map((n) => String(n.id));
const dependsOn = rawNodes.map((n) =>
  Array.isArray(n.dependsOn) ? (n.dependsOn as string[]) : [],
);
const derived = stagesFromDependsOn(nodeIds, dependsOn);

const nodes = rawNodes.map((n, i) => {
  // dependsOn es derivado del stage: el backend lo rechaza si viene en el payload
  const { dependsOn: _ignored, ...rest } = n;
  return {
    ...rest,
    stage: typeof n.stage === "number" ? n.stage : derived[i],
    stageLabel: typeof n.stageLabel === "string" ? n.stageLabel : null,
  };
});
```

Usar `nodes` en el body del `apiPost` en lugar de `obj.nodes`.

Un JSON exportado con el formato nuevo ya trae `stage`, así que se respeta y la derivación no
se usa. Uno viejo sólo trae `dependsOn` y se deriva por nivel topológico — el mismo criterio
que la migración de Task 2.

- [ ] **Step 2: Typecheck**

Run: `cd packages/web && npx tsc -b`
Expected: PASS

- [ ] **Step 3: Verify in the app**

Con `make dev`, exportar un workflow existente, importarlo con otro nombre, y comparar los dos
detalles.
Expected: el importado tiene los mismos pasos y el mismo grafo que el original.

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/components/workflows/import-workflow-dialog.tsx
git commit -m "feat(web): derive stage when importing legacy workflow JSON"
```
