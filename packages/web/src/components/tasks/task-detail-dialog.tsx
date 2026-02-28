import { useState } from "react";
import { Link } from "react-router-dom";
import type { TaskResult } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { RotateCw, Loader2, CheckCircle } from "lucide-react";

function formatJson(value: string | undefined): string {
  if (!value) return "—";
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function normalizeArgs(raw: string | undefined): string {
  if (!raw || raw === "()" || raw === "null") return "[]";
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(Array.isArray(parsed) ? parsed : []);
  } catch {
    return "[]";
  }
}

function normalizeKwargs(raw: string | undefined): string {
  if (!raw || raw === "null") return "{}";
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {});
  } catch {
    return "{}";
  }
}

function hasPayload(args?: string, kwargs?: string): boolean {
  const hasArgs = !!args && args !== "[]" && args !== "()" && args !== "null";
  const hasKwargs = !!kwargs && kwargs !== "{}" && kwargs !== "null";
  return hasArgs || hasKwargs;
}

export function TaskDetailDialog({
  task,
  open,
  onOpenChange,
}: {
  task: TaskResult | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [retrying, setRetrying] = useState(false);
  const [retried, setRetried] = useState(false);

  if (!task) return null;

  const showPayload = hasPayload(task.args, task.kwargs);

  const handleResend = async () => {
    if (!task.name) return;
    setRetrying(true);
    setRetried(false);

    try {
      await fetch("/api/tasks/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          taskName: task.name,
          queue: "celery",
          args: normalizeArgs(task.args),
          kwargs: normalizeKwargs(task.kwargs),
        }),
      });
      setRetried(true);
      setTimeout(() => setRetried(false), 3000);
    } finally {
      setRetrying(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) {
          setRetried(false);
          setRetrying(false);
        }
        onOpenChange(v);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {task.name ? (
              <Link to={`/tasks/${encodeURIComponent(task.name)}`} className="hover:underline">
                {task.name}
              </Link>
            ) : "Task Detail"}
            <Badge
              variant={
                task.status === "SUCCESS"
                  ? "default"
                  : task.status === "FAILURE"
                    ? "destructive"
                    : "secondary"
              }
            >
              {task.status}
            </Badge>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Task ID</p>
              <p className="font-mono text-xs">{task.taskId}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Worker</p>
              <p>{task.worker || "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Runtime</p>
              <p>
                {task.runtime != null ? `${task.runtime.toFixed(3)}s` : "—"}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Completed</p>
              <p>
                {task.dateDone
                  ? new Date(task.dateDone).toLocaleString()
                  : "—"}
              </p>
            </div>
          </div>

          {showPayload && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="mb-1 text-sm text-muted-foreground">Args</p>
                <ScrollArea className="max-h-32 rounded-md border bg-muted p-3">
                  <pre className="text-xs whitespace-pre-wrap">
                    {formatJson(task.args)}
                  </pre>
                </ScrollArea>
              </div>
              <div>
                <p className="mb-1 text-sm text-muted-foreground">Kwargs</p>
                <ScrollArea className="max-h-32 rounded-md border bg-muted p-3">
                  <pre className="text-xs whitespace-pre-wrap">
                    {formatJson(task.kwargs)}
                  </pre>
                </ScrollArea>
              </div>
            </div>
          )}

          <div>
            <p className="mb-1 text-sm text-muted-foreground">Result</p>
            <ScrollArea className="max-h-48 rounded-md border bg-muted p-3">
              <pre className="text-xs whitespace-pre-wrap">
                {task.result != null
                  ? JSON.stringify(task.result, null, 2)
                  : "null"}
              </pre>
            </ScrollArea>
          </div>

          {task.traceback && (
            <div>
              <p className="mb-1 text-sm text-destructive">Traceback</p>
              <ScrollArea className="max-h-64 rounded-md border border-destructive/20 bg-destructive/5 p-3">
                <pre className="text-xs whitespace-pre-wrap">
                  {task.traceback}
                </pre>
              </ScrollArea>
            </div>
          )}

          {task.name && (
            <Button
              className="w-full"
              variant="outline"
              onClick={handleResend}
              disabled={retrying}
            >
              {retrying ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : retried ? (
                <CheckCircle className="mr-2 h-4 w-4 text-emerald-500" />
              ) : (
                <RotateCw className="mr-2 h-4 w-4" />
              )}
              {retried ? "Sent" : "Resend with same payload"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
