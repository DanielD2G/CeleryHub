import { useState } from "react";
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
import { Loader2, Plus, Trash2 } from "lucide-react";
import {
  WorkflowNodeEditor,
  nodeEditorToApi,
  type NodeEditorState,
} from "./workflow-node-editor";
import { WorkflowDag } from "./workflow-dag";
import type { WorkflowNode } from "@/lib/types";

export interface CreateWorkflowInput {
  name: string;
  description: string | null;
  scheduleType: string;
  intervalSeconds?: number;
  cronExpression?: string;
  enabled: boolean;
  maxRunCount: number | null;
  nodes: {
    id: string;
    label: string;
    taskName: string;
    args: string;
    kwargs: string;
    queue: string | null;
    dependsOn: string[];
    condition: string;
    timeoutSeconds: number | null;
  }[];
}

interface WorkflowFormProps {
  initialValues?: Partial<{
    name: string;
    description: string | null;
    scheduleType: string;
    intervalSeconds: number;
    cronExpression: string;
    enabled: boolean;
    maxRunCount: number | null;
    nodes: NodeEditorState[];
  }>;
  onSubmit: (input: CreateWorkflowInput) => Promise<{ error?: string }>;
  submitLabel?: string;
}

let _nextNodeId = 1;
function _generateNodeId(): string {
  return `node-${Date.now()}-${_nextNodeId++}`;
}

function _detectIntervalUnit(seconds: number): { value: number; unit: string } {
  if (seconds > 0 && seconds % 86400 === 0) return { value: seconds / 86400, unit: "days" };
  if (seconds > 0 && seconds % 3600 === 0) return { value: seconds / 3600, unit: "hours" };
  if (seconds > 0 && seconds % 60 === 0) return { value: seconds / 60, unit: "minutes" };
  return { value: seconds, unit: "seconds" };
}

export function WorkflowForm({
  initialValues,
  onSubmit,
  submitLabel = "Create Workflow",
}: WorkflowFormProps) {
  const [name, setName] = useState(initialValues?.name || "");
  const [description, setDescription] = useState(initialValues?.description || "");
  const [scheduleType, setScheduleType] = useState<"none" | "interval" | "cron">(
    (initialValues?.scheduleType as "none" | "interval" | "cron") || "none"
  );
  const { value: _detectedValue, unit: _detectedUnit } = _detectIntervalUnit(
    initialValues?.intervalSeconds ?? 0
  );
  const [intervalValue, setIntervalValue] = useState(
    initialValues?.intervalSeconds ? String(_detectedValue) : "10"
  );
  const [intervalUnit, setIntervalUnit] = useState(
    initialValues?.intervalSeconds ? _detectedUnit : "seconds"
  );
  const [cronExpression, setCronExpression] = useState(
    initialValues?.cronExpression || "* * * * *"
  );
  const [enabled, setEnabled] = useState(initialValues?.enabled !== false);
  const [maxRunCount, setMaxRunCount] = useState(
    initialValues?.maxRunCount != null ? String(initialValues.maxRunCount) : ""
  );
  const [nodes, setNodes] = useState<NodeEditorState[]>(
    initialValues?.nodes || []
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getIntervalSeconds = (): number => {
    const val = parseInt(intervalValue, 10) || 0;
    switch (intervalUnit) {
      case "minutes":
        return val * 60;
      case "hours":
        return val * 3600;
      case "days":
        return val * 86400;
      default:
        return val;
    }
  };

  const addNode = () => {
    setNodes([
      ...nodes,
      {
        id: _generateNodeId(),
        label: "",
        taskName: "",
        dependsOn: [],
        condition: "all_succeeded",
        queue: "celery",
        argItems: [],
        kwargPairs: [],
        timeoutSeconds: null,
      },
    ]);
  };

  const updateNode = (index: number, updated: NodeEditorState) => {
    setNodes(nodes.map((n, i) => (i === index ? updated : n)));
  };

  const removeNode = (index: number) => {
    const removedId = nodes[index].id;
    setNodes(
      nodes
        .filter((_, i) => i !== index)
        .map((n) => ({
          ...n,
          dependsOn: n.dependsOn.filter((d) => d !== removedId),
        }))
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    const input: CreateWorkflowInput = {
      name,
      description: description || null,
      scheduleType,
      intervalSeconds:
        scheduleType === "interval" ? getIntervalSeconds() : undefined,
      cronExpression:
        scheduleType === "cron" ? cronExpression : undefined,
      enabled,
      maxRunCount: maxRunCount ? parseInt(maxRunCount, 10) : null,
      nodes: nodes.map(nodeEditorToApi),
    };

    try {
      const result = await onSubmit(input);
      if (result.error) {
        setError(result.error);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  };

  // Build preview nodes for the DAG
  const previewNodes: WorkflowNode[] = nodes
    .filter((n) => n.label)
    .map((n) => ({
      id: n.id,
      label: n.label,
      taskName: n.taskName,
      args: null,
      kwargs: null,
      queue: n.queue || null,
      dependsOn: JSON.stringify(n.dependsOn),
      condition: n.condition,
      timeoutSeconds: null,
    }));

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(320px,1fr)_minmax(0,2fr)]">
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

        <div className="min-w-0 space-y-2">
          <Label>DAG Preview</Label>
          {previewNodes.length > 0 ? (
            <WorkflowDag nodes={previewNodes} scheduleType={scheduleType} />
          ) : (
            <div className="rounded-lg border bg-muted/30 p-6 text-sm text-muted-foreground">
              Add at least one labeled node to preview the DAG.
            </div>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between pb-2">
          <Label>Nodes ({nodes.length})</Label>
          <Button type="button" variant="outline" size="sm" onClick={addNode}>
            <Plus className="mr-1.5 h-3 w-3" />
            Add Node
          </Button>
        </div>

        {nodes.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Add at least one node to the workflow
          </p>
        )}

        {nodes.map((node, i) => (
          <div key={node.id} className="relative">
            <div className="absolute -top-1 -right-1 z-10">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                onClick={() => removeNode(i)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
            <WorkflowNodeEditor
              step={node}
              onChange={(updated) => updateNode(i, updated)}
              otherNodes={nodes
                .filter((_, idx) => idx !== i)
                .map((n) => ({ id: n.id, label: n.label || `Node ${nodes.indexOf(n) + 1}` }))}
            />
          </div>
        ))}
      </div>
    </form>
  );
}
