import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiGet } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDurationSeconds } from "@/lib/workflow-utils";
import { AlertTriangle } from "lucide-react";

interface DailyStat {
  day: string;
  succeeded: number;
  failed: number;
  runtimeAvg: number | null;
  runtimeP50: number | null;
  runtimeP95: number | null;
}

interface ExceptionHistoryItem {
  taskName: string;
  exception: string;
  count: number;
  firstDay: string;
  lastDay: string;
  lastSeen: string | null;
}

interface Anomaly {
  kind: string;
  taskName: string;
  taskId: string | null;
  detectedAt: string | null;
  detail: string;
}

interface UsingWorkflow {
  workflowId: string;
  workflowName: string;
  stepLabel: string;
}

export function TaskHistoryPanel({ taskName }: { taskName: string }) {
  const [daily, setDaily] = useState<DailyStat[] | null>(null);
  const [exceptions, setExceptions] = useState<ExceptionHistoryItem[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [workflows, setWorkflows] = useState<UsingWorkflow[]>([]);

  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setRefreshTick((v) => v + 1), 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const enc = encodeURIComponent(taskName);
    apiGet<DailyStat[]>(
      `/api/event-log/stats/daily?taskName=${enc}&days=30`,
      controller.signal
    )
      .then(setDaily)
      .catch(() => setDaily([]));
    apiGet<ExceptionHistoryItem[]>(
      `/api/event-log/exceptions/history?taskName=${enc}&days=365&limit=10`,
      controller.signal
    )
      .then(setExceptions)
      .catch(() => {});
    apiGet<Anomaly[]>(`/api/event-log/anomalies`, controller.signal)
      .then((all) => setAnomalies(all.filter((a) => a.taskName === taskName)))
      .catch(() => {});
    apiGet<UsingWorkflow[]>(
      `/api/workflows/using-task/${enc}`,
      controller.signal
    )
      .then(setWorkflows)
      .catch(() => {});
    return () => controller.abort();
  }, [taskName, refreshTick]);

  const hasSeries = (daily ?? []).some((d) => d.succeeded + d.failed > 0);

  return (
    <div className="space-y-4">
      {anomalies.length > 0 && (
        <div className="space-y-2">
          {anomalies.map((a) => (
            <div
              key={a.kind + a.detail}
              className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              <div>
                <span className="font-medium">
                  {a.kind === "slow_run" ? "Slow run" : "Failure streak"}:
                </span>{" "}
                {a.detail}
              </div>
            </div>
          ))}
        </div>
      )}

      {hasSeries && daily && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Runtime p50 / p95 — 30 days</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={140}>
                <AreaChart data={daily} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="day"
                    tick={{ fontSize: 10 }}
                    tickLine={false}
                    tickFormatter={(d: string) => d.slice(5)}
                  />
                  <YAxis
                    width={44}
                    tick={{ fontSize: 10 }}
                    tickLine={false}
                    tickFormatter={(v: number) => formatDurationSeconds(v)}
                  />
                  <Tooltip
                    formatter={(v: number, name: string) => [
                      formatDurationSeconds(v ?? 0),
                      name,
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="runtimeP95"
                    name="p95"
                    stroke="var(--color-amber-500, #f59e0b)"
                    fill="var(--color-amber-500, #f59e0b)"
                    fillOpacity={0.12}
                  />
                  <Area
                    type="monotone"
                    dataKey="runtimeP50"
                    name="p50"
                    stroke="var(--color-sky-500, #0ea5e9)"
                    fill="var(--color-sky-500, #0ea5e9)"
                    fillOpacity={0.25}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Outcomes per day — 30 days</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={daily} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="day"
                    tick={{ fontSize: 10 }}
                    tickLine={false}
                    tickFormatter={(d: string) => d.slice(5)}
                  />
                  <YAxis width={30} tick={{ fontSize: 10 }} tickLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Bar
                    dataKey="succeeded"
                    name="succeeded"
                    stackId="a"
                    fill="var(--color-emerald-500, #10b981)"
                  />
                  <Bar
                    dataKey="failed"
                    name="failed"
                    stackId="a"
                    fill="var(--color-red-500, #ef4444)"
                    radius={[2, 2, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}

      {workflows.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Used by:</span>
          {workflows.map((w) => (
            <Link key={w.workflowId + w.stepLabel} to={`/workflows/${w.workflowId}`}>
              <Badge variant="outline" className="hover:bg-accent">
                {w.workflowName} · {w.stepLabel}
              </Badge>
            </Link>
          ))}
        </div>
      )}

      {exceptions.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Exception history — 12 months</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Exception</TableHead>
                    <TableHead className="w-20 text-right">Count</TableHead>
                    <TableHead className="w-28">Last seen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {exceptions.map((e) => (
                    <TableRow key={e.exception}>
                      <TableCell className="max-w-md truncate font-mono text-xs">
                        {e.exception}
                      </TableCell>
                      <TableCell className="text-right text-sm">{e.count}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {e.lastDay}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
