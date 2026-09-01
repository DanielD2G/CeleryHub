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
  WorkflowStepEditor,
  stepEditorToApi,
  type StepEditorState,
} from "./workflow-step-editor";
import { WorkflowDag } from "./workflow-dag";
import type { WorkflowStep } from "@/lib/types";

export interface CreateWorkflowInput {
  name: string;
  description: string | null;
  scheduleType: string;
  intervalSeconds?: number;
  cronExpression?: string;
  enabled: boolean;
  maxRunCount: number | null;
  expectSuccessWithinSeconds?: number | null;
  steps: {
    id: string;
    label: string;
    taskNames: string[];
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
    expectSuccessWithinSeconds?: number | null;
    steps: StepEditorState[];
  }>;
  onSubmit: (input: CreateWorkflowInput) => Promise<{ error?: string }>;
  submitLabel?: string;
}

let _nextStepId = 1;
function _generateStepId(): string {
  return `step-${Date.now()}-${_nextStepId++}`;
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
  const [expectSuccessWithin, setExpectSuccessWithin] = useState(
    initialValues?.expectSuccessWithinSeconds != null
      ? String(initialValues.expectSuccessWithinSeconds)
      : ""
  );
  const [steps, setSteps] = useState<StepEditorState[]>(
    initialValues?.steps || []
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

  const addStep = () => {
    setSteps([
      ...steps,
      {
        id: _generateStepId(),
        label: "",
        taskNames: [],
        dependsOn: [],
        condition: "all_succeeded",
        queue: "celery",
        argItems: [],
        kwargPairs: [],
        timeoutSeconds: null,
      },
    ]);
  };

  const updateStep = (index: number, updated: StepEditorState) => {
    setSteps(steps.map((s, i) => (i === index ? updated : s)));
  };

  const removeStep = (index: number) => {
    const removedId = steps[index].id;
    setSteps(
      steps
        .filter((_, i) => i !== index)
        .map((s) => ({
          ...s,
          dependsOn: s.dependsOn.filter((d) => d !== removedId),
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
      expectSuccessWithinSeconds: expectSuccessWithin
        ? parseInt(expectSuccessWithin, 10)
        : null,
      steps: steps.map(stepEditorToApi),
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

  // Build preview steps for the DAG
  const previewSteps: WorkflowStep[] = steps
    .filter((s) => s.label)
    .map((s) => ({
      id: s.id,
      label: s.label,
      taskNames: JSON.stringify(s.taskNames),
      args: null,
      kwargs: null,
      queue: s.queue || null,
      dependsOn: JSON.stringify(s.dependsOn),
      condition: s.condition,
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

          <div className="flex flex-wrap gap-6">
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
            <div className="space-y-2">
              <Label htmlFor="wf-dms">Alert if no success within (seconds)</Label>
              <Input
                id="wf-dms"
                type="number"
                min="60"
                value={expectSuccessWithin}
                onChange={(e) => setExpectSuccessWithin(e.target.value)}
                placeholder="Disabled"
                className="w-40"
              />
              <p className="text-xs text-muted-foreground">
                Dead man&apos;s switch — fires the alert rule even if CeleryHub
                itself was down when the schedule was missed.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Switch id="wf-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="wf-enabled">Enabled</Label>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button
            type="submit"
            disabled={submitting || !name || steps.length === 0}
            className="w-full"
          >
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </div>

        <div className="min-w-0 space-y-2">
          <Label>DAG Preview</Label>
          {previewSteps.length > 0 ? (
            <WorkflowDag steps={previewSteps} scheduleType={scheduleType} />
          ) : (
            <div className="rounded-lg border bg-muted/30 p-6 text-sm text-muted-foreground">
              Add at least one labeled step to preview the DAG.
            </div>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between pb-2">
          <Label>Steps ({steps.length})</Label>
          <Button type="button" variant="outline" size="sm" onClick={addStep}>
            <Plus className="mr-1.5 h-3 w-3" />
            Add Step
          </Button>
        </div>

        {steps.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Add at least one step to the workflow
          </p>
        )}

        {steps.map((step, i) => (
          <div key={step.id} className="relative">
            <div className="absolute -top-1 -right-1 z-10">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                onClick={() => removeStep(i)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
            <WorkflowStepEditor
              step={step}
              onChange={(updated) => updateStep(i, updated)}
              otherSteps={steps
                .filter((_, idx) => idx !== i)
                .map((s) => ({ id: s.id, label: s.label || `Step ${steps.indexOf(s) + 1}` }))}
            />
          </div>
        ))}
      </div>
    </form>
  );
}
