import { useState, useRef } from "react";
import { useCelery } from "@/hooks/use-celery";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Send, CheckCircle, XCircle, Loader2 } from "lucide-react";

interface SendResult {
  taskId?: string;
  error?: string;
}

export function SendForm() {
  const { knownTaskNames } = useCelery();
  const [taskName, setTaskName] = useState("");
  const [queue, setQueue] = useState("celery");
  const [args, setArgs] = useState("[]");
  const [kwargs, setKwargs] = useState("{}");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<SendResult | null>(null);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestions = Array.from(knownTaskNames).filter((name) =>
    name.toLowerCase().includes(taskName.toLowerCase())
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSending(true);
    setResult(null);
    setTaskStatus(null);

    try {
      const res = await fetch("/api/tasks/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskName, queue, args, kwargs }),
      });
      const data = await res.json();
      setResult(data);

      // Poll for status if we got a taskId
      if (data.taskId) {
        let attempts = 0;
        const poll = async () => {
          if (attempts >= 30) {
            setTaskStatus("TIMEOUT");
            return;
          }
          attempts++;
          try {
            const statusRes = await fetch(`/api/tasks/${data.taskId}/status`);
            const status = await statusRes.json();
            if (status && status.status !== "PENDING") {
              setTaskStatus(status.status);
            } else {
              setTaskStatus("PENDING");
              setTimeout(poll, 2000);
            }
          } catch {
            setTimeout(poll, 2000);
          }
        };
        setTimeout(poll, 1000);
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-2">
        <label className="text-sm font-medium">Task Name</label>
        <div className="relative">
          <Input
            ref={inputRef}
            value={taskName}
            onChange={(e) => {
              setTaskName(e.target.value);
              setShowSuggestions(true);
            }}
            onFocus={() => setShowSuggestions(true)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
            placeholder="e.g. app.tasks.process_data"
            required
          />
          {showSuggestions && suggestions.length > 0 && taskName && (
            <div className="absolute top-full left-0 z-10 mt-1 w-full rounded-md border bg-popover p-1 shadow-md">
              {suggestions.slice(0, 8).map((name) => (
                <button
                  key={name}
                  type="button"
                  className="w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent"
                  onMouseDown={() => {
                    setTaskName(name);
                    setShowSuggestions(false);
                  }}
                >
                  {name}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium">Queue</label>
        <Input
          value={queue}
          onChange={(e) => setQueue(e.target.value)}
          placeholder="celery"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label className="text-sm font-medium">Args (JSON array)</label>
          <Textarea
            value={args}
            onChange={(e) => setArgs(e.target.value)}
            placeholder="[]"
            className="font-mono text-sm"
            rows={4}
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Kwargs (JSON object)</label>
          <Textarea
            value={kwargs}
            onChange={(e) => setKwargs(e.target.value)}
            placeholder="{}"
            className="font-mono text-sm"
            rows={4}
          />
        </div>
      </div>

      <Button type="submit" disabled={sending || !taskName}>
        {sending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <Send className="mr-2 h-4 w-4" />
        )}
        Send Task
      </Button>

      {result && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              {result.error ? (
                <>
                  <XCircle className="h-4 w-4 text-destructive" />
                  Error
                </>
              ) : (
                <>
                  <CheckCircle className="h-4 w-4 text-emerald-500" />
                  Task Sent
                </>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {result.error ? (
              <p className="text-sm text-destructive">{result.error}</p>
            ) : (
              <div className="space-y-2">
                <p className="font-mono text-xs">{result.taskId}</p>
                {taskStatus && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      Status:
                    </span>
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
    </form>
  );
}
