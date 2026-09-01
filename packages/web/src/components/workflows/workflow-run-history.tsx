import { clickableRow } from "@/lib/row-nav";
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
import {
  formatWorkflowDate,
  WorkflowStatusBadge,
  formatWorkflowDuration,
} from "@/lib/workflow-utils";

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
              {...clickableRow(() => navigate(`/workflows/${workflowId}/runs/${run.id}`))}
            >
              <TableCell className="text-sm">{formatWorkflowDate(run.startedAt)}</TableCell>
              <TableCell>
                <WorkflowStatusBadge status={run.status} />
              </TableCell>
              <TableCell>
                <Badge variant="secondary" className="text-xs">
                  {run.trigger}
                </Badge>
              </TableCell>
              <TableCell className="text-sm">
                {formatWorkflowDuration(run.startedAt, run.finishedAt)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
