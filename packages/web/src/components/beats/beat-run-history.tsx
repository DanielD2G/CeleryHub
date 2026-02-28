import { Link } from "react-router-dom";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

interface BeatRun {
  id: string;
  scheduledAt: string | null;
  sentAt: string | null;
  taskId: string | null;
  taskName: string | null;
  status: string | null;
  error: string | null;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return null;
  const variant =
    status === "SENT"
      ? "outline"
      : status === "SUCCESS"
        ? "default"
        : "destructive";
  return <Badge variant={variant}>{status}</Badge>;
}

export function BeatRunHistory({ runs }: { runs: BeatRun[] }) {
  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-8 text-center">
        <p className="text-muted-foreground">No runs yet</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Task</TableHead>
            <TableHead>Scheduled At</TableHead>
            <TableHead>Sent At</TableHead>
            <TableHead>Task ID</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Error</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.id}>
              <TableCell className="text-sm font-medium">
                {run.taskName ? (
                  <Link to={`/tasks/${encodeURIComponent(run.taskName)}`} className="hover:underline">
                    {run.taskName}
                  </Link>
                ) : "—"}
              </TableCell>
              <TableCell className="text-sm">
                {formatDate(run.scheduledAt)}
              </TableCell>
              <TableCell className="text-sm">
                {formatDate(run.sentAt)}
              </TableCell>
              <TableCell className="font-mono text-xs">
                {run.taskId ? run.taskId.slice(0, 8) + "..." : "—"}
              </TableCell>
              <TableCell>
                <StatusBadge status={run.status} />
              </TableCell>
              <TableCell className="text-sm text-destructive">
                {run.error || "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
