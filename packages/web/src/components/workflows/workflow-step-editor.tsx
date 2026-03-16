import { useState } from "react";
import { useCelery } from "@/hooks/use-celery";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  QueueSelector,
  ArgsBuilder,
  KwargsBuilder,
  parseArgsToItems,
  parseKwargsToPairs,
  serializeArgs,
  serializeKwargs,
} from "@/components/task-inputs";
import { X } from "lucide-react";

export interface StepEditorState {
  id: string;
  label: string;
  taskNames: string[];
  dependsOn: string[];
  condition: string;
  queue: string;
  argItems: string[];
  kwargPairs: [string, string][];
  timeoutSeconds: number | null;
}

interface WorkflowStepEditorProps {
  step: StepEditorState;
  onChange: (step: StepEditorState) => void;
  otherSteps: { id: string; label: string }[];
}

export function WorkflowStepEditor({
  step,
  onChange,
  otherSteps,
}: WorkflowStepEditorProps) {
  const { knownTaskNames, knownQueues } = useCelery();
  const [taskSearch, setTaskSearch] = useState("");
  const [showTaskDropdown, setShowTaskDropdown] = useState(false);
  const [depSearch, setDepSearch] = useState("");
  const [showDepDropdown, setShowDepDropdown] = useState(false);

  const queues = Array.from(knownQueues).sort();

  const availableTasks = Array.from(knownTaskNames)
    .filter((n) => !step.taskNames.includes(n))
    .filter((n) =>
      taskSearch ? n.toLowerCase().includes(taskSearch.toLowerCase()) : true
    )
    .sort((a, b) => a.localeCompare(b));

  const availableDeps = otherSteps
    .filter((s) => !step.dependsOn.includes(s.id))
    .filter((s) =>
      depSearch ? s.label.toLowerCase().includes(depSearch.toLowerCase()) : true
    );

  const addTask = (taskName: string) => {
    if (!step.taskNames.includes(taskName)) {
      onChange({ ...step, taskNames: [...step.taskNames, taskName] });
    }
    setTaskSearch("");
  };

  const removeTask = (taskName: string) => {
    onChange({ ...step, taskNames: step.taskNames.filter((t) => t !== taskName) });
  };

  const addDep = (depId: string) => {
    if (!step.dependsOn.includes(depId)) {
      onChange({ ...step, dependsOn: [...step.dependsOn, depId] });
    }
    setDepSearch("");
  };

  const removeDep = (depId: string) => {
    onChange({ ...step, dependsOn: step.dependsOn.filter((d) => d !== depId) });
  };

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="space-y-1.5">
        <Label>Label</Label>
        <Input
          value={step.label}
          onChange={(e) => onChange({ ...step, label: e.target.value })}
          placeholder="e.g. Extract data"
        />
      </div>

      <div className="space-y-1.5">
        <Label>Tasks</Label>
        {step.taskNames.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {step.taskNames.map((t) => (
              <Badge key={t} variant="secondary" className="gap-1 pr-1 font-mono text-xs">
                {t}
                <button
                  type="button"
                  onClick={() => removeTask(t)}
                  className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
        <div className="relative">
          <Input
            value={taskSearch}
            onChange={(e) => {
              setTaskSearch(e.target.value);
              setShowTaskDropdown(true);
            }}
            onFocus={() => setShowTaskDropdown(true)}
            onBlur={() => setTimeout(() => setShowTaskDropdown(false), 200)}
            placeholder={
              step.taskNames.length > 0
                ? "Add another task..."
                : "Search and select tasks..."
            }
          />
          {showTaskDropdown && availableTasks.length > 0 && (
            <div className="absolute top-full left-0 z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-md border bg-popover p-1 shadow-md">
              {availableTasks.map((n) => (
                <button
                  key={n}
                  type="button"
                  className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent font-mono"
                  onMouseDown={() => addTask(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          )}
        </div>
        {taskSearch &&
          !knownTaskNames.has(taskSearch) &&
          !step.taskNames.includes(taskSearch) && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => addTask(taskSearch)}
            >
              + Add &quot;{taskSearch}&quot; as custom task
            </button>
          )}
      </div>

      <div className="space-y-1.5">
        <Label>Dependencies</Label>
        {step.dependsOn.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {step.dependsOn.map((depId) => {
              const depStep = otherSteps.find((s) => s.id === depId);
              return (
                <Badge key={depId} variant="outline" className="gap-1 pr-1 text-xs">
                  {depStep?.label || depId}
                  <button
                    type="button"
                    onClick={() => removeDep(depId)}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              );
            })}
          </div>
        )}
        {otherSteps.length > 0 && (
          <div className="relative">
            <Input
              value={depSearch}
              onChange={(e) => {
                setDepSearch(e.target.value);
                setShowDepDropdown(true);
              }}
              onFocus={() => setShowDepDropdown(true)}
              onBlur={() => setTimeout(() => setShowDepDropdown(false), 200)}
              placeholder="Select dependency steps..."
            />
            {showDepDropdown && availableDeps.length > 0 && (
              <div className="absolute top-full left-0 z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-md border bg-popover p-1 shadow-md">
                {availableDeps.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                    onMouseDown={() => addDep(s.id)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Condition</Label>
          <Select
            value={step.condition}
            onValueChange={(v) => onChange({ ...step, condition: v })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all_succeeded">All Succeeded</SelectItem>
              <SelectItem value="all_completed">All Completed</SelectItem>
              <SelectItem value="any_succeeded">Any Succeeded</SelectItem>
              <SelectItem value="any_failed">Any Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label>Queue</Label>
          <QueueSelector
            value={step.queue}
            onChange={(v) => onChange({ ...step, queue: v })}
            queues={queues}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Timeout (seconds)</Label>
        <Input
          type="number"
          min={0}
          value={step.timeoutSeconds ?? ""}
          onChange={(e) =>
            onChange({
              ...step,
              timeoutSeconds: e.target.value ? parseInt(e.target.value, 10) : null,
            })
          }
          placeholder="No timeout"
          className="w-40"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Args</Label>
          <ArgsBuilder
            items={step.argItems}
            onChange={(items) => onChange({ ...step, argItems: items })}
          />
        </div>

        <div className="space-y-1.5">
          <Label>Kwargs</Label>
          <KwargsBuilder
            pairs={step.kwargPairs}
            onChange={(pairs) => onChange({ ...step, kwargPairs: pairs })}
          />
        </div>
      </div>
    </div>
  );
}

// Helper functions to convert between StepEditorState and API format
export function stepEditorToApi(step: StepEditorState): {
  id: string;
  label: string;
  taskNames: string[];
  args: string;
  kwargs: string;
  queue: string | null;
  dependsOn: string[];
  condition: string;
  timeoutSeconds: number | null;
} {
  return {
    id: step.id,
    label: step.label,
    taskNames: step.taskNames,
    args: serializeArgs(step.argItems),
    kwargs: serializeKwargs(step.kwargPairs),
    queue: step.queue || null,
    dependsOn: step.dependsOn,
    condition: step.condition,
    timeoutSeconds: step.timeoutSeconds,
  };
}

export function apiToStepEditor(step: {
  id: string;
  label: string;
  taskNames: string;
  args: string | null;
  kwargs: string | null;
  queue: string | null;
  dependsOn: string;
  condition: string;
  timeoutSeconds?: number | null;
}): StepEditorState {
  return {
    id: step.id,
    label: step.label,
    taskNames: JSON.parse(step.taskNames || "[]"),
    dependsOn: JSON.parse(step.dependsOn || "[]"),
    condition: step.condition,
    queue: step.queue || "celery",
    argItems: parseArgsToItems(step.args || "[]"),
    kwargPairs: parseKwargsToPairs(step.kwargs || "{}"),
    timeoutSeconds: step.timeoutSeconds ?? null,
  };
}
