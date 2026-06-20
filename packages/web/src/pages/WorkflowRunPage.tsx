import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet, apiPost } from "@/lib/api";
import type { WorkflowRunDetail, Workflow } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { WorkflowDag } from "@/components/workflows/workflow-dag";
import { ArrowLeft, XCircle } from "lucide-react";
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
  const [cancelling, setCancelling] = useState(false);
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

  const handleCancelRun = async () => {
    if (!runId) return;
    setCancelling(true);
    try {
      await apiPost(`/api/workflows/runs/${runId}/cancel`);
      fetchData();
    } catch {
      // next poll will show current status
    } finally {
      setCancelling(false);
    }
  };

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
        {isRunning && (
          <Button
            variant="destructive"
            size="sm"
            disabled={cancelling}
            onClick={handleCancelRun}
          >
            <XCircle className="mr-1.5 h-4 w-4" />
            Cancel Run
          </Button>
        )}
      </div>

      {workflow && workflow.nodes.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-lg font-semibold">Pipeline</h3>
          <WorkflowDag
            nodes={workflow.nodes}
            nodeRuns={run.nodeRuns}
            scheduleType={workflow.scheduleType}
          />
        </div>
      )}

      {run.nodeRuns.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Node Details</h3>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Node</TableHead>
                  <TableHead>Task</TableHead>
                  <TableHead>Celery Task ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Error</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {run.nodeRuns.map((nr) => (
                  <TableRow key={nr.id}>
                    <TableCell className="font-medium">{nr.label}</TableCell>
                    <TableCell className="text-sm">
                      <Link
                        to={`/tasks/${encodeURIComponent(nr.taskName)}`}
                        className="hover:underline"
                      >
                        {nr.taskName}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {nr.celeryTaskId ? nr.celeryTaskId.slice(0, 8) + "..." : "—"}
                    </TableCell>
                    <TableCell>
                      <WorkflowStatusBadge status={nr.status} />
                    </TableCell>
                    <TableCell className="text-sm">
                      {nr.startedAt ? formatWorkflowDate(nr.startedAt) : "—"}
                    </TableCell>
                    <TableCell className="text-sm">
                      {nr.startedAt
                        ? formatWorkflowDuration(nr.startedAt, nr.finishedAt)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-sm text-destructive">
                      {nr.error || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </div>
  );
}
