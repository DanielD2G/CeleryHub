import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useCelery, useCeleryTasks } from "@/hooks/use-celery";
import type { CompletedTaskMeta } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AreaChart, Area } from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TaskDetailDialog } from "@/components/tasks/task-detail-dialog";
import {
  QueueSelector,
  ArgsBuilder,
  KwargsBuilder,
  serializeArgs,
  serializeKwargs,
} from "@/components/task-inputs";
import {
  ArrowLeft,
  Send,
  Clock,
  Loader2,
  CheckCircle,
  XCircle,
  Play,
  RotateCw,
  Timer,
} from "lucide-react";
import { formatSchedule } from "@/lib/scheduler/cron";

// --- helpers ---

function normalizeArgs(raw: string | undefined): string {
  if (!raw || raw === "()" || raw === "null") return "[]";
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(Array.isArray(parsed) ? parsed : []);
  } catch {
    return "[]";
  }
}

function normalizeKwargs(raw: string | undefined): string {
  if (!raw || raw === "null") return "{}";
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {});
  } catch {
    return "{}";
  }
}

const throughputConfig = {
  value: { label: "Tasks", color: "var(--chart-1)" },
} satisfies ChartConfig;

const runtimeConfig = {
  value: { label: "Runtime", color: "var(--chart-3)" },
} satisfies ChartConfig;

const rateConfig = {
  value: { label: "Rate", color: "var(--chart-2)" },
} satisfies ChartConfig;

function statusVariant(
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "SUCCESS":
      return "default";
    case "FAILURE":
      return "destructive";
    case "REVOKED":
      return "outline";
    default:
      return "secondary";
  }
}

function formatDuration(secs: number): string {
  if (secs < 60) return `${secs.toFixed(1)}s`;
  return `${Math.floor(secs / 60)}m ${Math.floor(secs % 60)}s`;
}

function Duration({
  since,
  avgRuntime,
}: {
  since: number;
  avgRuntime: number | null;
}) {
  const [elapsed, setElapsed] = useState("0.0s");
  const [remaining, setRemaining] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);

  useEffect(() => {
    const update = () => {
      const secs = Date.now() / 1000 - since;
      setElapsed(formatDuration(secs));

      if (avgRuntime != null && avgRuntime > 0) {
        const left = avgRuntime - secs;
        setProgress(Math.min((secs / avgRuntime) * 100, 100));
        if (left > 0) {
          setRemaining(`~${formatDuration(left)} left`);
        } else {
          setRemaining("overtime");
        }
      }
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [since, avgRuntime]);

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs">{elapsed}</span>
        {remaining && (
          <span
            className={`text-xs ${remaining === "overtime" ? "text-amber-500" : "text-muted-foreground"}`}
          >
            {remaining}
          </span>
        )}
      </div>
      {progress != null && (
        <div className="h-1.5 w-24 rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${progress >= 100 ? "bg-amber-500" : "bg-emerald-500"}`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

async function sendTask(body: {
  taskName: string;
  queue: string;
  args: string;
  kwargs: string;
}): Promise<{ taskId?: string; error?: string }> {
  const res = await fetch("/api/tasks/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function pollTaskStatus(
  taskId: string
): Promise<{ status: string; result: unknown } | null> {
  const res = await fetch(`/api/tasks/${taskId}/status`);
  if (!res.ok) return null;
  return res.json();
}

// --- page ---

export default function TaskGroupPage() {
  const { name } = useParams<{ name: string }>();
  const taskName = decodeURIComponent(name || "");
  const { completedTasks, knownQueues } = useCelery();
  const activeTasks = useCeleryTasks();

  const [selected, setSelected] = useState<CompletedTaskMeta | null>(null);

  // Beats that schedule this task
  interface BeatInfo {
    id: string;
    name: string;
    scheduleType: string;
    intervalSeconds: number | null;
    cronExpression: string | null;
    enabled: boolean | null;
  }
  const [beatsForTask, setBeatsForTask] = useState<BeatInfo[]>([]);

  useEffect(() => {
    fetch("/api/beats")
      .then((r) => r.json())
      .then((beats: Array<Record<string, unknown>>) => {
        const matching = beats.filter((b) => {
          const names: string[] = JSON.parse(
            (b.taskNames as string) || "[]"
          );
          return names.includes(taskName);
        });
        setBeatsForTask(
          matching.map((b) => ({
            id: b.id as string,
            name: b.name as string,
            scheduleType: b.scheduleType as string,
            intervalSeconds: b.intervalSeconds as number | null,
            cronExpression: b.cronExpression as string | null,
            enabled: b.enabled as boolean | null,
          }))
        );
      })
      .catch(() => {});
  }, [taskName]);

  // Send dialog state
  const [sendOpen, setSendOpen] = useState(false);
  const [queue, setQueue] = useState("celery");
  const [argItems, setArgItems] = useState<string[]>([]);
  const [kwargPairs, setKwargPairs] = useState<[string, string][]>([]);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<{
    taskId?: string;
    error?: string;
  } | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);

  // Retry state
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const queues = Array.from(knownQueues).sort();

  // Completed tasks for this name
  const history = Array.from(completedTasks.values())
    .filter((t) => t.name === taskName)
    .sort((a, b) => b.completedAt - a.completedAt);

  const successCount = history.filter((t) => t.status === "SUCCESS").length;
  const failureCount = history.filter((t) => t.status === "FAILURE").length;

  // Runtime estimate from successful executions (works with 1+ samples)
  const runtimes = history
    .filter((t) => t.status === "SUCCESS" && t.runtime != null)
    .map((t) => t.runtime!);
  const runtimeSamples = runtimes.length;
  const avgRuntime = runtimeSamples > 0
    ? runtimes.reduce((a, b) => a + b, 0) / runtimeSamples
    : null;

  const successRate = history.length > 0
    ? ((successCount / history.length) * 100).toFixed(1)
    : "—";

  const p95Runtime = runtimeSamples > 0
    ? (() => {
        const sorted = [...runtimes].sort((a, b) => a - b);
        return sorted[Math.floor(sorted.length * 0.95)] || sorted[sorted.length - 1];
      })()
    : null;

  const throughputSparkline = useMemo(() => {
    if (history.length === 0) return [];
    const buckets = new Map<string, number>();
    for (const task of history) {
      const date = new Date(task.completedAt * 1000);
      const key = `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }
    return Array.from(buckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, value]) => ({ time, value }));
  }, [history]);

  const runtimeSparkline = useMemo(() => {
    const withRuntime = history
      .filter((t) => t.status === "SUCCESS" && t.runtime != null)
      .sort((a, b) => a.completedAt - b.completedAt);
    if (withRuntime.length < 2) return [];
    const buckets = new Map<string, { total: number; count: number }>();
    for (const task of withRuntime) {
      const date = new Date(task.completedAt * 1000);
      const key = `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
      if (!buckets.has(key)) buckets.set(key, { total: 0, count: 0 });
      const b = buckets.get(key)!;
      b.total += task.runtime!;
      b.count++;
    }
    return Array.from(buckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, { total, count }]) => ({
        time,
        value: parseFloat((total / count).toFixed(3)),
      }));
  }, [history]);

  const rateSparkline = useMemo(() => {
    if (history.length === 0) return [];
    const sorted = [...history].sort((a, b) => a.completedAt - b.completedAt);
    const buckets = new Map<string, { success: number; total: number }>();
    for (const task of sorted) {
      const date = new Date(task.completedAt * 1000);
      const mins = Math.floor(date.getMinutes() / 5) * 5;
      const key = `${date.getHours().toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}`;
      if (!buckets.has(key)) buckets.set(key, { success: 0, total: 0 });
      const b = buckets.get(key)!;
      b.total++;
      if (task.status === "SUCCESS") b.success++;
    }
    return Array.from(buckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, { success, total }]) => ({
        time,
        value: total > 0 ? Math.round((success / total) * 100) : 0,
      }));
  }, [history]);

  // Active tasks for this name
  const activeForTask = Array.from(activeTasks.values()).filter(
    (t) => t.name === taskName
  );

  const handleSend = async () => {
    setSending(true);
    setSendResult(null);
    setTaskStatus(null);

    try {
      const res = await sendTask({
        taskName,
        queue,
        args: serializeArgs(argItems),
        kwargs: serializeKwargs(kwargPairs),
      });
      setSendResult(res);

      if (res.taskId) {
        let attempts = 0;
        const poll = async () => {
          if (attempts >= 30) {
            setTaskStatus("TIMEOUT");
            return;
          }
          attempts++;
          const status = await pollTaskStatus(res.taskId!);
          if (status && status.status !== "PENDING") {
            setTaskStatus(status.status);
          } else {
            setTaskStatus("PENDING");
            setTimeout(poll, 2000);
          }
        };
        setTimeout(poll, 1000);
      }
    } finally {
      setSending(false);
    }
  };

  const handleRetry = async (task: CompletedTaskMeta) => {
    setRetryingId(task.taskId);

    try {
      await sendTask({
        taskName,
        queue: "celery",
        args: normalizeArgs(task.args),
        kwargs: normalizeKwargs(task.kwargs),
      });
    } finally {
      setTimeout(() => setRetryingId(null), 1500);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link
          to="/tasks"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Tasks
        </Link>

        <Button
          onClick={() => {
            setSendResult(null);
            setTaskStatus(null);
            setArgItems([]);
            setKwargPairs([]);
            setQueue("celery");
            setSendOpen(true);
          }}
        >
          <Send className="mr-2 h-4 w-4" />
          Send Task
        </Button>
      </div>

      <div>
        <h2 className="text-xl font-bold tracking-tight lg:text-2xl">{taskName}</h2>
        {activeForTask.length > 0 && (
          <div className="mt-1">
            <Badge
              variant="outline"
              className="border-emerald-500/50 text-emerald-500"
            >
              <Play className="mr-0.5 h-2.5 w-2.5 fill-current" />
              {activeForTask.length} running
            </Badge>
          </div>
        )}
      </div>

      {/* KPIs */}
      {history.length > 0 && (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-3">
          {/* Throughput */}
          <Card className="py-3">
            <CardHeader className="flex flex-row items-center justify-between px-4 py-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Executions
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 py-0 pt-1">
              <div className="text-2xl font-bold tracking-tight">
                {history.length}
              </div>
              {throughputSparkline.length >= 2 && (
                <ChartContainer config={throughputConfig} className="mt-2 h-[40px] w-full">
                  <AreaChart data={throughputSparkline} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="spark-tg-throughput" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--color-value)" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="var(--color-value)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <ChartTooltip cursor={false} content={<ChartTooltipContent labelKey="time" />} />
                    <Area type="monotone" dataKey="value" stroke="var(--color-value)" fill="url(#spark-tg-throughput)" strokeWidth={1.5} dot={false} />
                  </AreaChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>

          {/* Success Rate */}
          <Card className="py-3">
            <CardHeader className="flex flex-row items-center justify-between px-4 py-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Success Rate
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 py-0 pt-1">
              <div className="text-2xl font-bold tracking-tight">
                {successRate}
                {successRate !== "—" && (
                  <span className="text-xs font-normal text-muted-foreground">%</span>
                )}
              </div>
              {rateSparkline.length >= 2 && (
                <ChartContainer config={rateConfig} className="mt-2 h-[40px] w-full">
                  <AreaChart data={rateSparkline} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="spark-tg-rate" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--color-value)" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="var(--color-value)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <ChartTooltip cursor={false} content={<ChartTooltipContent labelKey="time" valueFormatter={(v) => `${v}%`} />} />
                    <Area type="monotone" dataKey="value" stroke="var(--color-value)" fill="url(#spark-tg-rate)" strokeWidth={1.5} dot={false} />
                  </AreaChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>

          {/* Avg Runtime */}
          <Card className="py-3">
            <CardHeader className="flex flex-row items-center justify-between px-4 py-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Avg Runtime
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 py-0 pt-1">
              <div className="text-2xl font-bold tracking-tight">
                {avgRuntime != null
                  ? avgRuntime < 1
                    ? `${(avgRuntime * 1000).toFixed(0)}ms`
                    : `${avgRuntime.toFixed(2)}s`
                  : "—"}
                {p95Runtime != null && (
                  <span className="text-xs font-normal text-muted-foreground ml-1">
                    p95 {p95Runtime < 1 ? `${(p95Runtime * 1000).toFixed(0)}ms` : `${p95Runtime.toFixed(2)}s`}
                  </span>
                )}
              </div>
              {runtimeSparkline.length >= 2 && (
                <ChartContainer config={runtimeConfig} className="mt-2 h-[40px] w-full">
                  <AreaChart data={runtimeSparkline} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="spark-tg-runtime" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--color-value)" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="var(--color-value)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <ChartTooltip cursor={false} content={<ChartTooltipContent labelKey="time" valueFormatter={(v) => `${Number(v).toFixed(3)}s`} />} />
                    <Area type="monotone" dataKey="value" stroke="var(--color-value)" fill="url(#spark-tg-runtime)" strokeWidth={1.5} dot={false} />
                  </AreaChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Scheduled by beats */}
      {beatsForTask.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Timer className="h-4 w-4" />
            Scheduled by
          </h3>
          <div className="flex flex-wrap gap-2">
            {beatsForTask.map((b) => (
              <Link key={b.id} to={`/beats/${b.id}`}>
                <Badge
                  variant="outline"
                  className="gap-1.5 hover:bg-accent cursor-pointer"
                >
                  {b.name}
                  <span className="text-muted-foreground font-mono text-[10px]">
                    {formatSchedule(
                      b.scheduleType,
                      b.intervalSeconds,
                      b.cronExpression
                    )}
                  </span>
                  {!b.enabled && (
                    <span className="text-muted-foreground text-[10px]">
                      (disabled)
                    </span>
                  )}
                </Badge>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Active runs */}
      {activeForTask.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Play className="h-4 w-4 text-emerald-500" />
            Running now
            {avgRuntime != null && (
              <span className="font-normal text-xs text-muted-foreground">
                {runtimeSamples === 1 ? "est." : "avg"} {formatDuration(avgRuntime)}
              </span>
            )}
          </h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Worker</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Progress</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {activeForTask.map((task) => (
                <TableRow key={task.taskId}>
                  <TableCell className="font-mono text-xs">
                    {task.taskId.slice(0, 8)}...
                  </TableCell>
                  <TableCell>{task.worker || "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{task.status}</Badge>
                  </TableCell>
                  <TableCell>
                    <Duration since={task.startedAt} avgRuntime={avgRuntime} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      )}

      {/* Past executions */}
      <section className="space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Clock className="h-4 w-4" />
          Past Executions
        </h3>

        {history.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No completed executions yet.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Worker</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Runtime</TableHead>
                <TableHead>Completed</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((task) => (
                <TableRow
                  key={task.taskId}
                  className="cursor-pointer"
                  onClick={() => setSelected(task)}
                >
                  <TableCell className="font-mono text-xs">
                    {task.taskId.slice(0, 8)}...
                  </TableCell>
                  <TableCell>{task.worker || "—"}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(task.status)}>
                      {task.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {task.runtime != null
                      ? `${task.runtime.toFixed(3)}s`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(task.completedAt * 1000).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      title="Retry with same payload"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRetry(task);
                      }}
                      disabled={retryingId === task.taskId}
                    >
                      {retryingId === task.taskId ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <RotateCw className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      {/* Send dialog */}
      <Dialog open={sendOpen} onOpenChange={setSendOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Send className="h-4 w-4" />
              Send {taskName}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {sendResult && (
              <Card>
                <CardContent className="pt-4">
                  {sendResult.error ? (
                    <div className="flex items-center gap-2 text-sm text-destructive">
                      <XCircle className="h-4 w-4" />
                      {sendResult.error}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm">
                        <CheckCircle className="h-4 w-4 text-emerald-500" />
                        Task sent
                      </div>
                      <p className="font-mono text-xs text-muted-foreground">
                        {sendResult.taskId}
                      </p>
                      {taskStatus && (
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={
                              taskStatus === "SUCCESS"
                                ? "default"
                                : taskStatus === "FAILURE"
                                  ? "destructive"
                                  : "outline"
                            }
                          >
                            {taskStatus}
                          </Badge>
                          {taskStatus === "PENDING" && (
                            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Queue selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Queue</label>
              <QueueSelector
                value={queue}
                onChange={setQueue}
                queues={queues}
              />
            </div>

            {/* Args builder */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Args</label>
              <ArgsBuilder items={argItems} onChange={setArgItems} />
            </div>

            {/* Kwargs builder */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Kwargs</label>
              <KwargsBuilder pairs={kwargPairs} onChange={setKwargPairs} />
            </div>

            <Button
              className="w-full"
              onClick={handleSend}
              disabled={sending}
            >
              {sending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Send className="mr-2 h-4 w-4" />
              )}
              {argItems.length === 0 && kwargPairs.length === 0
                ? "Send without parameters"
                : "Send Task"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Detail dialog */}
      {selected && (
        <TaskDetailDialog
          task={{
            taskId: selected.taskId,
            status: selected.status,
            result: selected.result ?? null,
            traceback: selected.traceback ?? null,
            dateDone: new Date(selected.completedAt * 1000).toISOString(),
            name: selected.name,
            worker: selected.worker,
            runtime: selected.runtime,
            args: selected.args,
            kwargs: selected.kwargs,
          }}
          open={!!selected}
          onOpenChange={(open) => !open && setSelected(null)}
        />
      )}
    </div>
  );
}
