import { useState } from "react";
import type { ActiveTask } from "@/lib/types";
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Play, Loader2, Square } from "lucide-react";

function _formatDuration(secs: number): string {
  if (secs < 60) return `${secs.toFixed(1)}s`;
  return `${Math.floor(secs / 60)}m ${Math.floor(secs % 60)}s`;
}

function Duration({
  since,
  avgRuntime,
  tick,
}: {
  since: number;
  avgRuntime: number | null;
  tick: number;
}) {
  void tick; // triggers re-render
  const secs = Date.now() / 1000 - since;
  const elapsed = _formatDuration(secs);
  let remaining: string | null = null;
  let progress: number | null = null;

  if (avgRuntime != null && avgRuntime > 0) {
    const left = avgRuntime - secs;
    progress = Math.min((secs / avgRuntime) * 100, 100);
    remaining = left > 0 ? `~${_formatDuration(left)} left` : "overtime";
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs">{elapsed}</span>
        {remaining && (
          <span
            className={`text-xs ${remaining === "overtime" ? "text-amber-500" : "text-muted-foreground"}`}
          >
            {remaining}
          </span>
        )}
      </div>
      {progress != null && (
        <div className="h-1.5 w-24 rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${progress >= 100 ? "bg-amber-500" : "bg-emerald-500"}`}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

export function TaskGroupActive({
  tasks,
  avgRuntime,
  runtimeSamples,
  tick,
}: {
  tasks: ActiveTask[];
  avgRuntime: number | null;
  runtimeSamples: number;
  tick: number;
}) {
  const [revokingIds, setRevokingIds] = useState<Set<string>>(new Set());

  const handleRevoke = async (taskId: string) => {
    setRevokingIds((prev) => new Set(prev).add(taskId));
    try {
      await apiPost(`/api/tasks/${taskId}/revoke`, { terminate: true, signal: "SIGTERM" });
    } catch {
      // ignore
    } finally {
      setTimeout(() => {
        setRevokingIds((prev) => {
          const next = new Set(prev);
          next.delete(taskId);
          return next;
        });
      }, 2000);
    }
  };

  if (tasks.length === 0) return null;

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold flex items-center gap-2">
        <Play className="h-4 w-4 text-emerald-500" />
        Running now
        {avgRuntime != null && (
          <span className="font-normal text-xs text-muted-foreground">
            {runtimeSamples === 1 ? "est." : "avg"} {_formatDuration(avgRuntime)}
          </span>
        )}
      </h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID</TableHead>
            <TableHead>Worker</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Progress</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {tasks.map((task) => {
            const revoking = revokingIds.has(task.taskId);
            return (
              <TableRow key={task.taskId}>
                <TableCell className="font-mono text-xs">
                  {task.taskId.slice(0, 8)}...
                </TableCell>
                <TableCell>{task.worker || "—"}</TableCell>
                <TableCell>
                  <Badge variant="outline">{task.status}</Badge>
                </TableCell>
                <TableCell>
                  <Duration since={task.startedAt} avgRuntime={avgRuntime} tick={tick} />
                </TableCell>
                <TableCell>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        disabled={revoking}
                        onClick={() => handleRevoke(task.taskId)}
                      >
                        {revoking ? (
                          <Loader2 className="animate-spin" />
                        ) : (
                          <Square />
                        )}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Stop task</TooltipContent>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </section>
  );
}
