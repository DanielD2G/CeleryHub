import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  formatDurationSeconds,
  formatWorkflowDate,
  WorkflowStatusBadge,
} from "@/lib/workflow-utils";

interface EventItem {
  eventTime: string;
  eventType: string;
  taskId: string | null;
  taskName: string | null;
  hostname: string | null;
  queue: string | null;
  runtime: number | null;
}

interface EventPage {
  items: EventItem[];
  nextCursor: string | null;
}

const EVENT_TYPES = [
  "task-received",
  "task-started",
  "task-succeeded",
  "task-failed",
  "task-retried",
  "task-revoked",
];

function eventBadge(type: string) {
  const status =
    type === "task-succeeded"
      ? "succeeded"
      : type === "task-failed"
        ? "failed"
        : type === "task-started"
          ? "running"
          : type === "task-revoked"
            ? "cancelled"
            : type;
  return <WorkflowStatusBadge status={status} />;
}

export default function EventsPage() {
  useDocumentTitle("Event Log");
  const [items, setItems] = useState<EventItem[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [taskName, setTaskName] = useState("");
  const [debouncedTaskName, setDebouncedTaskName] = useState("");
  const [eventType, setEventType] = useState("all");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedTaskName(taskName), 300);
    return () => clearTimeout(t);
  }, [taskName]);

  const buildQuery = useCallback(
    (before?: string | null) => {
      const q = new URLSearchParams({ limit: "100" });
      if (debouncedTaskName.trim()) q.set("taskName", debouncedTaskName.trim());
      if (eventType !== "all") q.set("eventType", eventType);
      if (before) q.set("before", before);
      return q.toString();
    },
    [debouncedTaskName, eventType]
  );

  useEffect(() => {
    const controller = new AbortController();
    apiGet<EventPage>(`/api/event-log?${buildQuery()}`, controller.signal)
      .then((page) => {
        setItems(page.items);
        setCursor(page.nextCursor);
        setLoadError(false);
      })
      .catch((e) => {
        if (!(e instanceof DOMException && e.name === "AbortError")) {
          setLoadError(true);
        }
      });
    return () => controller.abort();
  }, [buildQuery]);

  const loadMore = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await apiGet<EventPage>(
        `/api/event-log?${buildQuery(cursor)}`
      );
      setItems((prev) => [...(prev ?? []), ...page.items]);
      setCursor(page.nextCursor);
    } catch {
      setLoadError(true);
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Event Log"
        description="Persistent Celery event history (Postgres-backed, survives restarts)"
      />

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-full sm:w-64">
          <Input
            placeholder="Filter by task name…"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
          />
        </div>
        <Select value={eventType} onValueChange={setEventType}>
          <SelectTrigger className="w-full sm:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All event types</SelectItem>
            {EVENT_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loadError && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          Failed to load the event log.
        </div>
      )}

      {items === null && !loadError ? (
        <Skeleton className="h-64" />
      ) : items && items.length === 0 && !loadError ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12 text-center">
          <p className="text-muted-foreground">No events match the filters.</p>
        </div>
      ) : items && items.length > 0 ? (
        <>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Task</TableHead>
                  <TableHead>Runtime</TableHead>
                  <TableHead>Worker</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((e, i) => (
                  <TableRow key={`${e.taskId}-${e.eventType}-${i}`}>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatWorkflowDate(e.eventTime)}
                    </TableCell>
                    <TableCell>{eventBadge(e.eventType)}</TableCell>
                    <TableCell className="text-sm">
                      {e.taskName ? (
                        <Link
                          to={`/tasks/${encodeURIComponent(e.taskName)}`}
                          className="hover:underline"
                        >
                          {e.taskName}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs tabular-nums">
                      {e.runtime != null
                        ? formatDurationSeconds(e.runtime)
                        : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {e.hostname ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {cursor && (
            <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "Loading…" : "Load older events"}
            </Button>
          )}
          <p className="text-xs text-muted-foreground">
            {items.length} event(s) loaded
            <Badge variant="outline" className="ml-2 text-xs">
              retention applies
            </Badge>
          </p>
        </>
      ) : null}
    </div>
  );
}
