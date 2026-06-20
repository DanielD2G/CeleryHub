import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, Plus, LayoutGrid } from "lucide-react";
import type { WorkflowNode } from "@/lib/types";
import { WorkflowCanvas } from "./workflow-canvas";
import { NodeConfigDrawer } from "./node-config-drawer";
import { nodesToFlow, autoLayout } from "@/lib/workflow-graph";

export interface WorkflowFormValues {
  name: string;
  description: string;
  scheduleType: "none" | "interval" | "cron";
  intervalValue: string;
  intervalUnit: string;
  cronExpression: string;
  enabled: boolean;
  maxRunCount: string;
}

export interface WorkflowEditorProps {
  defaultValues?: Partial<WorkflowFormValues>;
  nodes?: WorkflowNode[];
  onSubmit: (values: WorkflowFormValues, nodes: WorkflowNode[]) => Promise<void>;
  submitLabel?: string;
}

function _detectIntervalUnit(seconds: number): { value: number; unit: string } {
  if (seconds > 0 && seconds % 86400 === 0) return { value: seconds / 86400, unit: "days" };
  if (seconds > 0 && seconds % 3600 === 0) return { value: seconds / 3600, unit: "hours" };
  if (seconds > 0 && seconds % 60 === 0) return { value: seconds / 60, unit: "minutes" };
  return { value: seconds, unit: "seconds" };
}

export { _detectIntervalUnit };

export function _toIntervalSeconds(value: string, unit: string): number {
  const val = parseInt(value, 10) || 0;
  switch (unit) {
    case "minutes":
      return val * 60;
    case "hours":
      return val * 3600;
    case "days":
      return val * 86400;
    default:
      return val;
  }
}

export function WorkflowEditor({
  defaultValues,
  nodes: initialNodes,
  onSubmit,
  submitLabel = "Create Workflow",
}: WorkflowEditorProps) {
  const [name, setName] = useState(defaultValues?.name ?? "");
  const [description, setDescription] = useState(defaultValues?.description ?? "");
  const [scheduleType, setScheduleType] = useState<"none" | "interval" | "cron">(
    defaultValues?.scheduleType ?? "none",
  );
  const [intervalValue, setIntervalValue] = useState(defaultValues?.intervalValue ?? "10");
  const [intervalUnit, setIntervalUnit] = useState(defaultValues?.intervalUnit ?? "seconds");
  const [cronExpression, setCronExpression] = useState(
    defaultValues?.cronExpression ?? "* * * * *",
  );
  const [enabled, setEnabled] = useState(defaultValues?.enabled !== false);
  const [maxRunCount, setMaxRunCount] = useState(defaultValues?.maxRunCount ?? "");
  const [nodes, setNodes] = useState<WorkflowNode[]>(initialNodes ?? []);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) ?? null;

  const handleAddNode = () => {
    const newNode: WorkflowNode = {
      id: crypto.randomUUID(),
      label: `Task ${nodes.length + 1}`,
      taskName: "",
      args: "[]",
      kwargs: "{}",
      queue: null,
      dependsOn: "[]",
      condition: "all_succeeded",
      timeoutSeconds: null,
      positionX: null,
      positionY: null,
      position: { x: 250, y: 200 },
    };
    setNodes((prev) => [...prev, newNode]);
  };

  const handleAutoLayout = () => {
    const { flowNodes, flowEdges } = nodesToFlow(nodes);
    const laid = autoLayout(flowNodes, flowEdges);
    const posMap = new Map(laid.map((n) => [n.id, n.position]));
    setNodes(nodes.map((n) => ({ ...n, position: posMap.get(n.id) ?? n.position })));
  };

  const handleInsertNode = useCallback(
    (edgeId: string) => {
      const [source, target] = edgeId.split("->");
      const newNode: WorkflowNode = {
        id: crypto.randomUUID(),
        label: `Task ${nodes.length + 1}`,
        taskName: "",
        args: "[]",
        kwargs: "{}",
        queue: null,
        dependsOn: JSON.stringify([source]),
        condition: "all_succeeded",
        timeoutSeconds: null,
        positionX: null,
        positionY: null,
        position: { x: 250, y: 200 },
      };
      setNodes((prev) => [
        ...prev.map((n) => {
          if (n.id !== target) return n;
          const deps: string[] = JSON.parse(n.dependsOn);
          return {
            ...n,
            dependsOn: JSON.stringify(deps.map((d) => (d === source ? newNode.id : d))),
          };
        }),
        newNode,
      ]);
    },
    [nodes.length],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(
        {
          name,
          description,
          scheduleType,
          intervalValue,
          intervalUnit,
          cronExpression,
          enabled,
          maxRunCount,
        },
        nodes,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(320px,1fr)_minmax(0,2fr)]">
        {/* Left column: workflow-level fields */}
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="wf-name">Workflow Name</Label>
            <Input
              id="wf-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Daily ETL Pipeline"
              required
            />
          </div>

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
            <Tabs
              value={scheduleType}
              onValueChange={(v) => setScheduleType(v as "none" | "interval" | "cron")}
            >
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

          <div className="flex items-center gap-2">
            <Switch id="wf-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="wf-enabled">Enabled</Label>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button
            type="submit"
            disabled={submitting || !name || nodes.length === 0}
            className="w-full"
          >
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </div>

        {/* Right column: canvas + toolbar */}
        <div className="min-w-0 space-y-2">
          <div className="flex items-center justify-between">
            <Label>Canvas ({nodes.length} node{nodes.length !== 1 ? "s" : ""})</Label>
            <div className="flex gap-2">
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
            </div>
          </div>

          {nodes.length === 0 ? (
            <div className="flex h-[560px] items-center justify-center rounded-md border bg-muted/30 text-sm text-muted-foreground">
              Click &quot;+ Tarea&quot; to add your first node
            </div>
          ) : (
            <WorkflowCanvas
              nodes={nodes}
              onChange={(updated) => setNodes(updated)}
              onSelectNode={(id) => setSelectedNodeId(id)}
              onInsertNode={handleInsertNode}
            />
          )}
        </div>
      </div>

      {/* Node config drawer — rendered outside the grid so it slides over everything */}
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
}
