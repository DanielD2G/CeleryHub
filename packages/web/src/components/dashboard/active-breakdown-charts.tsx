import { useMemo } from "react";
import { useCelery } from "@/hooks/use-celery";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { BarChart, Bar, XAxis, YAxis, Cell, PieChart, Pie } from "recharts";

const barChartConfig = {
  count: { label: "Tasks", color: "var(--chart-1)" },
} satisfies ChartConfig;

const pieChartConfig = {
  count: { label: "Tasks" },
} satisfies ChartConfig;

const PIE_FILLS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "color-mix(in oklch, var(--chart-1) 60%, transparent)",
  "color-mix(in oklch, var(--chart-2) 60%, transparent)",
];

export function ActiveByWorkerChart() {
  const { activeTasks } = useCelery();

  const data = useMemo(() => {
    const workerMap = new Map<string, number>();
    for (const task of activeTasks.values()) {
      const name = task.worker.split("@").pop() || task.worker || "pending";
      workerMap.set(name, (workerMap.get(name) || 0) + 1);
    }
    return Array.from(workerMap.entries())
      .map(([worker, count]) => ({ worker, count }))
      .sort((a, b) => b.count - a.count);
  }, [activeTasks]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Active Tasks by Worker
        </CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-[200px] items-center justify-center">
            <p className="text-sm text-muted-foreground">No active tasks</p>
          </div>
        ) : (
          <ChartContainer config={barChartConfig} className="aspect-auto h-[200px] w-full">
            <BarChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <XAxis dataKey="worker" tickLine={false} axisLine={false} tickMargin={8} />
              <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
              <Bar dataKey="count" fill="var(--color-count)" radius={[4, 4, 0, 0]} fillOpacity={0.9} />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}

export function ActiveByTypeChart() {
  const { activeTasks } = useCelery();

  const data = useMemo(() => {
    const typeMap = new Map<string, number>();
    for (const task of activeTasks.values()) {
      if (task.name === "unknown") continue;
      const name = task.name.split(".").pop() || task.name;
      typeMap.set(name, (typeMap.get(name) || 0) + 1);
    }
    return Array.from(typeMap.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [activeTasks]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Active Tasks by Type
        </CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-[200px] items-center justify-center">
            <p className="text-sm text-muted-foreground">No active tasks</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4">
            <ChartContainer config={pieChartConfig} className="aspect-square h-[200px]">
              <PieChart>
                <Pie
                  data={data}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={70}
                  paddingAngle={3}
                  dataKey="count"
                  nameKey="name"
                  strokeWidth={0}
                >
                  {data.map((_, idx) => (
                    <Cell key={idx} fill={PIE_FILLS[idx % PIE_FILLS.length]} />
                  ))}
                </Pie>
                <ChartTooltip content={<ChartTooltipContent nameKey="name" />} />
              </PieChart>
            </ChartContainer>
            <div className="flex flex-wrap justify-center gap-x-4 gap-y-1">
              {data.map((entry, idx) => (
                <div key={entry.name} className="flex items-center gap-2 text-xs">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: PIE_FILLS[idx % PIE_FILLS.length] }}
                  />
                  <span className="max-w-[80px] truncate text-muted-foreground">
                    {entry.name}
                  </span>
                  <span className="font-mono font-medium">{entry.count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
