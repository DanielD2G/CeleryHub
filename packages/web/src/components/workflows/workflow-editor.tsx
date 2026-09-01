import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ArrowLeft, Loader2, Plus, LayoutGrid, Settings } from "lucide-react";
import type { WorkflowNode } from "@/lib/types";
import { WorkflowCanvas } from "./workflow-canvas";
import { NodeConfigDrawer } from "./node-config-drawer";
import { WorkflowSettingsDrawer } from "./workflow-settings-drawer";
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
  onBack?: () => void;
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
  onBack,
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
  const [settingsOpen, setSettingsOpen] = useState(false);

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
}
