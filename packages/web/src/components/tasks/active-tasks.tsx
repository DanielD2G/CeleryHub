import { Link } from "react-router-dom";
import { useCeleryTasks } from "@/hooks/use-celery";
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
import { useCallback, useEffect, useState } from "react";
import { Loader2, Square } from "lucide-react";

function Duration({ since }: { since: number }) {
  const [elapsed, setElapsed] = useState("0.0s");

  useEffect(() => {
    const update = () => {
      const secs = Date.now() / 1000 - since;
      if (secs < 60) {
        setElapsed(`${secs.toFixed(1)}s`);
      } else {
        setElapsed(`${Math.floor(secs / 60)}m ${Math.floor(secs % 60)}s`);
      }
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [since]);

  return <span className="font-mono text-xs">{elapsed}</span>;
}

export function ActiveTasks() {
  const activeTasks = useCeleryTasks();
  const tasks = Array.from(activeTasks.values());
  const [revokingIds, setRevokingIds] = useState<Set<string>>(new Set());

  const handleRevoke = useCallback(async (taskId: string) => {
    setRevokingIds((prev) => new Set(prev).add(taskId));
    try {
      await fetch(`/api/tasks/${taskId}/revoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ terminate: true, signal: "SIGTERM" }),
      });
    } finally {
      setTimeout(() => {
        setRevokingIds((prev) => {
          const next = new Set(prev);
          next.delete(taskId);
          return next;
        });
      }, 2000);
    }
  }, []);

  if (tasks.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No active tasks
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Task Name</TableHead>
          <TableHead>ID</TableHead>
          <TableHead>Worker</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {tasks.map((task) => {
          const revoking = revokingIds.has(task.taskId);
          return (
            <TableRow key={task.taskId}>
              <TableCell className="font-medium">
                <Link to={`/tasks/${encodeURIComponent(task.name)}`} className="hover:underline">
                  {task.name}
                </Link>
              </TableCell>
              <TableCell className="font-mono text-xs">
                {task.taskId.slice(0, 8)}...
              </TableCell>
              <TableCell>{task.worker || "—"}</TableCell>
              <TableCell>
                <Badge variant="outline">{task.status}</Badge>
              </TableCell>
              <TableCell>
                <Duration since={task.startedAt} />
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
  );
}
