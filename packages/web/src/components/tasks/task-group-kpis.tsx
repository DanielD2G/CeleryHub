import { useMemo } from "react";
import type { CompletedTaskMeta } from "@/lib/types";
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

const _throughputConfig = {
  value: { label: "Tasks", color: "var(--chart-1)" },
} satisfies ChartConfig;

const _runtimeConfig = {
  value: { label: "Runtime", color: "var(--chart-3)" },
} satisfies ChartConfig;

const _rateConfig = {
  value: { label: "Rate", color: "var(--chart-2)" },
} satisfies ChartConfig;

interface SparklinePoint {
  time: string;
  value: number;
}

function _buildThroughputSparkline(history: CompletedTaskMeta[]): SparklinePoint[] {
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
}

function _buildRuntimeSparkline(history: CompletedTaskMeta[]): SparklinePoint[] {
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
}

function _buildRateSparkline(history: CompletedTaskMeta[]): SparklinePoint[] {
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
}

export interface TaskGroupStats {
  avgRuntime: number | null;
  runtimeSamples: number;
}

export function computeTaskGroupStats(history: CompletedTaskMeta[]): TaskGroupStats {
  const runtimes = history
    .filter((t) => t.status === "SUCCESS" && t.runtime != null)
    .map((t) => t.runtime!);
  const runtimeSamples = runtimes.length;
  const avgRuntime = runtimeSamples > 0
    ? runtimes.reduce((a, b) => a + b, 0) / runtimeSamples
    : null;
  return { avgRuntime, runtimeSamples };
}

function SparklineCard({
  title,
  value,
  suffix,
  extra,
  data,
  config,
  gradientId,
  valueFormatter,
}: {
  title: string;
  value: string;
  suffix?: string;
  extra?: string;
  data: SparklinePoint[];
  config: ChartConfig;
  gradientId: string;
  valueFormatter?: (v: number) => string;
}) {
  return (
    <Card className="py-3">
      <CardHeader className="flex flex-row items-center justify-between px-4 py-0">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 py-0 pt-1">
        <div className="text-2xl font-bold tracking-tight">
          {value}
          {suffix && (
            <span className="text-xs font-normal text-muted-foreground">{suffix}</span>
          )}
          {extra && (
            <span className="text-xs font-normal text-muted-foreground ml-1">{extra}</span>
          )}
        </div>
        {data.length >= 2 && (
          <ChartContainer config={config} className="mt-2 h-[40px] w-full">
            <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-value)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--color-value)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    labelKey="time"
                    {...(valueFormatter ? { valueFormatter: (v) => valueFormatter(Number(v)) } : {})}
                  />
                }
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--color-value)"
                fill={`url(#${gradientId})`}
                strokeWidth={1.5}
                dot={false}
              />
            </AreaChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}

function _formatRuntime(value: number): string {
  return value < 1 ? `${(value * 1000).toFixed(0)}ms` : `${value.toFixed(2)}s`;
}

export function TaskGroupKpis({ history }: { history: CompletedTaskMeta[] }) {
  const { successCount, runtimes, avgRuntime, p95Runtime, successRate } = useMemo(() => {
    let _successCount = 0;
    const _runtimes: number[] = [];
    let _runtimeSum = 0;

    for (const t of history) {
      if (t.status === "SUCCESS") {
        _successCount++;
        if (t.runtime != null) {
          _runtimes.push(t.runtime);
          _runtimeSum += t.runtime;
        }
      }
    }

    const _avgRuntime = _runtimes.length > 0 ? _runtimeSum / _runtimes.length : null;

    let _p95Runtime: number | null = null;
    if (_runtimes.length > 0) {
      _runtimes.sort((a, b) => a - b);
      _p95Runtime = _runtimes[Math.floor(_runtimes.length * 0.95)] || _runtimes[_runtimes.length - 1];
    }

    const _successRate = history.length > 0
      ? ((_successCount / history.length) * 100).toFixed(1)
      : "—";

    return {
      successCount: _successCount,
      runtimes: _runtimes,
      avgRuntime: _avgRuntime,
      p95Runtime: _p95Runtime,
      successRate: _successRate,
    };
  }, [history]);

  const throughputSparkline = useMemo(() => _buildThroughputSparkline(history), [history]);
  const runtimeSparkline = useMemo(() => _buildRuntimeSparkline(history), [history]);
  const rateSparkline = useMemo(() => _buildRateSparkline(history), [history]);

  return (
    <div className="grid gap-4 grid-cols-2 md:grid-cols-3">
      <SparklineCard
        title="Executions"
        value={String(history.length)}
        data={throughputSparkline}
        config={_throughputConfig}
        gradientId="spark-tg-throughput"
      />
      <SparklineCard
        title="Success Rate"
        value={successRate}
        suffix={successRate !== "—" ? "%" : undefined}
        data={rateSparkline}
        config={_rateConfig}
        gradientId="spark-tg-rate"
        valueFormatter={(v) => `${v}%`}
      />
      <SparklineCard
        title="Avg Runtime"
        value={avgRuntime != null ? _formatRuntime(avgRuntime) : "—"}
        extra={p95Runtime != null ? `p95 ${_formatRuntime(p95Runtime)}` : undefined}
        data={runtimeSparkline}
        config={_runtimeConfig}
        gradientId="spark-tg-runtime"
        valueFormatter={(v) => `${Number(v).toFixed(3)}s`}
      />
    </div>
  );
}
