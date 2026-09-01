import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDurationSeconds } from "@/lib/workflow-utils";

interface ComparisonStep {
  stepLabel: string;
  status: string;
  durationSeconds: number | null;
  baselineP50Seconds: number | null;
  baselineRuns: number;
  deltaSeconds: number | null;
}

interface Comparison {
  runId: string;
  steps: ComparisonStep[];
  totalSeconds: number;
  baselineTotalSeconds: number;
}

function DeltaLabel({ delta, baseline }: { delta: number | null; baseline: number | null }) {
  if (delta === null || baseline === null || baseline <= 0) {
    return <span className="text-muted-foreground">—</span>;
  }
  const pct = (delta / baseline) * 100;
  if (Math.abs(pct) < 15) {
    return <span className="text-muted-foreground">≈ typical</span>;
  }
  const slower = delta > 0;
  return (
    <span className={slower ? "font-medium text-red-500" : "font-medium text-emerald-500"}>
      {slower ? "+" : "−"}
      {formatDurationSeconds(Math.abs(delta))} ({slower ? "+" : "−"}
      {Math.abs(pct).toFixed(0)}%)
    </span>
  );
}

export function RunComparison({ runId, finished }: { runId: string; finished: boolean }) {
  const [cmp, setCmp] = useState<Comparison | null>(null);

  useEffect(() => {
    if (!finished) return;
    const controller = new AbortController();
    apiGet<Comparison>(`/api/workflows/runs/${runId}/comparison`, controller.signal)
      .then(setCmp)
      .catch(() => {});
    return () => controller.abort();
  }, [runId, finished]);

  if (!cmp || !cmp.steps.some((s) => s.baselineRuns > 0)) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          vs. recent runs{" "}
          <span className="text-sm font-normal text-muted-foreground">
            (p50 of the last {Math.max(...cmp.steps.map((s) => s.baselineRuns))} finished)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-1.5 text-sm">
          {cmp.steps.map((s) => {
            const width =
              cmp.totalSeconds > 0 && s.durationSeconds
                ? Math.max(2, (s.durationSeconds / cmp.totalSeconds) * 100)
                : 0;
            return (
              <div key={s.stepLabel} className="grid grid-cols-[1fr_auto_auto] items-center gap-3">
                <div className="min-w-0">
                  <div className="truncate">{s.stepLabel}</div>
                  <div className="h-1.5 rounded bg-muted">
                    <div
                      className="h-1.5 rounded bg-sky-500/70"
                      style={{ width: `${width}%` }}
                    />
                  </div>
                </div>
                <div className="w-16 text-right tabular-nums">
                  {s.durationSeconds !== null
                    ? formatDurationSeconds(s.durationSeconds)
                    : "—"}
                </div>
                <div className="w-32 text-right">
                  <DeltaLabel delta={s.deltaSeconds} baseline={s.baselineP50Seconds} />
                </div>
              </div>
            );
          })}
          <div className="mt-2 border-t pt-2 text-xs text-muted-foreground">
            Total {formatDurationSeconds(cmp.totalSeconds)} vs typical{" "}
            {formatDurationSeconds(cmp.baselineTotalSeconds)}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
