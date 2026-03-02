import { useMemo } from "react";
import { useCelery } from "@/hooks/use-celery";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { BarChart, Bar, XAxis, YAxis } from "recharts";

const chartConfig = {
  total: { label: "Completed", color: "var(--chart-1)" },
} satisfies ChartConfig;

export function TopTasksChart() {
  const { completedTasks, activeTasks } = useCelery();

  const data = useMemo(() => {
    const taskCounts = new Map<string, { total: number; failed: number; active: number }>();

    for (const task of completedTasks.values()) {
      if (task.name === "unknown") continue;
      const name = task.name.split(".").pop() || task.name;
      const existing = taskCounts.get(name) || { total: 0, failed: 0, active: 0 };
      existing.total++;
      if (task.status === "FAILURE") existing.failed++;
      taskCounts.set(name, existing);
    }

    for (const task of activeTasks.values()) {
      if (task.name === "unknown") continue;
      const name = task.name.split(".").pop() || task.name;
      const existing = taskCounts.get(name) || { total: 0, failed: 0, active: 0 };
      existing.active++;
      taskCounts.set(name, existing);
    }

    return Array.from(taskCounts.entries())
      .map(([name, stats]) => ({ name, ...stats }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 8);
  }, [completedTasks, activeTasks]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Top Tasks</CardTitle>
        <p className="text-xs text-muted-foreground">
          Most executed task types
        </p>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-[250px] items-center justify-center">
            <p className="text-sm text-muted-foreground">No task data yet</p>
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
            >
              <XAxis type="number" tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis
                type="category"
                dataKey="name"
                tickLine={false}
                axisLine={false}
                width={140}
              />
              <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
              <Bar
                dataKey="total"
                fill="var(--color-total)"
                radius={[0, 4, 4, 0]}
                fillOpacity={0.9}
              />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}
