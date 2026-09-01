import { Badge } from "@/components/ui/badge";

export function formatWorkflowDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function WorkflowStatusBadge({ status }: { status: string }) {
  if (status === "succeeded" || status === "SUCCESS") {
    return <Badge>{status}</Badge>;
  }
  if (status === "failed" || status === "FAILURE") {
    return <Badge variant="destructive">{status}</Badge>;
  }
  if (status === "running" || status === "STARTED" || status === "SENT") {
    return (
      <Badge variant="outline" className="border-sky-500/50 text-sky-500">
        {status}
      </Badge>
    );
  }
  if (status === "cancelled" || status === "REVOKED") {
    return (
      <Badge variant="outline" className="border-amber-500/50 text-amber-500">
        {status}
      </Badge>
    );
  }
  return <Badge variant="outline">{status}</Badge>;
}

export function formatWorkflowDuration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return formatDurationSeconds(ms / 1000);
}

export function formatDurationSeconds(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (m < 60) return rest ? `${m}m ${rest}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

export function parseJson<T>(json: string | null, fallback: T): T {
  if (!json) return fallback;
  try {
    return JSON.parse(json) as T;
  } catch {
    return fallback;
  }
}
