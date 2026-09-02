import { clickableRow } from "@/lib/row-nav";
import { toast } from "sonner";
import { formatDurationSeconds } from "@/lib/workflow-utils";
import { useState } from "react";
import type { CompletedTaskMeta } from "@/lib/types";
import { statusVariant, normalizeArgs, normalizeKwargs } from "@/lib/task-utils";
import { apiPost } from "@/lib/api";
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
import { TaskDetailDialog } from "@/components/tasks/task-detail-dialog";
import { Clock, Loader2, RotateCw } from "lucide-react";

export function TaskGroupHistory({
  history,
  taskName,
}: {
  history: CompletedTaskMeta[];
  taskName: string;
}) {
  const [selected, setSelected] = useState<CompletedTaskMeta | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const handleRetry = async (task: CompletedTaskMeta) => {
    setRetryingId(task.taskId);
    try {
      const res = await apiPost<{ taskId?: string }>("/api/tasks/send", {
        taskName,
        // completed-task metadata does not record the queue
        queue: "celery",
        args: normalizeArgs(task.args),
        kwargs: normalizeKwargs(task.kwargs),
      });
      toast.success(`Task dispatched (${(res.taskId ?? "").slice(0, 8)}…)`);
    } catch {
      toast.error("Retry failed — the task was not dispatched");
    } finally {
      setRetryingId(null);
    }
  };

  return (
    <>
      <section className="space-y-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Clock className="h-4 w-4" />
          Past Executions
        </h3>

        {history.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No completed executions yet.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Worker</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Runtime</TableHead>
                <TableHead>Completed</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((task) => (
                <TableRow
                  key={task.taskId}
                  {...clickableRow(() => setSelected(task))}
                >
                  <TableCell className="font-mono text-xs">
                    {task.taskId.slice(0, 8)}...
                  </TableCell>
                  <TableCell>{task.worker || "—"}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(task.status)}>
                      {task.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {task.runtime != null ? (
                      formatDurationSeconds(task.runtime)
                    ) : task.status === "FAILURE" && task.exception ? (
                      <span className="text-destructive" title={task.exception}>
                        {task.exception}
                      </span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(task.completedAt * 1000).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      title="Retry with same payload"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRetry(task);
                      }}
                      disabled={retryingId === task.taskId}
                    >
                      {retryingId === task.taskId ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <RotateCw className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      {selected && (
        <TaskDetailDialog
          task={{
            taskId: selected.taskId,
            status: selected.status,
            result: selected.result ?? null,
            traceback: selected.traceback ?? null,
            dateDone: new Date(selected.completedAt * 1000).toISOString(),
            name: selected.name,
            worker: selected.worker,
            runtime: selected.runtime,
            args: selected.args,
            kwargs: selected.kwargs,
          }}
          open={!!selected}
          onOpenChange={(open) => !open && setSelected(null)}
        />
      )}
    </>
  );
}
