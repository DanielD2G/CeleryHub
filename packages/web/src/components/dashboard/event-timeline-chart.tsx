import { useMemo } from "react";
import { useCeleryEvents } from "@/hooks/use-celery";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from "recharts";

const chartConfig = {
  task: { label: "Task Events", color: "var(--chart-1)" },
  worker: { label: "Worker Events", color: "var(--chart-3)" },
} satisfies ChartConfig;

export function EventTimelineChart() {
  const events = useCeleryEvents();

  const data = useMemo(() => {
    if (events.length === 0) return [];

    const buckets = new Map<string, { task: number; worker: number }>();

    for (const event of events) {
      const date = new Date(event.timestamp * 1000);
      const seconds = Math.floor(date.getSeconds() / 30) * 30;
      const key = `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;

      if (!buckets.has(key)) {
        buckets.set(key, { task: 0, worker: 0 });
      }
      const bucket = buckets.get(key)!;
      if (event.type.startsWith("task-")) {
        bucket.task++;
      } else {
        bucket.worker++;
      }
    }

    return Array.from(buckets.entries())
      .map(([time, counts]) => ({ time, ...counts }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [events]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Event Activity</CardTitle>
        <p className="text-xs text-muted-foreground">
          Event volume by type (30s windows)
        </p>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-[250px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              Waiting for events...
            </p>
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
            <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="time" tickLine={false} axisLine={false} tickMargin={8} />
              <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="dot" />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Line
                type="monotone"
                dataKey="task"
                stroke="var(--color-task)"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="worker"
                stroke="var(--color-worker)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
