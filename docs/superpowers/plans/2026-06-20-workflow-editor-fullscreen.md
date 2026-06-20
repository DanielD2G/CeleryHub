# Full-screen Workflow Editor Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move workflow create/edit out of cramped modals into dedicated full-screen routes (`/workflows/new`, `/workflows/:id/edit`) backed by one `WorkflowEditorPage`.

**Architecture:** A single full-screen page renders the existing `WorkflowEditor` in create mode (no `id`) or edit mode (loads the workflow by `id`), consolidating the create/edit submit-payload logic that currently lives duplicated in `create-workflow-dialog.tsx` and `workflow-detail-client.tsx`. The "Create Workflow" and "Edit" buttons navigate to the routes; the create dialog and the inline edit dialog are removed.

**Tech Stack:** React 19 + React Router v7 + TypeScript + Vite; existing `WorkflowEditor` (React Flow canvas).

## Global Constraints

- Frontend: no `"use client"`/`"use server"`/`server-only` in authored code; `@/` alias for `./src/*`.
- Commit messages: do NOT include a `Co-Authored-By` trailer.
- No backend changes (create/update endpoints already exist). No changes to `WorkflowEditor`/canvas.
- Verification is `tsc -b --noEmit` + `vite build` + manual (no page test runner). Run vitest to confirm pure-logic tests still pass.
- Do NOT stage the unrelated uncommitted working-tree change to `packages/web/src/components/tasks/task-detail-dialog.tsx` (a user WIP). Stage only files you change, by explicit path — never `git add -A`/`git commit -am`.

---

### Task 1: `WorkflowEditorPage` + routes

**Files:**
- Create: `packages/web/src/pages/WorkflowEditorPage.tsx`
- Modify: `packages/web/src/router.tsx`

**Interfaces:**
- Consumes: `WorkflowEditor`, `_detectIntervalUnit`, `_toIntervalSeconds`, `WorkflowFormValues` from `@/components/workflows/workflow-editor`; `apiGet`/`apiPost`/`apiPut` from `@/lib/api`; `normalizeWorkflow` from `@/lib/workflow-utils`; `Workflow`/`WorkflowNode` from `@/lib/types`.
- Produces: `WorkflowEditorPage` (default-style export `export function WorkflowEditorPage()`), reachable at `/workflows/new` (create) and `/workflows/:id/edit` (edit).

- [ ] **Step 1: Create `pages/WorkflowEditorPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import type { Workflow, WorkflowNode } from "@/lib/types";
import { apiGet, apiPost, apiPut } from "@/lib/api";
import { normalizeWorkflow } from "@/lib/workflow-utils";
import {
  WorkflowEditor,
  _detectIntervalUnit,
  _toIntervalSeconds,
  type WorkflowFormValues,
} from "@/components/workflows/workflow-editor";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Loader2 } from "lucide-react";

function _buildPayload(values: WorkflowFormValues, nodes: WorkflowNode[]) {
  const intervalSeconds =
    values.scheduleType === "interval"
      ? _toIntervalSeconds(values.intervalValue, values.intervalUnit)
      : undefined;
  return {
    name: values.name,
    description: values.description || null,
    scheduleType: values.scheduleType,
    intervalSeconds,
    cronExpression:
      values.scheduleType === "cron" ? values.cronExpression : undefined,
    enabled: values.enabled,
    maxRunCount: values.maxRunCount ? parseInt(values.maxRunCount, 10) : null,
    nodes: nodes.map((n) => ({
      id: n.id,
      label: n.label,
      taskName: n.taskName,
      args: n.args ?? "[]",
      kwargs: n.kwargs ?? "{}",
      queue: n.queue,
      dependsOn: JSON.parse(n.dependsOn),
      condition: n.condition,
      timeoutSeconds: n.timeoutSeconds,
      positionX: n.position?.x ?? n.positionX ?? null,
      positionY: n.position?.y ?? n.positionY ?? null,
    })),
  };
}

function _toDefaults(workflow: Workflow): Partial<WorkflowFormValues> {
  return {
    name: workflow.name,
    description: workflow.description ?? "",
    scheduleType: workflow.scheduleType as "none" | "interval" | "cron",
    intervalValue: workflow.intervalSeconds
      ? String(_detectIntervalUnit(workflow.intervalSeconds).value)
      : "10",
    intervalUnit: workflow.intervalSeconds
      ? _detectIntervalUnit(workflow.intervalSeconds).unit
      : "seconds",
    cronExpression: workflow.cronExpression ?? "* * * * *",
    enabled: workflow.enabled,
    maxRunCount:
      workflow.maxRunCount != null ? String(workflow.maxRunCount) : "",
  };
}

export function WorkflowEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(isEdit);

  useEffect(() => {
    if (!id) return;
    let active = true;
    apiGet<Workflow>(`/api/workflows/${id}`)
      .catch(() => null)
      .then((wf) => {
        if (!active) return;
        setWorkflow(wf ? normalizeWorkflow(wf) : null);
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  const handleSubmit = async (
    values: WorkflowFormValues,
    nodes: WorkflowNode[],
  ) => {
    const payload = _buildPayload(values, nodes);
    if (isEdit) {
      const result = await apiPut<{ error?: string }>(
        `/api/workflows/${id}`,
        payload,
      );
      if (result.error) throw new Error(result.error);
      navigate(`/workflows/${id}`);
    } else {
      const result = await apiPost<{ id?: string; error?: string }>(
        "/api/workflows",
        payload,
      );
      if (result.error) throw new Error(result.error);
      if (result.id) navigate(`/workflows/${result.id}`);
    }
  };

  const backTo = isEdit ? `/workflows/${id}` : "/workflows";

  if (isEdit && loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isEdit && !workflow) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Workflow not found</p>
        <Button asChild variant="outline">
          <Link to="/workflows">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to workflows
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-4 py-3">
        <Button asChild variant="ghost" size="icon">
          <Link to={backTo} aria-label="Back">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h1 className="text-lg font-semibold">
          {isEdit ? "Edit Workflow" : "Create Workflow"}
        </h1>
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        <WorkflowEditor
          key={workflow?.id ?? "new"}
          defaultValues={workflow ? _toDefaults(workflow) : undefined}
          nodes={workflow?.nodes}
          onSubmit={handleSubmit}
          submitLabel={isEdit ? "Save Changes" : "Create Workflow"}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register the routes in `router.tsx`**

Add the import and two `<Route>` entries. The existing block is:

```tsx
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="/workflows/:id/runs/:runId" element={<WorkflowRunPage />} />
```

Add `import { WorkflowEditorPage } from "@/pages/WorkflowEditorPage";` with the other page imports, and change the block to:

```tsx
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/workflows/new" element={<WorkflowEditorPage />} />
        <Route path="/workflows/:id" element={<WorkflowDetailPage />} />
        <Route path="/workflows/:id/edit" element={<WorkflowEditorPage />} />
        <Route path="/workflows/:id/runs/:runId" element={<WorkflowRunPage />} />
```

(React Router v7 ranks static segments above dynamic, so `/workflows/new` resolves to the editor, not `/workflows/:id`.)

- [ ] **Step 3: Typecheck + build**

Run: `cd packages/web && npx tsc -b --noEmit && npx vite build`
Expected: tsc 0 errors; vite build succeeds. (The page is reachable; entry-point buttons are wired in Task 2.)

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/pages/WorkflowEditorPage.tsx packages/web/src/router.tsx
git commit -m "feat(web): full-screen workflow editor page + routes"
```

---

### Task 2: Wire entry points + remove modals

**Files:**
- Modify: `packages/web/src/pages/WorkflowsPage.tsx`
- Modify: `packages/web/src/components/workflows/workflow-detail-client.tsx`
- Delete: `packages/web/src/components/workflows/create-workflow-dialog.tsx`

**Interfaces:**
- Consumes: the routes from Task 1.

- [ ] **Step 1: Point the "Create Workflow" button at the route**

In `WorkflowsPage.tsx`: remove the `CreateWorkflowDialog` import and its usage (`<CreateWorkflowDialog onCreated={fetchWorkflows} />`). Replace with a button that links to `/workflows/new`:

```tsx
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
```

```tsx
        <Button asChild>
          <Link to="/workflows/new">
            <Plus className="mr-2 h-4 w-4" />
            Create Workflow
          </Link>
        </Button>
```

(If `Link`/`Button`/`Plus` are already imported, don't duplicate. `fetchWorkflows` runs on mount/navigation back, so the create dialog's `onCreated` callback is no longer needed.)

- [ ] **Step 2: Point the "Edit" button at the edit route, remove the edit Dialog**

In `workflow-detail-client.tsx`: replace the edit `<Dialog>...</Dialog>` block (the one with `DialogTitle` "Edit Workflow", containing `<WorkflowEditor .../>`) with a button that navigates to the edit route:

```tsx
            <Button variant="outline" onClick={() => navigate(`/workflows/${workflow.id}/edit`)}>
              <Pencil className="mr-2 h-4 w-4" />
              Edit
            </Button>
```

(`navigate` from `useNavigate()` already exists in this component; `Pencil` is already imported for the current Edit trigger — keep it.) Remove the now-unused `editOpen`/`setEditOpen` state and the `WorkflowEditor`, `_detectIntervalUnit`, `_toIntervalSeconds`, and `apiPut` imports IF they are no longer used elsewhere in the file (check: the duplicate workflow / other handlers may still use `apiPost`/`apiPut` — only remove imports that become unused). Leave the Duplicate and Delete dialogs untouched.

- [ ] **Step 3: Delete the create dialog**

Confirm nothing else imports it:
`cd packages/web && grep -rn "create-workflow-dialog\|CreateWorkflowDialog" src` → should show only `WorkflowsPage.tsx` (now removed) — then:
`git rm packages/web/src/components/workflows/create-workflow-dialog.tsx`

- [ ] **Step 4: Verify**

Run: `cd packages/web && npm test && npx tsc -b --noEmit && npx vite build`
Expected: vitest 7/7; tsc 0 errors; vite build succeeds.

Then confirm no stragglers:
`grep -rn "create-workflow-dialog\|CreateWorkflowDialog\|editOpen" src` → nothing (the edit Dialog state is gone).

- [ ] **Step 5: Commit**

```bash
git add packages/web/src/pages/WorkflowsPage.tsx packages/web/src/components/workflows/workflow-detail-client.tsx
git rm packages/web/src/components/workflows/create-workflow-dialog.tsx 2>/dev/null; git add -u packages/web/src/components/workflows/create-workflow-dialog.tsx
git commit -m "feat(web): navigate to full-screen editor routes; remove create/edit modals"
```

(Stage only these files by explicit path — do NOT `git add -A`; an unrelated `task-detail-dialog.tsx` WIP must stay uncommitted.)

---

## Verification (end of plan)

- [ ] `cd packages/web && npm test` (vitest 7/7) · `npx tsc -b --noEmit` (0 errors) · `npx vite build` (succeeds).
- [ ] `grep -rn "create-workflow-dialog\|CreateWorkflowDialog" packages/web/src` returns nothing.
- [ ] `git status` still shows `task-detail-dialog.tsx` as an uncommitted modification (not swept into a commit).
- [ ] Manual smoke: `/workflows` → "Create Workflow" opens `/workflows/new` full screen → create → lands on `/workflows/:id`; on the detail page, "Edit" opens `/workflows/:id/edit` prefilled → save → returns to `/workflows/:id`.
