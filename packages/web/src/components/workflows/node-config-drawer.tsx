import { useState } from "react";
import { useCelery } from "@/hooks/use-celery";
import { WorkflowNode } from "@/lib/types";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
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

interface NodeConfigDrawerProps {
  node: WorkflowNode | null;
  otherNodeIds: { id: string; label: string }[];
  onChange: (node: WorkflowNode) => void;
  onClose: () => void;
}

export function NodeConfigDrawer({
  node,
  otherNodeIds: _otherNodeIds,
  onChange,
  onClose,
}: NodeConfigDrawerProps) {
  const { knownTaskNames, knownQueues } = useCelery();
  const [taskSearch, setTaskSearch] = useState("");
  const [showTaskDropdown, setShowTaskDropdown] = useState(false);

  const queues = Array.from(knownQueues).sort();

  const availableTasks = Array.from(knownTaskNames)
    .filter((n) =>
      taskSearch ? n.toLowerCase().includes(taskSearch.toLowerCase()) : true
    )
    .sort((a, b) => a.localeCompare(b));

  const selectTask = (taskName: string) => {
    if (!node) return;
    onChange({ ...node, taskName });
    setTaskSearch("");
    setShowTaskDropdown(false);
  };

  const clearTask = () => {
    if (!node) return;
    onChange({ ...node, taskName: "" });
    setTaskSearch("");
  };

  const argItems = node ? parseArgsToItems(node.args ?? "[]") : [];
  const kwargPairs = node ? parseKwargsToPairs(node.kwargs ?? "{}") : [];

  const handleArgsChange = (items: string[]) => {
    if (!node) return;
    onChange({ ...node, args: serializeArgs(items) });
  };

  const handleKwargsChange = (pairs: [string, string][]) => {
    if (!node) return;
    onChange({ ...node, kwargs: serializeKwargs(pairs) });
  };

  return (
    <Sheet open={node !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent side="right" className="w-96 sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Configure Node</SheetTitle>
          <SheetDescription>
            Edit the configuration for the selected workflow node.
          </SheetDescription>
        </SheetHeader>

        {node && (
          <div className="space-y-4 p-4">
            {/* Label */}
            <div className="space-y-1.5">
              <Label htmlFor="node-label">Label</Label>
              <Input
                id="node-label"
                value={node.label}
                onChange={(e) => onChange({ ...node, label: e.target.value })}
                placeholder="e.g. Extract data"
              />
            </div>

            {/* Task Name */}
            <div className="space-y-1.5">
              <Label>Task</Label>
              {node.taskName ? (
                <div className="flex items-center gap-1.5">
                  <Badge variant="secondary" className="gap-1 pr-1 font-mono text-xs">
                    {node.taskName}
                    <button
                      type="button"
                      onClick={clearTask}
                      className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                </div>
              ) : (
                <div className="relative">
                  <Input
                    value={taskSearch}
                    onChange={(e) => {
                      setTaskSearch(e.target.value);
                      setShowTaskDropdown(true);
                    }}
                    onFocus={() => setShowTaskDropdown(true)}
                    onBlur={() => setTimeout(() => setShowTaskDropdown(false), 200)}
                    placeholder="Search and select a task..."
                  />
                  {showTaskDropdown && availableTasks.length > 0 && (
                    <div className="absolute top-full left-0 z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-md border bg-popover p-1 shadow-md">
                      {availableTasks.map((n) => (
                        <button
                          key={n}
                          type="button"
                          className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent font-mono"
                          onMouseDown={() => selectTask(n)}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {!node.taskName && taskSearch && !knownTaskNames.has(taskSearch) && (
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => selectTask(taskSearch)}
                >
                  + Use &quot;{taskSearch}&quot; as custom task
                </button>
              )}
            </div>

            {/* Queue */}
            <div className="space-y-1.5">
              <Label>Queue</Label>
              <QueueSelector
                value={node.queue ?? "celery"}
                onChange={(v) => onChange({ ...node, queue: v || null })}
                queues={queues}
              />
            </div>

            {/* Condition */}
            <div className="space-y-1.5">
              <Label>Condition</Label>
              <Select
                value={node.condition}
                onValueChange={(v) => onChange({ ...node, condition: v })}
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

            {/* Timeout */}
            <div className="space-y-1.5">
              <Label htmlFor="node-timeout">Timeout (seconds)</Label>
              <Input
                id="node-timeout"
                type="number"
                min={0}
                value={node.timeoutSeconds ?? ""}
                onChange={(e) =>
                  onChange({
                    ...node,
                    timeoutSeconds: e.target.value
                      ? parseInt(e.target.value, 10)
                      : null,
                  })
                }
                placeholder="No timeout"
                className="w-40"
              />
            </div>

            {/* Args */}
            <div className="space-y-1.5">
              <Label>Args</Label>
              <ArgsBuilder items={argItems} onChange={handleArgsChange} />
            </div>

            {/* Kwargs */}
            <div className="space-y-1.5">
              <Label>Kwargs</Label>
              <KwargsBuilder pairs={kwargPairs} onChange={handleKwargsChange} />
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
