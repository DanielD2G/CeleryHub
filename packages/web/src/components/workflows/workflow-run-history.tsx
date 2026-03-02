import { useNavigate } from "react-router-dom";
import type { WorkflowRun } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

function _formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function _StatusBadge({ status }: { status: string }) {
  const variant =
    status === "succeeded"
      ? "default"
      : status === "failed"
        ? "destructive"
        : "outline";
  return <Badge variant={variant}>{status}</Badge>;
}

function _formatDuration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60000)}m`;
}

export function WorkflowRunHistory({
  runs,
  workflowId,
}: {
  runs: WorkflowRun[];
  workflowId: string;
}) {
  const navigate = useNavigate();

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
            <TableHead>Started At</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Trigger</TableHead>
            <TableHead>Duration</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow
              key={run.id}
              className="cursor-pointer"
              onClick={() => navigate(`/workflows/${workflowId}/runs/${run.id}`)}
            >
              <TableCell className="text-sm">{_formatDate(run.startedAt)}</TableCell>
              <TableCell>
                <_StatusBadge status={run.status} />
              </TableCell>
              <TableCell>
                <Badge variant="secondary" className="text-xs">
                  {run.trigger}
                </Badge>
              </TableCell>
              <TableCell className="text-sm">
                {_formatDuration(run.startedAt, run.finishedAt)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
