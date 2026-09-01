# Workflow Canvas Editor (React Flow) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the card-form workflow editor and the read-only dagre DAG with a single interactive React Flow canvas (`@xyflow/react`) that serves three modes — create, edit, and read-only run view — with persisted node positions and a config drawer.

**Architecture:** Backend gains `position_x`/`position_y` on `WorkflowNode` (migration 0005) exposed as `positionX`/`positionY`. Frontend adds `@xyflow/react`, a pure `lib/workflow-graph.ts` (model↔flow mapping, cycle detection, dagre auto-layout) unit-tested with a newly-added vitest runner, custom canvas node/edge components, a `WorkflowCanvas` wrapper (editable + readOnly), and config/run drawers. The old form + DAG components are deleted and all callers (create dialog, detail client, run page) move to the canvas.

**Tech Stack:** React 19 + Vite + TypeScript, `@xyflow/react` v12 (MIT), `@dagrejs/dagre` (existing), vitest (new, pure-logic tests only); backend FastAPI + SQLAlchemy + Alembic + Postgres.

## Global Constraints

- Python `>=3.11`; type-annotate everything; `_` prefix for private vars/functions.
- API responses are camelCase via `CamelModel` (`alias_generator=to_camel`).
- Frontend: no `"use client"`/`"use server"`/`server-only`; `@/` alias for `./src/*`.
- Commit messages: do NOT include a `Co-Authored-By` trailer.
- Library: `@xyflow/react` v12, MIT core only (no React Flow Pro). Keep `@dagrejs/dagre`.
- Frontend tests: vitest for PURE logic only (`lib/workflow-graph.ts`); components verified via `tsc -b --noEmit` + `vite build` + manual. No `@testing-library`.
- `NodeRun` is unchanged; positions live on `WorkflowNode` only. Nodes without a stored position fall back to dagre auto-layout (no data migration).
- Do NOT touch the event-persistence feature (`celery_events`, partitions, `event_persister`, retention) or the workflow engine semantics.

---

### Task 1: Backend — node positions (model, migration, schema, router)

**Files:**
- Modify: `services/celery-gateway/src/celery_gateway/db/models.py` (WorkflowNode)
- Create: `services/celery-gateway/migrations/versions/0005_node_positions.py`
- Modify: `services/celery-gateway/src/celery_gateway/models/workflows.py` (NodeInput, NodeResponse)
- Modify: `services/celery-gateway/src/celery_gateway/routers/workflows.py` (create + update persist positions)
- Test: `services/celery-gateway/tests/api/test_workflows_router.py`

**Interfaces:**
- Produces: `WorkflowNode.position_x: float | None`, `WorkflowNode.position_y: float | None`; `NodeInput.position_x/position_y: float | None` (camelCase `positionX`/`positionY`); `NodeResponse.position_x/position_y: float | None`.

- [ ] **Step 1: Add columns to the model**

In `db/models.py`, add `from sqlalchemy import Float` (already imported for CeleryEvent — verify) and add to `WorkflowNode`:

```python
    position_x: Mapped[float | None] = mapped_column(Float, default=None)
    position_y: Mapped[float | None] = mapped_column(Float, default=None)
```

- [ ] **Step 2: Create migration `migrations/versions/0005_node_positions.py`**

```python
"""node positions

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_nodes", sa.Column("position_x", sa.Float(), nullable=True))
    op.add_column("workflow_nodes", sa.Column("position_y", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_nodes", "position_y")
    op.drop_column("workflow_nodes", "position_x")
```

- [ ] **Step 3: Add the failing router test**

In `tests/api/test_workflows_router.py` add:

```python
@pytest.mark.asyncio
async def test_create_persists_node_positions(client):
    payload = {
        "name": "wf-pos",
        "nodes": [
            {"id": "a", "label": "A", "taskName": "tasks.a",
             "positionX": 120.5, "positionY": 40.0},
        ],
    }
    resp = await client.post("/api/workflows", json=payload)
    assert resp.status_code == 201
    wid = resp.json()["id"]

    detail = await client.get(f"/api/workflows/{wid}")
    node = detail.json()["nodes"][0]
    assert node["positionX"] == 120.5
    assert node["positionY"] == 40.0
```

- [ ] **Step 4: Run it to verify it fails**

Run: `cd services/celery-gateway && source .venv/bin/activate && pytest tests/api/test_workflows_router.py::test_create_persists_node_positions -v`
Expected: FAIL (positionX not persisted / KeyError or None).

- [ ] **Step 5: Add fields to schemas**

In `models/workflows.py`, add to `NodeInput`:

```python
    position_x: float | None = None
    position_y: float | None = None
```

and to `NodeResponse`:

```python
    position_x: float | None
    position_y: float | None
```

- [ ] **Step 6: Persist in the router**

In `routers/workflows.py`, in BOTH the `create_workflow` and `update_workflow` `WorkflowNode(...)` constructions, add:

```python
                position_x=node.position_x,
                position_y=node.position_y,
```

- [ ] **Step 7: Apply migration, run test, verify reversibility**

```bash
cd services/celery-gateway && source .venv/bin/activate
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/celeryhub
alembic upgrade head && alembic downgrade 0004 && alembic upgrade head
pytest tests/api/test_workflows_router.py -q
```
Expected: migration up/down/up exit 0; the new test passes and the existing router tests stay green.

- [ ] **Step 8: Commit**

```bash
git add services/celery-gateway/src/celery_gateway/db/models.py services/celery-gateway/migrations/versions/0005_node_positions.py services/celery-gateway/src/celery_gateway/models/workflows.py services/celery-gateway/src/celery_gateway/routers/workflows.py services/celery-gateway/tests/api/test_workflows_router.py
git commit -m "feat(workflows): persist node positions"
```

---

### Task 2: Frontend — vitest setup + `lib/workflow-graph.ts` pure helpers

**Files:**
- Modify: `packages/web/package.json` (add `vitest`, a `test` script)
- Create: `packages/web/vitest.config.ts`
- Create: `packages/web/src/lib/workflow-graph.ts`
- Create: `packages/web/src/lib/workflow-graph.test.ts`
- Modify: `packages/web/src/lib/types.ts` (add `position` to `WorkflowNode`)

**Interfaces:**
- Consumes: `WorkflowNode` type, `parseJson` from `workflow-utils`.
- Produces (all pure):
  - `type FlowNode = { id: string; position: { x: number; y: number }; data: { label: string; taskName: string; status?: string } }`
  - `type FlowEdge = { id: string; source: string; target: string }`
  - `nodesToFlow(nodes: WorkflowNode[], runs?: NodeRun[]): { flowNodes: FlowNode[]; flowEdges: FlowEdge[] }` — edge per `dependsOn` entry (source = dependency id, target = node id); position from `node.position` (fallback handled by autoLayout caller); `data.status` from the matching `NodeRun.status` by `nodeId` when `runs` given.
  - `wouldCreateCycle(edges: FlowEdge[], source: string, target: string): boolean` — true if adding source→target creates a cycle or is a self-loop.
  - `autoLayout(flowNodes: FlowNode[], flowEdges: FlowEdge[]): FlowNode[]` — returns nodes with dagre-computed `position`.

- [ ] **Step 1: Add vitest**

In `package.json` `devDependencies` add `"vitest": "^2.1.0"`; in `scripts` add `"test": "vitest run"`. Create `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
```

Install: `cd packages/web && npm install`.

- [ ] **Step 2: Add `position` to the `WorkflowNode` type**

In `src/lib/types.ts`, add to `WorkflowNode`:

```ts
  position: { x: number; y: number } | null; // from API positionX/positionY; null → auto-layout
```

(The API client maps `positionX`/`positionY` → `position`. If the raw API type is consumed directly, instead add `positionX: number | null; positionY: number | null;` and map in `nodesToFlow`. Use whichever matches how `Workflow.nodes` is currently fetched — read the API client first and stay consistent.)

- [ ] **Step 3: Write the failing tests**

Create `src/lib/workflow-graph.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { nodesToFlow, wouldCreateCycle, autoLayout } from "./workflow-graph";

const node = (id: string, deps: string[], pos?: { x: number; y: number }) => ({
  id, label: id, taskName: "tasks." + id,
  args: null, kwargs: null, queue: null,
  dependsOn: JSON.stringify(deps), condition: "all_succeeded",
  timeoutSeconds: null, position: pos ?? null,
});

describe("nodesToFlow", () => {
  it("builds one edge per dependency (source=dep, target=node)", () => {
    const { flowNodes, flowEdges } = nodesToFlow([node("a", []), node("b", ["a"])]);
    expect(flowNodes).toHaveLength(2);
    expect(flowEdges).toEqual([{ id: "a->b", source: "a", target: "b" }]);
  });

  it("uses stored position when present", () => {
    const { flowNodes } = nodesToFlow([node("a", [], { x: 10, y: 20 })]);
    expect(flowNodes[0].position).toEqual({ x: 10, y: 20 });
  });

  it("maps run status by nodeId", () => {
    const runs = [{ id: "r1", nodeId: "a", label: "a", taskName: "tasks.a",
      celeryTaskId: null, status: "succeeded", error: null,
      startedAt: null, finishedAt: null }];
    const { flowNodes } = nodesToFlow([node("a", [])], runs as any);
    expect(flowNodes[0].data.status).toBe("succeeded");
  });
});

describe("wouldCreateCycle", () => {
  const edges = [{ id: "a->b", source: "a", target: "b" }];
  it("detects a back-edge cycle", () => {
    expect(wouldCreateCycle(edges, "b", "a")).toBe(true);
  });
  it("detects self-loop", () => {
    expect(wouldCreateCycle(edges, "a", "a")).toBe(true);
  });
  it("allows a valid new edge", () => {
    expect(wouldCreateCycle(edges, "b", "c")).toBe(false);
  });
});

describe("autoLayout", () => {
  it("assigns a position to every node", () => {
    const { flowNodes, flowEdges } = nodesToFlow([node("a", []), node("b", ["a"])]);
    const laid = autoLayout(flowNodes, flowEdges);
    expect(laid).toHaveLength(2);
    for (const n of laid) {
      expect(typeof n.position.x).toBe("number");
      expect(typeof n.position.y).toBe("number");
    }
  });
});
```

- [ ] **Step 4: Run to verify failure**

Run: `cd packages/web && npm test`
Expected: FAIL (module `./workflow-graph` not found).

- [ ] **Step 5: Implement `src/lib/workflow-graph.ts`**

```ts
import dagre from "@dagrejs/dagre";
import type { WorkflowNode, NodeRun } from "@/lib/types";
import { parseJson } from "@/lib/workflow-utils";

export interface FlowNode {
  id: string;
  position: { x: number; y: number };
  data: { label: string; taskName: string; status?: string };
}
export interface FlowEdge {
  id: string;
  source: string;
  target: string;
}

const NODE_W = 280;
const NODE_H = 100;

export function nodesToFlow(
  nodes: WorkflowNode[],
  runs?: NodeRun[],
): { flowNodes: FlowNode[]; flowEdges: FlowEdge[] } {
  const statusByNodeId = new Map<string, string>();
  for (const r of runs ?? []) statusByNodeId.set(r.nodeId, r.status);

  const flowNodes: FlowNode[] = nodes.map((n) => ({
    id: n.id,
    position: n.position ?? { x: 0, y: 0 },
    data: { label: n.label, taskName: n.taskName, status: statusByNodeId.get(n.id) },
  }));

  const flowEdges: FlowEdge[] = [];
  for (const n of nodes) {
    for (const dep of parseJson<string[]>(n.dependsOn, [])) {
      flowEdges.push({ id: `${dep}->${n.id}`, source: dep, target: n.id });
    }
  }
  return { flowNodes, flowEdges };
}

export function wouldCreateCycle(
  edges: FlowEdge[],
  source: string,
  target: string,
): boolean {
  if (source === target) return true;
  // adding source->target creates a cycle iff source is already reachable from target
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    const list = adj.get(e.source) ?? [];
    list.push(e.target);
    adj.set(e.source, list);
  }
  const stack = [target];
  const seen = new Set<string>();
  while (stack.length) {
    const cur = stack.pop()!;
    if (cur === source) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const nxt of adj.get(cur) ?? []) stack.push(nxt);
  }
  return false;
}

export function autoLayout(
  flowNodes: FlowNode[],
  flowEdges: FlowEdge[],
): FlowNode[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 80 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of flowNodes) g.setNode(n.id, { width: NODE_W, height: NODE_H });
  for (const e of flowEdges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return flowNodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}
```

- [ ] **Step 6: Run to verify pass**

Run: `cd packages/web && npm test`
Expected: PASS (all describe blocks green).

- [ ] **Step 7: Commit**

```bash
git add packages/web/package.json packages/web/package-lock.json packages/web/vitest.config.ts packages/web/src/lib/workflow-graph.ts packages/web/src/lib/workflow-graph.test.ts packages/web/src/lib/types.ts
git commit -m "feat(web): workflow-graph helpers + vitest for pure logic"
```

---

### Task 3: Frontend — add `@xyflow/react` + API position mapping

**Files:**
- Modify: `packages/web/package.json` (add `@xyflow/react`)
- Modify: the API client / fetch layer where `Workflow.nodes` is read (search: `grep -rn "positionX\|/api/workflows" packages/web/src/lib`)

**Interfaces:**
- Produces: `@xyflow/react` available; each fetched `WorkflowNode` carries `position` derived from API `positionX`/`positionY` (or the raw fields exposed, consistent with Task 2 Step 2 decision).

- [ ] **Step 1: Install React Flow**

```bash
cd packages/web && npm install @xyflow/react@^12
```

- [ ] **Step 2: Map positions on fetch**

Find where workflows are fetched (the api client returns `Workflow` with `nodes`). Ensure each node exposes `position`: if the client returns raw camelCase JSON, add a small normalizer where workflows are loaded so `node.position = (node.positionX != null && node.positionY != null) ? { x: node.positionX, y: node.positionY } : null`. Keep it in one place (the api client or a `normalizeWorkflow` helper in `workflow-utils.tsx`). Verify with `npx tsc -b --noEmit` that `types.ts` + `workflow-graph.ts` compile (components still error until later tasks — expected).

- [ ] **Step 3: Commit**

```bash
git add packages/web/package.json packages/web/package-lock.json packages/web/src/lib
git commit -m "feat(web): add @xyflow/react and map node positions"
```

---

### Task 4: Frontend — custom canvas node + edge components

**Files:**
- Create: `packages/web/src/components/workflows/canvas-node.tsx`
- Create: `packages/web/src/components/workflows/canvas-edge.tsx`

**Interfaces:**
- Consumes: `@xyflow/react` (`Handle`, `Position`, `NodeProps`, `EdgeProps`, `BaseEdge`, `getBezierPath`, `EdgeLabelRenderer`); `FlowNode` data shape from Task 2.
- Produces: `CanvasNode` (default export usable in `nodeTypes`), `CanvasEdge` (for `edgeTypes`), and an `onInsert?: (edgeId: string) => void` contract carried via edge `data` for the "+" insert affordance.

- [ ] **Step 1: Implement `canvas-node.tsx`**

A custom node showing label + taskName + an optional status badge, with a target handle (top) and source handle (bottom). Status color comes from `data.status`.

```tsx
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Badge } from "@/components/ui/badge";

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-blue-500/15 text-blue-600",
  succeeded: "bg-green-500/15 text-green-600",
  failed: "bg-red-500/15 text-red-600",
  skipped: "bg-amber-500/15 text-amber-600",
};

export function CanvasNode({ data, selected }: NodeProps) {
  const status = data.status as string | undefined;
  return (
    <div
      className={`rounded-md border bg-card px-3 py-2 shadow-sm w-[260px] ${
        selected ? "ring-2 ring-primary" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} />
      <div className="text-sm font-medium truncate">{data.label as string}</div>
      <div className="text-xs text-muted-foreground truncate">
        {data.taskName as string}
      </div>
      {status && (
        <Badge className={`mt-1 ${STATUS_COLOR[status] ?? ""}`}>{status}</Badge>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
```

- [ ] **Step 2: Implement `canvas-edge.tsx`**

A bezier edge with a centered "+" button (shown only when `data.onInsert` is provided — editable mode) to insert a node between the two endpoints.

```tsx
import {
  BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps,
} from "@xyflow/react";
import { Plus } from "lucide-react";

export function CanvasEdge({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data,
}: EdgeProps) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
  });
  const onInsert = (data as { onInsert?: (edgeId: string) => void } | undefined)?.onInsert;
  return (
    <>
      <BaseEdge id={id} path={path} />
      {onInsert && (
        <EdgeLabelRenderer>
          <button
            type="button"
            onClick={() => onInsert(id)}
            style={{
              position: "absolute",
              transform: `translate(-50%,-50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "all",
            }}
            className="rounded-full border bg-background p-1 shadow"
            aria-label="Insert node"
          >
            <Plus className="h-3 w-3" />
          </button>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep -E "canvas-node|canvas-edge" || echo "canvas node/edge clean"`
Expected: no errors in these two files.

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/components/workflows/canvas-node.tsx packages/web/src/components/workflows/canvas-edge.tsx
git commit -m "feat(web): canvas node and edge components"
```

---

### Task 5: Frontend — `WorkflowCanvas` wrapper (editable + readOnly)

**Files:**
- Create: `packages/web/src/components/workflows/workflow-canvas.tsx`

**Interfaces:**
- Consumes: `@xyflow/react` (`ReactFlow`, `ReactFlowProvider`, `Background`, `Controls`, `useNodesState`, `useEdgesState`, `addEdge`, `type Connection`), `CanvasNode`, `CanvasEdge`, `nodesToFlow`/`autoLayout`/`wouldCreateCycle`.
- Produces:
  - `interface WorkflowCanvasProps { nodes: WorkflowNode[]; runs?: NodeRun[]; readOnly?: boolean; onChange?: (nodes: WorkflowNode[]) => void; onSelectNode?: (id: string | null) => void; onAddNode?: () => void; onInsertNode?: (edgeId: string) => void; }`
  - `WorkflowCanvas` component. In editable mode it owns flow state, maps edge changes back to `dependsOn`, prevents cycles on connect, and calls `onChange` with updated `WorkflowNode[]` (positions + dependsOn). In readOnly mode it disables interaction and colors nodes by run status.
  - An exported `flowToWorkflowNodes(flowNodes, flowEdges, base): WorkflowNode[]` helper OR fold that mapping into `onChange` (keep the model the source of truth: rebuild `dependsOn` from edges, `position` from flow node positions).

- [ ] **Step 1: Implement the canvas**

Key wiring (full component): initialize `useNodesState`/`useEdgesState` from `nodesToFlow(nodes, runs)`; register `nodeTypes={{ canvas: CanvasNode }}` and `edgeTypes={{ canvas: CanvasEdge }}`; set `nodesDraggable={!readOnly}`, `nodesConnectable={!readOnly}`, `elementsSelectable`. On `onConnect`, reject if `wouldCreateCycle(edges, c.source, c.target)`; else `addEdge`. On any node/edge change in editable mode, recompute the `WorkflowNode[]` (rebuild each node's `dependsOn` = JSON of incoming edge sources; `position` = flow position) and call `onChange`. Wrap render in `<ReactFlowProvider>`; include `<Background/>` and `<Controls/>`. Pass `data.onInsert = onInsertNode` onto edges only when `!readOnly`. Import `@xyflow/react/dist/style.css` once (here or in the app entry).

```tsx
import { useCallback, useMemo } from "react";
import {
  ReactFlow, ReactFlowProvider, Background, Controls,
  useNodesState, useEdgesState, addEdge,
  type Connection, type Edge, type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { WorkflowNode, NodeRun } from "@/lib/types";
import { CanvasNode } from "./canvas-node";
import { CanvasEdge } from "./canvas-edge";
import { nodesToFlow, wouldCreateCycle } from "@/lib/workflow-graph";

const nodeTypes = { canvas: CanvasNode };
const edgeTypes = { canvas: CanvasEdge };

export interface WorkflowCanvasProps {
  nodes: WorkflowNode[];
  runs?: NodeRun[];
  readOnly?: boolean;
  onChange?: (nodes: WorkflowNode[]) => void;
  onSelectNode?: (id: string | null) => void;
  onInsertNode?: (edgeId: string) => void;
}

function _Inner(props: WorkflowCanvasProps) {
  const { readOnly, onChange, onSelectNode, onInsertNode } = props;
  const initial = useMemo(() => nodesToFlow(props.nodes, props.runs), []);
  const [nodes, setNodes, onNodesChange] = useNodesState(
    initial.flowNodes.map((n) => ({ ...n, type: "canvas" })) as Node[],
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(
    initial.flowEdges.map((e) => ({
      ...e, type: "canvas",
      data: readOnly ? {} : { onInsert: onInsertNode },
    })) as Edge[],
  );

  const emit = useCallback(
    (ns: Node[], es: Edge[]) => {
      if (!onChange) return;
      const depsByTarget = new Map<string, string[]>();
      for (const e of es) {
        const list = depsByTarget.get(e.target) ?? [];
        list.push(e.source);
        depsByTarget.set(e.target, list);
      }
      onChange(
        ns.map((n) => {
          const base = props.nodes.find((b) => b.id === n.id)!;
          return {
            ...base,
            position: { x: n.position.x, y: n.position.y },
            dependsOn: JSON.stringify(depsByTarget.get(n.id) ?? []),
          };
        }),
      );
    },
    [onChange, props.nodes],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      if (!c.source || !c.target) return;
      if (wouldCreateCycle(edges as any, c.source, c.target)) return;
      setEdges((es) => {
        const next = addEdge({ ...c, type: "canvas", data: { onInsert: onInsertNode } }, es);
        emit(nodes, next);
        return next;
      });
    },
    [edges, nodes, emit, onInsertNode],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={(c) => { onNodesChange(c); }}
      onEdgesChange={(c) => { onEdgesChange(c); }}
      onNodeDragStop={() => emit(nodes, edges)}
      onConnect={onConnect}
      onNodeClick={(_, n) => onSelectNode?.(n.id)}
      onPaneClick={() => onSelectNode?.(null)}
      nodesDraggable={!readOnly}
      nodesConnectable={!readOnly}
      elementsSelectable
      fitView
    >
      <Background />
      <Controls />
    </ReactFlow>
  );
}

export function WorkflowCanvas(props: WorkflowCanvasProps) {
  return (
    <div className="h-[560px] w-full rounded-md border">
      <ReactFlowProvider>
        <_Inner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep "workflow-canvas" || echo "canvas clean"`
Expected: no errors in `workflow-canvas.tsx`. (Callers still error until Tasks 8-9.)

- [ ] **Step 3: Commit**

```bash
git add packages/web/src/components/workflows/workflow-canvas.tsx
git commit -m "feat(web): WorkflowCanvas wrapper (editable + readOnly)"
```

---

### Task 6: Frontend — node config drawer (editable)

**Files:**
- Create: `packages/web/src/components/workflows/node-config-drawer.tsx`

**Interfaces:**
- Consumes: the shadcn drawer/sheet primitive (use the existing one — `grep -rn "sheet\|drawer" packages/web/src/components/ui`); `ArgsBuilder`/`KwargsBuilder`/`QueueSelector`/`parseArgsToItems`/`serializeArgs` from `@/components/task-inputs`; `WorkflowNode`.
- Produces: `NodeConfigDrawer` with props `{ node: WorkflowNode | null; otherNodeIds: { id: string; label: string }[]; onChange: (node: WorkflowNode) => void; onClose: () => void }`. Edits `label`, `taskName`, `queue`, args, kwargs, `condition`, `timeoutSeconds` and emits the updated node. `dependsOn` is edited on the canvas (edges), NOT here.

- [ ] **Step 1: Implement the drawer**

Open when `node` is non-null. Controlled fields bound to the node; on each change call `onChange({ ...node, <field> })`. Reuse the task-input builders for args/kwargs and the queue selector (parse with `parseJson`/`parseArgsToItems`, serialize back to the node's string fields). The task selector is a single `taskName` autocomplete over `knownTaskNames` (reuse the pattern from the deleted node editor — copy the relevant single-select logic). Provide a `condition` Select with the four values and a numeric `timeoutSeconds` input.

- [ ] **Step 2: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep "node-config-drawer" || echo "config drawer clean"`
Expected: no errors in `node-config-drawer.tsx`.

- [ ] **Step 3: Commit**

```bash
git add packages/web/src/components/workflows/node-config-drawer.tsx
git commit -m "feat(web): node config drawer"
```

---

### Task 7: Frontend — node run drawer (read-only)

**Files:**
- Create: `packages/web/src/components/workflows/node-run-drawer.tsx`

**Interfaces:**
- Consumes: the same drawer primitive; `NodeRun`; `WorkflowStatusBadge`, `formatWorkflowDuration` (existing, used by the run history/table).
- Produces: `NodeRunDrawer` with props `{ run: NodeRun | null; onClose: () => void }` showing status badge, `celeryTaskId` (link to `/tasks/<id>`), `startedAt`/`finishedAt` + duration, and `error`.

- [ ] **Step 1: Implement the drawer**

Open when `run` is non-null. Read-only fields. Match the columns already shown in the run table (`workflow-run-history.tsx` / the run page table) for consistency.

- [ ] **Step 2: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep "node-run-drawer" || echo "run drawer clean"`
Expected: no errors in `node-run-drawer.tsx`.

- [ ] **Step 3: Commit**

```bash
git add packages/web/src/components/workflows/node-run-drawer.tsx
git commit -m "feat(web): node run detail drawer"
```

---

### Task 8: Frontend — wire editing (create dialog + detail client), delete old form

**Files:**
- Modify: `packages/web/src/components/workflows/create-workflow-dialog.tsx`
- Modify: `packages/web/src/components/workflows/workflow-detail-client.tsx`
- Modify: `packages/web/src/components/workflows/import-workflow-dialog.tsx`
- Delete: `packages/web/src/components/workflows/workflow-form.tsx`, `packages/web/src/components/workflows/workflow-node-editor.tsx`

**Interfaces:**
- Consumes: `WorkflowCanvas` (Task 5), `NodeConfigDrawer` (Task 6), `autoLayout`/`nodesToFlow` (Task 2).
- Produces: a `WorkflowEditor` composition (canvas + "+ Tarea" add button + auto-layout button + config drawer) used by create dialog and detail-client edit; submit builds the `nodes` payload (`taskName`, `dependsOn`, `positionX`/`positionY` from `node.position`, args/kwargs/queue/condition/timeout). The import dialog keeps its old-format rejection and runs `autoLayout` when imported nodes lack positions.

- [ ] **Step 1: Build the editor composition**

Create a small `WorkflowEditor` (either inline in `workflow-detail-client.tsx` or a new `workflow-editor.tsx`) holding `WorkflowNode[]` state + selected node id. Render the toolbar (workflow name/schedule fields as today + "+ Tarea" add button + "Auto-ordenar" button calling `autoLayout` and writing positions back) + `<WorkflowCanvas nodes onChange onSelectNode onInsertNode />` + `<NodeConfigDrawer node={selected} ... />`. "+ Tarea" appends a `WorkflowNode` with a fresh id, empty `taskName`, `dependsOn:"[]"`, a position near center; "+" on edge (`onInsertNode`) splits the edge (new node between source/target, rewire dependsOn). Submit maps state → API payload `nodes` with `positionX: n.position?.x ?? null`, `positionY: n.position?.y ?? null`.

- [ ] **Step 2: Replace `WorkflowForm` usages**

In `create-workflow-dialog.tsx` and `workflow-detail-client.tsx`, replace `<WorkflowForm .../>` with the new editor composition. Remove the `WorkflowForm`/`apiToNodeEditor`/`workflow-node-editor` imports. In `import-workflow-dialog.tsx`, after parsing valid `nodes`, run `autoLayout` if any node lacks a position before sending.

- [ ] **Step 3: Delete the old files**

```bash
cd packages/web && grep -rn "workflow-form\|WorkflowForm\|workflow-node-editor\|NodeEditorState\|apiToNodeEditor" src
```
Confirm only the files being deleted/edited reference them, then `git rm src/components/workflows/workflow-form.tsx src/components/workflows/workflow-node-editor.tsx`.

- [ ] **Step 4: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep -E "create-workflow|workflow-detail-client|import-workflow|workflow-editor" || echo "editing wiring clean"`
Expected: no errors in these files (run page still errors until Task 9 — expected).

- [ ] **Step 5: Commit**

```bash
git add -A packages/web/src/components/workflows
git commit -m "feat(web): canvas-based workflow editor; remove card form"
```

---

### Task 9: Frontend — wire run view, delete old DAG, final build

**Files:**
- Modify: `packages/web/src/pages/WorkflowRunPage.tsx`
- Modify: `packages/web/src/components/workflows/workflow-detail-client.tsx` (preview uses canvas readOnly)
- Modify: `packages/web/src/pages/WorkflowDetailPage.tsx` (if it renders the DAG)
- Delete: `packages/web/src/components/workflows/workflow-dag.tsx`, `workflow-dag-node.tsx`, `workflow-dag-edge.tsx`

**Interfaces:**
- Consumes: `WorkflowCanvas` (readOnly), `NodeRunDrawer` (Task 7).

- [ ] **Step 1: Replace `WorkflowDag` with the read-only canvas**

In `WorkflowRunPage.tsx`, replace `<WorkflowDag nodes={workflow.nodes} nodeRuns={run.nodeRuns} />` with `<WorkflowCanvas nodes={workflow.nodes} runs={run.nodeRuns} readOnly onSelectNode={...} />` plus a `<NodeRunDrawer run={selectedRun} .../>` (resolve selected node id → its NodeRun). Keep the existing `nodeRuns` table below. Do the same for any read-only preview in `workflow-detail-client.tsx` / `WorkflowDetailPage.tsx`.

- [ ] **Step 2: Delete the old DAG files**

```bash
cd packages/web && grep -rn "workflow-dag\|WorkflowDag" src
```
Confirm no remaining importers, then `git rm src/components/workflows/workflow-dag.tsx src/components/workflows/workflow-dag-node.tsx src/components/workflows/workflow-dag-edge.tsx`.

- [ ] **Step 3: Full verification**

```bash
cd packages/web && npm test && npx tsc -b --noEmit && npx vite build
```
Expected: vitest green; tsc 0 errors; vite build succeeds.

- [ ] **Step 4: Final grep — no stragglers**

Run: `cd packages/web && grep -rn "WorkflowForm\|workflow-node-editor\|WorkflowDag\|workflow-dag" src` → expect nothing.

- [ ] **Step 5: Commit**

```bash
git add -A packages/web/src
git commit -m "feat(web): canvas-based run view; remove dagre DAG components"
```

---

## Verification (end of plan)

- [ ] Backend: `pytest -q` green; `alembic upgrade head` reaches `0005`; `alembic downgrade 0004 && alembic upgrade head` works.
- [ ] Frontend: `npm test` (vitest, workflow-graph) green; `npx tsc -b --noEmit` 0 errors; `npx vite build` succeeds.
- [ ] `grep -rn "WorkflowForm\|workflow-node-editor\|workflow-dag\|WorkflowDag" packages/web/src` returns nothing.
- [ ] Manual smoke: create a workflow on the canvas (add 3 nodes, drag to connect A→B→C, configure each via drawer, auto-layout, save); reopen — positions persisted; run it and watch the read-only canvas color nodes by status with the nodeRuns table below.

## Notes

- React Flow v12 ships `@xyflow/react/dist/style.css` — it must be imported once (in `workflow-canvas.tsx` per the plan, or the app entry). Without it the canvas renders unstyled.
- Cycle prevention is client-side UX; the backend `_validate_dag` remains the authority on save.
