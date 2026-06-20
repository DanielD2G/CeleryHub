import { Link } from "react-router-dom";
import { NodeRun } from "@/lib/types";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  WorkflowStatusBadge,
  formatWorkflowDuration,
  formatWorkflowDate,
} from "@/lib/workflow-utils";

interface NodeRunDrawerProps {
  run: NodeRun | null;
  onClose: () => void;
}

export function NodeRunDrawer({ run, onClose }: NodeRunDrawerProps) {
  return (
    <Sheet open={run !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent side="right" className="w-96 sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Node Run Detail</SheetTitle>
          <SheetDescription>
            {run ? run.label || run.taskName || run.nodeId : ""}
          </SheetDescription>
        </SheetHeader>

        {run && (
          <div className="space-y-4 p-4">
            {/* Status */}
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Status</p>
              <WorkflowStatusBadge status={run.status} />
            </div>

            {/* Task */}
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Task</p>
              <p className="font-mono text-sm">{run.taskName || "—"}</p>
            </div>

            {/* Celery Task ID */}
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Celery Task ID</p>
              {run.celeryTaskId ? (
                <Link
                  to={`/tasks/${run.celeryTaskId}`}
                  className="font-mono text-sm text-primary underline-offset-4 hover:underline break-all"
                >
                  {run.celeryTaskId}
                </Link>
              ) : (
                <p className="text-sm">—</p>
              )}
            </div>

            {/* Started At */}
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Started At</p>
              <p className="text-sm">{formatWorkflowDate(run.startedAt)}</p>
            </div>

            {/* Finished At */}
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Finished At</p>
              <p className="text-sm">{formatWorkflowDate(run.finishedAt)}</p>
            </div>

            {/* Duration */}
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Duration</p>
              <p className="text-sm">
                {run.startedAt
                  ? formatWorkflowDuration(run.startedAt, run.finishedAt)
                  : "—"}
              </p>
            </div>

            {/* Error */}
            {run.error && (
              <div className="space-y-1">
                <p className="text-sm font-medium text-muted-foreground">Error</p>
                <pre className="rounded-md bg-destructive/10 p-2 text-xs text-destructive whitespace-pre-wrap break-all">
                  {run.error}
                </pre>
              </div>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
