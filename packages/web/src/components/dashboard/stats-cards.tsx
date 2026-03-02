import { useMemo, useEffect, useState } from "react";
import { useCelery } from "@/hooks/use-celery";
import { apiGet } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Server, Inbox } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AreaChart, Area } from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";

const sparkConfig = {
  value: { label: "Tasks", color: "var(--chart-1)" },
} satisfies ChartConfig;

const sparkRateConfig = {
  value: { label: "Rate", color: "var(--chart-2)" },
} satisfies ChartConfig;

function Sparkline({
  data,
  id,
  config,
  suffix,
}: {
  data: { time: string; value: number }[];
  id: string;
  config: ChartConfig;
  suffix?: string;
}) {
  if (data.length < 2) return null;

  return (
    <ChartContainer config={config} className="mt-2 h-[40px] w-full">
      <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-value)" stopOpacity={0.3} />
            <stop offset="95%" stopColor="var(--color-value)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              labelKey="time"
              valueFormatter={(v) => `${v}${suffix ?? ""}`}
            />
          }
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke="var(--color-value)"
          fill={`url(#spark-${id})`}
          strokeWidth={1.5}
          dot={false}
        />
      </AreaChart>
    </ChartContainer>
  );
}

function SimpleStatCard({
  title,
  value,
  suffix,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  suffix?: string;
  icon: LucideIcon;
}) {
  return (
    <Card className="py-3">
      <CardHeader className="flex flex-row items-center justify-between px-4 py-0">
        <CardTitle className="text-xs font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      </CardHeader>
      <CardContent className="px-4 py-0 pt-1">
        <div className="text-2xl font-bold tracking-tight">
          {value}
          {suffix && (
            <span className="text-xs font-normal text-muted-foreground">
              {suffix}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function StatsCards() {
  const { workers, activeTasks, completedTasks } = useCelery();
  const [queueDepth, setQueueDepth] = useState(0);

  useEffect(() => {
    const fetchDepth = async () => {
      try {
        const data = await apiGet<{ depths?: Record<string, number> }>("/api/queues");
        const depths: Record<string, number> = data.depths ?? {};
        const total = Object.values(depths).reduce(
          (sum: number, v: number) => sum + (typeof v === "number" ? v : 0),
          0
        );
        setQueueDepth(total);
      } catch {
        // ignore
      }
    };

    fetchDepth();
    const depthInterval = setInterval(fetchDepth, 5000);

    return () => {
      clearInterval(depthInterval);
    };
  }, []);

  const throughputData = useMemo(() => {
    const tasks = Array.from(completedTasks.values());
    if (tasks.length === 0) return [];

    const buckets = new Map<string, number>();
    for (const task of tasks) {
      const date = new Date(task.completedAt * 1000);
      const key = `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }

    return Array.from(buckets.entries())
      .map(([time, value]) => ({ time, value }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [completedTasks]);

  const successRateData = useMemo(() => {
    const tasks = Array.from(completedTasks.values());
    if (tasks.length === 0) return [];

    const sorted = [...tasks].sort((a, b) => a.completedAt - b.completedAt);
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
      .map(([time, { success, total }]) => ({
        time,
        value: total > 0 ? Math.round((success / total) * 100) : 0,
      }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [completedTasks]);

  const computed = useMemo(() => {
    const onlineWorkers = Array.from(workers.values()).filter(
      (w) => w.status === "online"
    );
    const completed = Array.from(completedTasks.values());
    const total = completed.length;
    const successes = completed.filter((t) => t.status === "SUCCESS").length;
    const successRate =
      total > 0 ? ((successes / total) * 100).toFixed(1) : "—";

    return {
      onlineCount: onlineWorkers.length,
      totalWorkers: workers.size,
      successRate,
    };
  }, [workers, completedTasks]);

  return (
    <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
      <SimpleStatCard
        title="Workers"
        value={computed.onlineCount}
        suffix={`/ ${computed.totalWorkers}`}
        icon={Server}
      />

      {/* Active + Task Throughput sparkline */}
      <Card className="py-3">
        <CardHeader className="flex flex-row items-center justify-between px-4 py-0">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Active
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-0 pt-1">
          <div className="text-2xl font-bold tracking-tight">
            {activeTasks.size}
          </div>
          <Sparkline data={throughputData} id="throughput" config={sparkConfig} />
        </CardContent>
      </Card>

      <SimpleStatCard title="Queued" value={queueDepth} icon={Inbox} />

      {/* Success Rate + sparkline */}
      <Card className="py-3">
        <CardHeader className="flex flex-row items-center justify-between px-4 py-0">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Success Rate
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 py-0 pt-1">
          <div className="text-2xl font-bold tracking-tight">
            {computed.successRate}
            {computed.successRate !== "—" && (
              <span className="text-xs font-normal text-muted-foreground">
                %
              </span>
            )}
          </div>
          <Sparkline data={successRateData} id="success-rate" config={sparkRateConfig} suffix="%" />
        </CardContent>
      </Card>

    </div>
  );
}
