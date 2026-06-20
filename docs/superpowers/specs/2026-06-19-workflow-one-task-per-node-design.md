# Workflows: 1 nodo = 1 task — Diseño

**Fecha:** 2026-06-19
**Estado:** Aprobado (pendiente revisión final del usuario)
**Servicio:** `services/celery-gateway` (backend) + `packages/web` (frontend)

## Problema

El modelo de workflows actual deja que un **step** ejecute **varias tasks** a la
vez (`WorkflowStep.task_names` es una lista) y modela las corridas en dos
niveles (`StepRun` → varios `TaskRun`). Esto trae tres limitaciones:

1. **Fan-out pobre:** todas las tasks de un step comparten `args`/`kwargs`/`queue`.
2. **Join interno fijo:** dentro de un step el resultado está hardcodeado a
   "todas deben tener éxito"; el campo `condition` solo aplica a las
   dependencias, no a las tasks del propio step.
3. **Sin dependencias por task:** un step downstream depende del step entero,
   nunca de una task puntual.

Además hay un smell: existen **dos nociones de join** (el interno del step,
hardcodeado, y `condition` sobre dependencias).

## Objetivo

Migrar al modelo **1 nodo del DAG = 1 task de Celery**, colapsando la dualidad
step/task. El nodo pasa a ser la unidad de trabajo + sus dependencias + su
condición de join, y `depends_on` + `condition` se vuelven el **único**
mecanismo de composición (secuencial, fan-out, fan-in/join). Esto habilita
dependencias por-task, args por-task y condición de join por punto de unión.

## Decisiones tomadas

- **Colapsar a un nodo `task`:** el nodo del DAG ES una task; se fusionan
  `StepRun` + `TaskRun` en una sola tabla de runs.
- **Terminología:** el nodo del DAG se llama `node` (genérico); el nombre de la
  task de Celery que ejecuta es `taskName`. Evita el doble uso de "task".
- **Corte limpio:** migración Alembic que dropea y recrea las tablas de
  workflows; no se preservan workflows existentes (consistente con el corte
  limpio del paso a Postgres).
- **Alcance:** backend + frontend en un único spec.

## Modelo de datos

Migración Alembic `0004` (corte limpio): dropea `workflow_steps`, `step_runs`,
`task_runs`; crea `workflow_nodes`, `node_runs`.

### `WorkflowNode` (definición — reemplaza `WorkflowStep`)

```
id           str  PK
workflow_id  str  FK workflows.id ON DELETE CASCADE
label        str
task_name    str            -- la task de Celery a invocar (antes task_names: lista)
args         str | None     -- JSON
kwargs       str | None     -- JSON
queue        str | None
depends_on   str            -- JSON list de node ids
condition    str            -- all_succeeded | all_completed | any_succeeded | any_failed (join sobre deps)
timeout_seconds int | None

índice: (workflow_id)
```

### `NodeRun` (runs — fusiona `StepRun` + `TaskRun`)

```
id              str  PK
workflow_run_id str  FK workflow_runs.id ON DELETE CASCADE
node_id         str            -- denormalizado, sin FK
label           str            -- denormalizado
task_name       str            -- denormalizado
args            str | None
kwargs          str | None
queue           str | None
celery_task_id  str | None     -- UUID de Celery (antes TaskRun.task_id)
status          str            -- pending | running | succeeded | failed | skipped
error           str | None
started_at      datetime | None
finished_at     datetime | None

índices: (workflow_run_id), (celery_task_id)
```

### `WorkflowRun`

Sin cambios de columnas; su relación pasa de `step_runs` → `node_runs`.

Desaparece el doble nivel: ya no hay "varios `TaskRun` por `StepRun`". Cada
nodo = una task = un run.

## Engine

(`services/workflow_engine.py`) — se simplifica al eliminar la agregación de dos
niveles.

- `start_workflow_run`: crea el `WorkflowRun` + un `NodeRun` (pending) por nodo;
  avanza.
- `_advance_workflow`: por cada nodo pending, si sus deps están terminales y se
  cumple `condition` → despacha; si no se cumple → `skipped`. El algoritmo de
  DAG/Kahn y `_evaluate_condition` se mantienen, ahora sobre nodos.
- `_dispatch_node` (reemplaza `_dispatch_step`): despacha **una** task, marca
  `running`, guarda `celery_task_id`, arranca el timeout. Si el dispatch falla
  en el acto → `failed`.
- `on_task_completed(celery_uuid, status, error=None)`: busca el `NodeRun` por
  `celery_task_id`, lo pasa a `succeeded`/`failed` y avanza. **Se elimina** la
  lógica "¿están terminales todas las tasks del step?" — ahora es una
  transición directa de un nodo.
- `cancel_workflow_run` / timeout (`_handle_step_timeout` → `_handle_node_timeout`,
  `_expire_step` → `_expire_node`): operan sobre `NodeRun` (un task por nodo).
- `event_collector._update_run_status`: pasa a actualizar `NodeRun` por
  `celery_task_id` (antes `TaskRun`).

Estados terminales de nodo: `succeeded | failed | skipped`.

## API y validación

(`models/workflows.py`, `routers/workflows.py`)

- **`NodeInput`** (reemplaza `StepInput`): `id`, `label`, `taskName` (string
  único, antes `taskNames: list`), `args`, `kwargs`, `queue`, `dependsOn`,
  `condition`, `timeoutSeconds`. Se mantiene la validación Pydantic del JSON de
  args/kwargs.
- **`_validate_dag`**: mismo algoritmo de Kahn (ciclos, self-dep, dep
  desconocida), ahora sobre nodos.
- **Responses**: `WorkflowResponse.nodes` (antes `steps`), `NodeResponse`,
  `NodeRunResponse` (fusiona campos de step+task run),
  `WorkflowSummaryResponse.nodeCount` (antes `stepCount`).
- **Create/Update**: persisten `WorkflowNode` con `task_name` único; el
  full-replace de nodos en update se mantiene.
- **Import/Export**: el formato JSON pasa a `taskName`/`nodes`. Corte limpio: no
  se soportan exports del formato viejo.

## Frontend

(`packages/web`)

- **`workflow-step-editor.tsx`** → editor de nodo: `taskNames: string[]`
  (multi-add) pasa a **un solo `taskName`** (select/autocomplete único); se
  elimina la UI de agregar/quitar varias tasks.
- **DAG** (`workflow-dag.tsx`, `workflow-dag-node.tsx`, `workflow-dag-edge.tsx`):
  cada nodo muestra **una** task; las aristas `dependsOn` quedan igual. El grafo
  pasa a reflejar dependencias por-task.
- **`workflow-form.tsx`, `create-workflow-dialog.tsx`,
  `import-workflow-dialog.tsx`, tipos en `workflow-utils.tsx`**: actualizar al
  modelo de nodos (`taskName`, `nodes`).
- **Detalle/run** (`WorkflowDetailPage.tsx`, `WorkflowRunPage.tsx`,
  `workflow-run-history.tsx`): muestran `nodeRuns` (un estado por nodo) en vez
  del doble nivel step→tasks.
- **UI user-facing**: cada nodo se presenta como una "Task" del workflow
  (etiqueta amigable), respaldado por el modelo `node` de la API.

## Testing

- **Backend:** engine (dispatch de un nodo, gating por deps, cada `condition`,
  skip, timeout, `on_task_completed` por `celery_task_id`), validación de DAG
  (ciclo / self-dep / dep desconocida), router CRUD, integración con
  `event_collector` (evento de Celery → `NodeRun` actualizado → workflow
  avanza).
- **Frontend:** actualizar componentes/tipos y sus tests al modelo de nodos.
- **No afecta:** la persistencia de eventos (`celery_events` es standalone) ni
  los fixtures de partición.

## Fuera de alcance (YAGNI)

- Migración de datos de workflows existentes (corte limpio).
- Fan-out dinámico (N tasks desconocidas en diseño) — tampoco lo resolvía el
  modelo viejo; queda fuera.
- Compatibilidad con el formato de export/import viejo.
- Cambios en la persistencia de eventos / particionado.
