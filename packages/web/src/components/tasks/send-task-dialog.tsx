import { toast } from "sonner";
import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  QueueSelector,
  ArgsBuilder,
  KwargsBuilder,
  serializeArgs,
  serializeKwargs,
} from "@/components/task-inputs";
import {
  Send,
  Loader2,
  CheckCircle,
  XCircle,
} from "lucide-react";

async function _sendTask(body: {
  taskName: string;
  queue: string;
  args: string;
  kwargs: string;
}): Promise<{ taskId?: string; error?: string }> {
  return apiPost("/api/tasks/send", body);
}

async function _pollTaskStatus(
  taskId: string
): Promise<{ status: string; result: unknown } | null> {
  try {
    return await apiGet(`/api/tasks/${taskId}/status`);
  } catch {
    return null;
  }
}

export function SendTaskDialog({
  taskName,
  queues,
  open,
  onOpenChange,
}: {
  taskName: string;
  queues: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [queue, setQueue] = useState("celery");
  const [argItems, setArgItems] = useState<string[]>([]);
  const [kwargPairs, setKwargPairs] = useState<[string, string][]>([]);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<{
    taskId?: string;
    error?: string;
  } | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  const _resetState = () => {
    setSendResult(null);
    setTaskStatus(null);
    setArgItems([]);
    setKwargPairs([]);
    setQueue("celery");
  };

  const handleOpen = (v: boolean) => {
    if (v) _resetState();
    onOpenChange(v);
  };

  const handleSend = async () => {
    setSending(true);
    setSendResult(null);
    setTaskStatus(null);

    try {
      const res = await _sendTask({
        taskName,
        queue,
        args: serializeArgs(argItems),
        kwargs: serializeKwargs(kwargPairs),
      });
      setSendResult(res);

      if (res.taskId) {
        let attempts = 0;
        const poll = async () => {
          if (attempts >= 30) {
            setTaskStatus("TIMEOUT");
            return;
          }
          attempts++;
          const status = await _pollTaskStatus(res.taskId!);
          if (status && status.status !== "PENDING") {
            setTaskStatus(status.status);
          } else {
            setTaskStatus("PENDING");
            pollTimeoutRef.current = setTimeout(poll, 2000);
          }
        };
        pollTimeoutRef.current = setTimeout(poll, 1000);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to send task";
      setSendResult({ error: msg });
      toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="h-4 w-4" />
            Send {taskName}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {sendResult && (
            <Card>
              <CardContent className="pt-4">
                {sendResult.error ? (
                  <div className="flex items-center gap-2 text-sm text-destructive">
                    <XCircle className="h-4 w-4" />
                    {sendResult.error}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <CheckCircle className="h-4 w-4 text-emerald-500" />
                      Task sent
                    </div>
                    <p className="font-mono text-xs text-muted-foreground">
                      {sendResult.taskId}
                    </p>
                    {taskStatus && (
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            taskStatus === "SUCCESS"
                              ? "default"
                              : taskStatus === "FAILURE"
                                ? "destructive"
                                : "outline"
                          }
                        >
                          {taskStatus}
                        </Badge>
                        {taskStatus === "PENDING" && (
                          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                        )}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <div className="space-y-1.5">
            <label htmlFor="tg-queue" className="text-xs font-medium">Queue</label>
            <QueueSelector
              value={queue}
              onChange={setQueue}
              queues={queues}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="tg-args" className="text-xs font-medium">Args</label>
            <ArgsBuilder items={argItems} onChange={setArgItems} />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="tg-kwargs" className="text-xs font-medium">Kwargs</label>
            <KwargsBuilder pairs={kwargPairs} onChange={setKwargPairs} />
          </div>

          <Button
            className="w-full"
            onClick={handleSend}
            disabled={sending}
          >
            {sending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-2 h-4 w-4" />
            )}
            {argItems.length === 0 && kwargPairs.length === 0
              ? "Send without parameters"
              : "Send Task"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
