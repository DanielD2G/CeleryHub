# Workflow Editor n8n-Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the workflow editor from a two-column (form sidebar + small canvas) layout into an n8n-style layout: a top bar (inline name, enabled toggle, canvas actions, settings, save) over a full-width/height canvas, with the workflow settings (description, schedule, max runs) moved into a Settings drawer.

**Architecture:** A new `WorkflowSettingsDrawer` (Sheet) holds description/schedule/maxRuns. `WorkflowEditor` becomes `flex-col h-full`: a top bar + a `flex-1` canvas. `WorkflowCanvas` gains an optional `className` so the editor can make it fill height (run-view callers keep the default fixed height). `WorkflowEditorPage` drops its separate header and passes `onBack` to the editor's top bar.

**Tech Stack:** React 19 + TypeScript + Vite; existing shadcn `Sheet`/`Tabs`/`Select`/`Switch`/`Button`/`Input`; React Flow canvas (unchanged).

## Global Constraints

- Frontend: no `"use client"`/`"use server"`/`server-only` in authored code; `@/` alias for `./src/*`.
- Commit messages: do NOT include a `Co-Authored-By` trailer.
- No backend changes. `NodeConfigDrawer` (node config) stays unchanged. No new canvas features beyond the height/`className` prop.
- Verification: `tsc -b --noEmit` + `vite build` + manual; run vitest to confirm pure-logic tests still pass. No page test runner.
- Do NOT stage the unrelated uncommitted `packages/web/src/components/tasks/task-detail-dialog.tsx` (user WIP). Stage only files you change, by explicit path — never `git add -A`/`git commit -am`.

---

### Task 1: `WorkflowSettingsDrawer`

**Files:**
- Create: `packages/web/src/components/workflows/workflow-settings-drawer.tsx`

**Interfaces:**
- Consumes: shadcn `Sheet` (mirror the import + usage in `node-config-drawer.tsx` — same primitive), `Input`, `Label`, `Tabs`, `Select`.
- Produces: `WorkflowSettingsDrawer` (controlled) with props:
  ```ts
  interface WorkflowSettingsDrawerProps {
    open: boolean;
    onClose: () => void;
    description: string; setDescription: (v: string) => void;
    scheduleType: "none" | "interval" | "cron"; setScheduleType: (v: "none" | "interval" | "cron") => void;
    intervalValue: string; setIntervalValue: (v: string) => void;
    intervalUnit: string; setIntervalUnit: (v: string) => void;
    cronExpression: string; setCronExpression: (v: string) => void;
    maxRunCount: string; setMaxRunCount: (v: string) => void;
  }
  ```

- [ ] **Step 1: Read the Sheet usage pattern**

Open `packages/web/src/components/workflows/node-config-drawer.tsx` and note exactly how it imports and uses `Sheet`/`SheetContent`/`SheetHeader`/`SheetTitle` (open prop, `onOpenChange`, `side`, width classes). Mirror that pattern.

- [ ] **Step 2: Create `workflow-settings-drawer.tsx`**

The body reuses the exact schedule/description/maxRun controls that currently live in `workflow-editor.tsx`'s left column (moved verbatim):

```tsx
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface WorkflowSettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  description: string;
  setDescription: (v: string) => void;
  scheduleType: "none" | "interval" | "cron";
  setScheduleType: (v: "none" | "interval" | "cron") => void;
  intervalValue: string;
  setIntervalValue: (v: string) => void;
  intervalUnit: string;
  setIntervalUnit: (v: string) => void;
  cronExpression: string;
  setCronExpression: (v: string) => void;
  maxRunCount: string;
  setMaxRunCount: (v: string) => void;
}

export function WorkflowSettingsDrawer({
  open,
  onClose,
  description,
  setDescription,
  scheduleType,
  setScheduleType,
  intervalValue,
  setIntervalValue,
  intervalUnit,
  setIntervalUnit,
  cronExpression,
  setCronExpression,
  maxRunCount,
  setMaxRunCount,
}: WorkflowSettingsDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent side="right" className="w-[400px] overflow-y-auto sm:max-w-[400px]">
        <SheetHeader>
          <SheetTitle>Workflow Settings</SheetTitle>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="wf-description">Description (optional)</Label>
            <textarea
              id="wf-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what this workflow does..."
              className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              rows={2}
            />
          </div>

          <div className="space-y-2">
            <Label>Schedule</Label>
            <Tabs value={scheduleType} onValueChange={(v) => setScheduleType(v as "none" | "interval" | "cron")}>
              <TabsList>
                <TabsTrigger value="none">None</TabsTrigger>
                <TabsTrigger value="interval">Interval</TabsTrigger>
                <TabsTrigger value="cron">Cron</TabsTrigger>
              </TabsList>
              <TabsContent value="none">
                <p className="mt-2 text-xs text-muted-foreground">
                  Manual trigger only — use &quot;Run Now&quot; to execute
                </p>
              </TabsContent>
              <TabsContent value="interval">
                <div className="mt-2 flex gap-2">
                  <Input
                    type="number"
                    min="1"
                    value={intervalValue}
                    onChange={(e) => setIntervalValue(e.target.value)}
                    className="w-24"
                  />
                  <Select value={intervalUnit} onValueChange={setIntervalUnit}>
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="seconds">Seconds</SelectItem>
                      <SelectItem value="minutes">Minutes</SelectItem>
                      <SelectItem value="hours">Hours</SelectItem>
                      <SelectItem value="days">Days</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>
              <TabsContent value="cron">
                <Input
                  value={cronExpression}
                  onChange={(e) => setCronExpression(e.target.value)}
                  placeholder="* * * * *"
                  className="mt-2 font-mono"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Format: minute hour day-of-month month day-of-week
                </p>
              </TabsContent>
            </Tabs>
          </div>

          <div className="space-y-2">
            <Label htmlFor="wf-max-runs">Max Run Count (optional)</Label>
            <Input
              id="wf-max-runs"
              type="number"
              min="1"
              value={maxRunCount}
              onChange={(e) => setMaxRunCount(e.target.value)}
              placeholder="Unlimited"
              className="w-40"
            />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

(If `node-config-drawer.tsx` imports `Sheet` parts from a different path or with a `SheetDescription`, match that exact import set.)

- [ ] **Step 3: Typecheck**

Run: `cd packages/web && npx tsc -b --noEmit 2>&1 | grep "workflow-settings-drawer" || echo "settings drawer clean"`
Expected: no errors in the new file.

- [ ] **Step 4: Commit**

```bash
git add packages/web/src/components/workflows/workflow-settings-drawer.tsx
git commit -m "feat(web): workflow settings drawer"
```

---

### Task 2: Restructure editor to topbar + full canvas; full-height canvas; page header

**Files:**
- Modify: `packages/web/src/components/workflows/workflow-editor.tsx`
- Modify: `packages/web/src/components/workflows/workflow-canvas.tsx` (add optional `className`)
- Modify: `packages/web/src/pages/WorkflowEditorPage.tsx`

**Interfaces:**
- Consumes: `WorkflowSettingsDrawer` (Task 1).
- Produces: `WorkflowEditorProps` gains `onBack?: () => void`. `WorkflowCanvasProps` gains `className?: string` (default keeps the current fixed-height wrapper).

- [ ] **Step 1: Add an optional `className` to `WorkflowCanvas`**

In `workflow-canvas.tsx`, the outer wrapper currently is:

```tsx
    <div className="h-[560px] w-full rounded-md border">
```

Add `className?: string` to `WorkflowCanvasProps`, and change the `WorkflowCanvas` wrapper to use it with the current value as default:

```tsx
export function WorkflowCanvas(props: WorkflowCanvasProps) {
  return (
    <div className={props.className ?? "h-[560px] w-full rounded-md border"}>
      <ReactFlowProvider>
        <_Inner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
```

(Run-view callers omit `className` and keep the fixed height. Do not change `_Inner`.)

- [ ] **Step 2: Add `onBack` prop + `settingsOpen` state to `workflow-editor.tsx`**

Add `onBack?: () => void;` to `WorkflowEditorProps`, accept it in the destructure, and add `const [settingsOpen, setSettingsOpen] = useState(false);` alongside the other state. Update imports: add `ArrowLeft`, `Settings` to the `lucide-react` import (keep `Loader2`, `Plus`, `LayoutGrid`); add `import { WorkflowSettingsDrawer } from "./workflow-settings-drawer";`. Remove the now-unused `Tabs`/`Select` imports (they moved to the settings drawer); keep `Input`, `Label`, `Switch`, `Button`.

- [ ] **Step 3: Replace the `return (...)` JSX**

Replace the entire `return (...)` block (the `<form>...</form>`) with the topbar + full-canvas layout. Keep all existing state, `handleAddNode`, `handleAutoLayout`, `handleInsertNode`, `handleSubmit`, and `selectedNode` exactly as they are.

```tsx
  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-2 border-b px-3 py-2">
        {onBack && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onBack}
            aria-label="Back"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
        )}
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Workflow name"
          required
          aria-label="Workflow name"
          className="h-8 max-w-xs border-none px-1 text-base font-semibold shadow-none focus-visible:ring-1"
        />
        <div className="ml-auto flex items-center gap-2">
          <div className="mr-1 flex items-center gap-1.5">
            <Switch id="wf-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="wf-enabled" className="text-sm">
              Enabled
            </Label>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={handleAddNode}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Tarea
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleAutoLayout}
            disabled={nodes.length === 0}
          >
            <LayoutGrid className="mr-1.5 h-3.5 w-3.5" />
            Auto-ordenar
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings className="mr-1.5 h-3.5 w-3.5" />
            Settings
          </Button>
          <Button type="submit" size="sm" disabled={submitting || !name || nodes.length === 0}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </div>
      </div>

      {error && (
        <div className="border-b bg-destructive/10 px-3 py-1.5 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Canvas (full width/height) */}
      <div className="min-h-0 flex-1">
        {nodes.length === 0 ? (
          <div className="flex h-full items-center justify-center bg-muted/30 text-sm text-muted-foreground">
            Click &quot;+ Tarea&quot; to add your first node
          </div>
        ) : (
          <WorkflowCanvas
            nodes={nodes}
            className="h-full w-full"
            onChange={(updated) => setNodes(updated)}
            onSelectNode={(id) => setSelectedNodeId(id)}
            onInsertNode={handleInsertNode}
          />
        )}
      </div>

      {/* Settings drawer */}
      <WorkflowSettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        description={description}
        setDescription={setDescription}
        scheduleType={scheduleType}
        setScheduleType={setScheduleType}
        intervalValue={intervalValue}
        setIntervalValue={setIntervalValue}
        intervalUnit={intervalUnit}
        setIntervalUnit={setIntervalUnit}
        cronExpression={cronExpression}
        setCronExpression={setCronExpression}
        maxRunCount={maxRunCount}
        setMaxRunCount={setMaxRunCount}
      />

      {/* Node config drawer — unchanged */}
      {selectedNode && (
        <NodeConfigDrawer
          node={selectedNode}
          onChange={(updated) =>
            setNodes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)))
          }
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </form>
  );
```

(Note: `NodeConfigDrawer`'s `otherNodeIds` prop was removed earlier — keep the call exactly as it currently is in the file; do not re-add removed props. If the current call passes additional props, preserve them.)

- [ ] **Step 4: Update `WorkflowEditorPage.tsx` — drop its header, pass `onBack`, full-bleed**

The page currently renders its own `<header>` (back + "Create/Edit Workflow" title) and wraps the editor in a padded scroll container. Replace the success-path render so the editor fills the screen and owns the top bar:

```tsx
  return (
    <div className="flex h-screen flex-col">
      <WorkflowEditor
        key={workflow?.id ?? "new"}
        defaultValues={workflow ? _toDefaults(workflow) : undefined}
        nodes={workflow?.nodes}
        onBack={() => navigate(backTo)}
        onSubmit={handleSubmit}
        submitLabel={isEdit ? "Save Changes" : "Create Workflow"}
      />
    </div>
  );
```

Remove the now-unused `<header>`/`ArrowLeft`/title markup from the success path. Keep the `loading` spinner and the `!workflow` not-found states as they are (they still use their own `ArrowLeft`/`Link` — leave those imports if still used; if `ArrowLeft` becomes unused after removing the header, remove it from the page import).

- [ ] **Step 5: Verify**

Run: `cd packages/web && npm test && npx tsc -b --noEmit && npx vite build`
Expected: vitest 7/7; tsc 0 errors; vite build succeeds.

- [ ] **Step 6: Commit**

```bash
git add packages/web/src/components/workflows/workflow-editor.tsx packages/web/src/components/workflows/workflow-canvas.tsx packages/web/src/pages/WorkflowEditorPage.tsx
git commit -m "feat(web): n8n-style editor layout (topbar + full canvas + settings drawer)"
```

---

## Verification (end of plan)

- [ ] `cd packages/web && npm test` (vitest 7/7) · `npx tsc -b --noEmit` (0 errors) · `npx vite build` (succeeds).
- [ ] `grep -rn "xl:grid-cols" packages/web/src/components/workflows/workflow-editor.tsx` returns nothing (the 2-column grid is gone).
- [ ] `git status` still shows `task-detail-dialog.tsx` as an uncommitted modification (not swept into a commit).
- [ ] Manual smoke: open `/workflows/new` → top bar with inline name + Enabled toggle + + Tarea / Auto-ordenar / Settings / Create; canvas fills the page; Settings opens a drawer with description/schedule/max runs; create persists everything (name/schedule/enabled/nodes/positions) as before; same for edit at `/workflows/:id/edit`.

## Notes

- `WorkflowCanvas` is also used read-only in the run view; it keeps its default `h-[560px]` there because those callers don't pass `className`. Only the editor passes `className="h-full w-full"`.
- The Enabled toggle moved to the top bar; description/schedule/max runs moved to the Settings drawer. No fields were dropped — the submit payload (`handleSubmit` + page `_buildPayload`) is unchanged.
