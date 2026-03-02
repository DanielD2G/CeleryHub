import { Link } from "react-router-dom";
import { useCeleryEvents } from "@/hooks/use-celery";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { CeleryEvent } from "@/lib/types";

function getEventBadgeVariant(
  type: string
): "default" | "secondary" | "destructive" | "outline" {
  if (type.includes("failed") || type.includes("revoked")) return "destructive";
  if (type.includes("succeeded")) return "default";
  if (type.includes("worker")) return "secondary";
  return "outline";
}

function TaskLink({ name }: { name: string }) {
  return (
    <Link
      to={`/tasks/${encodeURIComponent(name)}`}
      className="hover:underline"
      onClick={(e) => e.stopPropagation()}
    >
      {name}
    </Link>
  );
}

function getEventLabel(event: CeleryEvent): React.ReactNode {
  const e = event as CeleryEvent & {
    uuid?: string;
    name?: string;
    exception?: string;
    result?: string;
    runtime?: number;
    active?: number;
    processed?: number;
  };

  switch (event.type) {
    case "worker-online":
      return event.hostname;
    case "worker-offline":
      return event.hostname;
    case "worker-heartbeat":
      return `${event.hostname} (active: ${e.active ?? 0}, processed: ${e.processed ?? 0})`;
    case "task-sent":
    case "task-received":
      return <><TaskLink name={e.name || "unknown"} /> [{e.uuid?.slice(0, 8) || ""}...]</>;
    case "task-started":
      return `${e.uuid?.slice(0, 8) || ""}... on ${event.hostname}`;
    case "task-succeeded":
      return `${e.uuid?.slice(0, 8) || ""}... (${e.runtime?.toFixed(3) || "?"}s)`;
    case "task-failed":
      return `${e.uuid?.slice(0, 8) || ""}... ${e.exception || ""}`;
    case "task-retried":
      return `${e.uuid?.slice(0, 8) || ""}... retry`;
    case "task-revoked":
      return `${e.uuid?.slice(0, 8) || ""}... revoked`;
    default:
      return event.hostname;
  }
}

function formatTimestamp(ts: number): string {
  const date = new Date(ts * 1000);
  return date.toLocaleTimeString("en-US", { hour12: false });
}

export function LiveFeed() {
  const events = useCeleryEvents();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Live Feed</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[400px]">
          <div className="space-y-0">
            {events.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">
                Waiting for events...
              </p>
            ) : (
              events.slice(0, 50).map((event, i) => (
                <div
                  key={`${event.timestamp}-${i}`}
                  className="flex items-center gap-3 border-b px-4 py-2 text-sm last:border-0"
                >
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">
                    {formatTimestamp(event.timestamp)}
                  </span>
                  <Badge
                    variant={getEventBadgeVariant(event.type)}
                    className="shrink-0 text-xs"
                  >
                    {event.type}
                  </Badge>
                  <span className="truncate">{getEventLabel(event)}</span>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
