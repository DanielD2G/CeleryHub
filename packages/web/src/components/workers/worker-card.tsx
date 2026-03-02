import { useMemo } from "react";
import type { WorkerState } from "@/lib/types";
import { useCelery } from "@/hooks/use-celery";
import { timeAgo } from "@/lib/task-utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

export function WorkerCard({ worker }: { worker: WorkerState }) {
  const { completedTasks } = useCelery();

  const sparklineData = useMemo(() => {
    const buckets = new Map<string, number>();

    for (const task of completedTasks.values()) {
      if (task.worker !== worker.hostname) continue;
      const date = new Date(task.completedAt * 1000);
      const key = `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
      buckets.set(key, (buckets.get(key) || 0) + 1);
    }

    return Array.from(buckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, value]) => ({ time, value }));
  }, [completedTasks, worker.hostname]);

  const gradientId = `spark-worker-${worker.hostname.replace(/[^a-zA-Z0-9]/g, "-")}`;

  return (
    <Card className="py-3">
      <CardHeader className="flex flex-row items-center justify-between px-4 pb-2">
        <CardTitle className="text-sm font-medium truncate">
          {worker.hostname}
        </CardTitle>
        <Badge
          variant={worker.status === "online" ? "default" : "destructive"}
        >
          {worker.status}
        </Badge>
      </CardHeader>
      <CardContent className="px-4 space-y-3">
        <div className="text-2xl font-bold tracking-tight">
          {worker.processed}
          <span className="text-xs font-normal text-muted-foreground ml-1">
            processed
          </span>
        </div>

        {sparklineData.length >= 2 && (
          <ChartContainer config={sparkConfig} className="h-[40px] w-full">
            <AreaChart data={sparklineData} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-value)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--color-value)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <ChartTooltip
                cursor={false}
                content={<ChartTooltipContent labelKey="time" />}
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

        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <p className="text-muted-foreground">Active</p>
            <p className="font-medium">{worker.active}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Last heartbeat</p>
            <p className="font-medium">{timeAgo(worker.lastHeartbeat)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">PID</p>
            <p className="font-medium">{worker.pid}</p>
          </div>
          {(worker.swVer || worker.swSys) && (
            <div>
              <p className="text-muted-foreground">Version</p>
              <p className="font-medium text-xs">
                {worker.swVer} ({worker.swSys})
              </p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
