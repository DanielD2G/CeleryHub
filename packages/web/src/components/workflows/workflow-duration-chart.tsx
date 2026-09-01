import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Tooltip,
  XAxis,
  YAxis,
  ResponsiveContainer,
} from "recharts";
import { apiGet } from "@/lib/api";
import { formatDurationSeconds } from "@/lib/workflow-utils";

interface StepDuration {
  stepLabel: string;
  status: string;
  durationSeconds: number | null;
}

interface RunDuration {
  runId: string;
  status: string;
  trigger: string;
  startedAt: string;
  finishedAt: string | null;
  durationSeconds: number | null;
  steps: StepDuration[];
}

interface RunDurationsResponse {
  workflowId: string;
  items: RunDuration[];
}

const STATUS_COLORS: Record<string, string> = {
  succeeded: "var(--color-emerald-500, #10b981)",
  failed: "var(--color-red-500, #ef4444)",
  cancelled: "var(--color-amber-500, #f59e0b)",
  running: "var(--color-sky-500, #0ea5e9)",
};

export function WorkflowDurationChart({ workflowId }: { workflowId: string }) {
  const [items, setItems] = useState<RunDuration[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiGet<RunDurationsResponse>(
      `/api/workflows/${workflowId}/run-durations?limit=50`,
      controller.signal
    )
      .then((res) => setItems(res.items))
      .catch(() => setItems([]));
    return () => controller.abort();
  }, [workflowId]);

  const finished = (items ?? []).filter((r) => r.durationSeconds !== null);
  if (items === null || finished.length < 2) {
    // A trend needs at least two finished runs; below that the table says it all.
    return null;
  }

  const data = finished.map((r) => ({
    ...r,
    label: new Date(r.startedAt).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <div className="rounded-md border p-4">
      <h3 className="mb-1 text-sm font-medium">Run duration trend</h3>
      <p className="mb-3 text-xs text-muted-foreground">
        Last {data.length} finished runs, oldest first
      </p>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} />
          <YAxis
            width={52}
            tick={{ fontSize: 11 }}
            tickLine={false}
            tickFormatter={(v: number) => formatDurationSeconds(v)}
          />
          <Tooltip
            cursor={{ fill: "var(--color-muted, #f4f4f5)", opacity: 0.4 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const run = payload[0].payload as RunDuration & { label: string };
              return (
                <div className="rounded-md border bg-background p-2 text-xs shadow-md">
                  <div className="mb-1 font-medium">
                    {new Date(run.startedAt).toLocaleString()} · {run.status}
                  </div>
                  <div>
                    Total: {formatDurationSeconds(run.durationSeconds ?? 0)}
                  </div>
                  {run.steps
                    .filter((s) => s.durationSeconds !== null)
                    .map((s) => (
                      <div key={s.stepLabel} className="text-muted-foreground">
                        {s.stepLabel}:{" "}
                        {formatDurationSeconds(s.durationSeconds ?? 0)}
                      </div>
                    ))}
                </div>
              );
            }}
          />
          <Bar dataKey="durationSeconds" radius={[3, 3, 0, 0]}>
            {data.map((r) => (
              <Cell
                key={r.runId}
                fill={STATUS_COLORS[r.status] ?? STATUS_COLORS.running}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
