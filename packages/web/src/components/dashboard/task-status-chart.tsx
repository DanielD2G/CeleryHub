import { useMemo } from "react";
import { useCelery } from "@/hooks/use-celery";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { PieChart, Pie, Cell } from "recharts";

const chartConfig = {
  count: { label: "Tasks" },
  SUCCESS: { label: "Success", color: "var(--chart-2)" },
  FAILURE: { label: "Failure", color: "var(--chart-5)" },
  REVOKED: { label: "Revoked", color: "var(--chart-4)" },
  RETRIED: { label: "Retried", color: "var(--chart-3)" },
} satisfies ChartConfig;

const STATUS_FILLS: Record<string, string> = {
  SUCCESS: "var(--color-SUCCESS)",
  FAILURE: "var(--color-FAILURE)",
  REVOKED: "var(--color-REVOKED)",
  RETRIED: "var(--color-RETRIED)",
};

export function TaskStatusChart() {
  const { completedTasks } = useCelery();

  const data = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const task of completedTasks.values()) {
      counts[task.status] = (counts[task.status] || 0) + 1;
    }
    return Object.entries(counts)
      .map(([status, count]) => ({ status, count }))
      .sort((a, b) => b.count - a.count);
  }, [completedTasks]);

  const total = data.reduce((sum, d) => sum + d.count, 0);
  const successRate = total > 0
    ? ((data.find((d) => d.status === "SUCCESS")?.count || 0) / total * 100).toFixed(1)
    : "—";

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Task Outcomes</CardTitle>
        <p className="text-xs text-muted-foreground">
          Success rate: {successRate}%
        </p>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-[250px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              No completed tasks yet
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4">
            <ChartContainer config={chartConfig} className="aspect-square h-[200px]">
              <PieChart>
                <Pie
                  data={data}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={3}
                  dataKey="count"
                  nameKey="status"
                  strokeWidth={0}
                >
                  {data.map((entry) => (
                    <Cell
                      key={entry.status}
                      fill={STATUS_FILLS[entry.status] || "var(--muted)"}
                    />
                  ))}
                </Pie>
                <ChartTooltip content={<ChartTooltipContent nameKey="status" />} />
              </PieChart>
            </ChartContainer>
            <div className="flex flex-wrap justify-center gap-x-4 gap-y-1">
              {data.map((entry) => (
                <div key={entry.status} className="flex items-center gap-2 text-xs">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: STATUS_FILLS[entry.status] || "var(--muted)" }}
                  />
                  <span className="text-muted-foreground">{entry.status}</span>
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
