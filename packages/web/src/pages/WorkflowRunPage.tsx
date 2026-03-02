import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet } from "@/lib/api";
import type { WorkflowRunDetail, Workflow } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";
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
import { WorkflowDag } from "@/components/workflows/workflow-dag";
import { ArrowLeft } from "lucide-react";
import {
  formatWorkflowDate,
  WorkflowStatusBadge,
  formatWorkflowDuration,
} from "@/lib/workflow-utils";

export default function WorkflowRunPage() {
  const { id, runId } = useParams<{ id: string; runId: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<WorkflowRunDetail | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(true);
  useDocumentTitle(run ? `Run ${run.id.slice(0, 8)}` : "Run Detail");

  const fetchData = useCallback(() => {
    if (!id || !runId) return;

    Promise.all([
      apiGet<WorkflowRunDetail>(`/api/workflows/runs/${runId}`).catch(() => null),
      apiGet<Workflow>(`/api/workflows/${id}`).catch(() => null),
    ])
      .then(([runData, wfData]) => {
        if (!runData) {
          navigate(`/workflows/${id}`, { replace: true });
          return;
        }
        setRun(runData);
        setWorkflow(wfData);
      })
      .catch(() => {
        navigate(`/workflows/${id}`, { replace: true });
      })
      .finally(() => setLoading(false));
  }, [id, runId, navigate]);

  const isRunning = run?.status === "running";

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, isRunning ? 3000 : 5000);
    return () => clearInterval(interval);
  }, [fetchData, isRunning]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!run) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to={`/workflows/${id}`}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <h2 className="text-2xl font-bold tracking-tight">
            Run {run.id.slice(0, 8)}...
          </h2>
          <div className="mt-1 flex items-center gap-2">
            <WorkflowStatusBadge status={run.status} />
            <Badge variant="secondary" className="text-xs">
              {run.trigger}
            </Badge>
            <span className="text-sm text-muted-foreground">
              {formatWorkflowDate(run.startedAt)}
            </span>
            {run.finishedAt && (
              <span className="text-sm text-muted-foreground">
                ({formatWorkflowDuration(run.startedAt, run.finishedAt)})
              </span>
            )}
          </div>
        </div>
      </div>

      {workflow && workflow.steps.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-lg font-semibold">Pipeline</h3>
          <WorkflowDag
            steps={workflow.steps}
            stepRuns={run.stepRuns}
            scheduleType={workflow.scheduleType}
          />
        </div>
      )}

      {run.stepRuns.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Step Details</h3>
          <div className="flex gap-4 overflow-x-auto pb-2">
            {run.stepRuns.map((sr) => (
              <Card key={sr.id} className="min-w-[350px] max-w-[450px] shrink-0">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{sr.stepLabel}</CardTitle>
                    <WorkflowStatusBadge status={sr.status} />
                  </div>
                  {sr.startedAt && (
                    <p className="text-xs text-muted-foreground">
                      {formatWorkflowDate(sr.startedAt)}
                      {sr.finishedAt &&
                        ` — ${formatWorkflowDuration(sr.startedAt, sr.finishedAt)}`}
                    </p>
                  )}
                </CardHeader>
                {sr.taskRuns.length > 0 && (
                  <CardContent>
                    <div className="rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Task</TableHead>
                            <TableHead>Task ID</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Error</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {sr.taskRuns.map((tr) => (
                            <TableRow key={tr.id}>
                              <TableCell className="text-sm font-medium">
                                <Link
                                  to={`/tasks/${encodeURIComponent(tr.taskName)}`}
                                  className="hover:underline"
                                >
                                  {tr.taskName}
                                </Link>
                              </TableCell>
                              <TableCell className="font-mono text-xs">
                                {tr.taskId ? tr.taskId.slice(0, 8) + "..." : "—"}
                              </TableCell>
                              <TableCell>
                                <WorkflowStatusBadge status={tr.status} />
                              </TableCell>
                              <TableCell className="text-sm text-destructive">
                                {tr.error || "—"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
