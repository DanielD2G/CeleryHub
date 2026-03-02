import { useState } from "react";
import { useCelery } from "@/hooks/use-celery";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  QueueSelector,
  ArgsBuilder,
  KwargsBuilder,
  serializeArgs,
  serializeKwargs,
  parseArgsToItems,
  parseKwargsToPairs,
} from "@/components/task-inputs";
import { Loader2, X } from "lucide-react";

export interface CreateBeatInput {
  name: string;
  taskNames: string[];
  args: string;
  kwargs: string;
  queue: string;
  scheduleType: string;
  intervalSeconds?: number;
  cronExpression?: string;
  enabled: boolean;
  maxRunCount: number | null;
}

interface BeatFormProps {
  initialValues?: Partial<CreateBeatInput & { enabled: boolean }>;
  onSubmit: (input: CreateBeatInput) => Promise<{ error?: string }>;
  submitLabel?: string;
}

export function BeatForm({
  initialValues,
  onSubmit,
  submitLabel = "Create Beat",
}: BeatFormProps) {
  const { knownTaskNames, knownQueues } = useCelery();
  const [name, setName] = useState(initialValues?.name || "");
  const [selectedTasks, setSelectedTasks] = useState<string[]>(
    initialValues?.taskNames || []
  );
  const [taskSearch, setTaskSearch] = useState("");
  const [showTaskDropdown, setShowTaskDropdown] = useState(false);
  const [queue, setQueue] = useState(initialValues?.queue || "celery");
  const [argItems, setArgItems] = useState<string[]>(
    parseArgsToItems(initialValues?.args || "[]")
  );
  const [kwargPairs, setKwargPairs] = useState<[string, string][]>(
    parseKwargsToPairs(initialValues?.kwargs || "{}")
  );
  const [scheduleType, setScheduleType] = useState<"interval" | "cron">(
    (initialValues?.scheduleType as "interval" | "cron") || "interval"
  );
  const [intervalValue, setIntervalValue] = useState(
    initialValues?.intervalSeconds
      ? String(initialValues.intervalSeconds)
      : "10"
  );
  const [intervalUnit, setIntervalUnit] = useState("seconds");
  const [cronExpression, setCronExpression] = useState(
    initialValues?.cronExpression || "* * * * *"
  );
  const [enabled, setEnabled] = useState(initialValues?.enabled !== false);
  const [maxRunCount, setMaxRunCount] = useState(
    initialValues?.maxRunCount != null ? String(initialValues.maxRunCount) : ""
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const queues = Array.from(knownQueues).sort();

  // Filter available tasks: not already selected, matching search
  const availableTasks = Array.from(knownTaskNames)
    .filter((n) => !selectedTasks.includes(n))
    .filter((n) =>
      taskSearch ? n.toLowerCase().includes(taskSearch.toLowerCase()) : true
    );

  const addTask = (taskName: string) => {
    if (!selectedTasks.includes(taskName)) {
      setSelectedTasks([...selectedTasks, taskName]);
    }
    setTaskSearch("");
  };

  const removeTask = (taskName: string) => {
    setSelectedTasks(selectedTasks.filter((t) => t !== taskName));
  };

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    const input: CreateBeatInput = {
      name,
      taskNames: selectedTasks,
      args: serializeArgs(argItems),
      kwargs: serializeKwargs(kwargPairs),
      queue,
      scheduleType,
      intervalSeconds:
        scheduleType === "interval" ? getIntervalSeconds() : undefined,
      cronExpression:
        scheduleType === "cron" ? cronExpression : undefined,
      enabled,
      maxRunCount: maxRunCount ? parseInt(maxRunCount, 10) : null,
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

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="beat-name">Beat Name</Label>
        <Input
          id="beat-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Process daily reports"
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="beat-task-search">Tasks</Label>

        {/* Selected tasks as chips */}
        {selectedTasks.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {selectedTasks.map((t) => (
              <Badge
                key={t}
                variant="secondary"
                className="gap-1 pr-1 font-mono text-xs"
              >
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

        {/* Search input + dropdown */}
        <div className="relative">
          <Input
            id="beat-task-search"
            value={taskSearch}
            onChange={(e) => {
              setTaskSearch(e.target.value);
              setShowTaskDropdown(true);
            }}
            onFocus={() => setShowTaskDropdown(true)}
            onBlur={() => setTimeout(() => setShowTaskDropdown(false), 200)}
            placeholder={
              selectedTasks.length > 0
                ? "Add another task..."
                : "Search and select tasks..."
            }
          />
          {showTaskDropdown && availableTasks.length > 0 && (
            <div className="absolute top-full left-0 z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-md border bg-popover p-1 shadow-md">
              {availableTasks.slice(0, 12).map((n) => (
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

        {/* Manual entry: allow typing a custom task name */}
        {taskSearch &&
          !knownTaskNames.has(taskSearch) &&
          !selectedTasks.includes(taskSearch) && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => addTask(taskSearch)}
            >
              + Add &quot;{taskSearch}&quot; as custom task
            </button>
          )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="beat-interval">Schedule</Label>
        <Tabs
          value={scheduleType}
          onValueChange={(v) => setScheduleType(v as "interval" | "cron")}
        >
          <TabsList>
            <TabsTrigger value="interval">Interval</TabsTrigger>
            <TabsTrigger value="cron">Cron</TabsTrigger>
          </TabsList>
          <TabsContent value="interval">
            <div className="flex gap-2 mt-2">
              <Input
                id="beat-interval"
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
              id="beat-cron"
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

      <div className="space-y-1.5">
        <Label htmlFor="beat-queue">Queue</Label>
        <QueueSelector value={queue} onChange={setQueue} queues={queues} />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="beat-args">Args</Label>
        <ArgsBuilder items={argItems} onChange={setArgItems} />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="beat-kwargs">Kwargs</Label>
        <KwargsBuilder pairs={kwargPairs} onChange={setKwargPairs} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="max-runs">Max Run Count (optional)</Label>
        <Input
          id="max-runs"
          type="number"
          min="1"
          value={maxRunCount}
          onChange={(e) => setMaxRunCount(e.target.value)}
          placeholder="Unlimited"
          className="w-40"
        />
      </div>

      <div className="flex items-center gap-2">
        <Switch id="enabled" checked={enabled} onCheckedChange={setEnabled} />
        <Label htmlFor="enabled">Enabled</Label>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button
        type="submit"
        disabled={submitting || !name || selectedTasks.length === 0}
      >
        {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {submitLabel}
      </Button>
    </form>
  );
}
