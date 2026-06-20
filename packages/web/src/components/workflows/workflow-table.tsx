import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { WorkflowSummary } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { formatSchedule } from "@/lib/scheduler/cron";
import { apiPost } from "@/lib/api";
import { useTick } from "@/hooks/use-tick";

function _computeRelativeLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = d.getTime() - now.getTime();
  const absDiff = Math.abs(diff);

  let label: string;
  if (absDiff < 60000) label = `${Math.round(absDiff / 1000)}s`;
  else if (absDiff < 3600000) label = `${Math.round(absDiff / 60000)}m`;
  else label = `${Math.round(absDiff / 3600000)}h`;

  if (diff < 0) label = `${label} ago`;
  else label = `in ${label}`;

  return label;
}

function _RelativeTime({ iso, warnIfPast }: { iso: string | null; warnIfPast?: boolean }) {
  useTick(); // shared 1s timer — no per-row setInterval

  if (!iso) return <span className="text-muted-foreground">—</span>;

  const label = _computeRelativeLabel(iso);
  const isPast = new Date(iso).getTime() < Date.now();

  return (
    <span
      title={new Date(iso).toISOString()}
      className={warnIfPast && isPast ? "text-amber-500" : undefined}
    >
      {label}
      {warnIfPast && isPast && " (overdue)"}
    </span>
  );
}

export function WorkflowTable({
  workflows,
  onRefresh,
}: {
  workflows: WorkflowSummary[];
  onRefresh?: () => void;
}) {
  const navigate = useNavigate();
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const handleToggle = async (id: string) => {
    setTogglingId(id);
    try {
      await apiPost(`/api/workflows/${id}/toggle`);
      onRefresh?.();
    } catch {
      // ignore
    } finally {
      setTogglingId(null);
    }
  };

  if (workflows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12 text-center">
        <p className="text-muted-foreground">No workflows yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Create one to start orchestrating tasks
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead className="text-center">Nodes</TableHead>
            <TableHead>Schedule</TableHead>
            <TableHead>Last Run</TableHead>
            <TableHead>Next Run</TableHead>
            <TableHead className="text-center">Runs</TableHead>
            <TableHead className="text-center">Enabled</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {workflows.map((wf) => (
            <TableRow
              key={wf.id}
              className="cursor-pointer"
              onClick={() => navigate(`/workflows/${wf.id}`)}
            >
              <TableCell className="font-medium">
                <div>
                  {wf.name}
                  {wf.description && (
                    <p className="text-xs text-muted-foreground truncate max-w-[200px]">
                      {wf.description}
                    </p>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-center">{wf.nodeCount}</TableCell>
              <TableCell>
                <Badge variant="outline" className="font-mono text-xs">
                  {formatSchedule(wf.scheduleType, wf.intervalSeconds, wf.cronExpression)}
                </Badge>
              </TableCell>
              <TableCell className="text-sm">
                <_RelativeTime iso={wf.lastRunAt} />
              </TableCell>
              <TableCell className="text-sm">
                {wf.enabled && wf.scheduleType !== "none" ? (
                  <_RelativeTime iso={wf.nextRunAt} warnIfPast />
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                {wf.totalRunCount}
                {wf.maxRunCount != null && (
                  <span className="text-muted-foreground">/{wf.maxRunCount}</span>
                )}
              </TableCell>
              <TableCell
                className="text-center"
                onClick={(e) => e.stopPropagation()}
              >
                <Switch
                  checked={wf.enabled}
                  onCheckedChange={() => handleToggle(wf.id)}
                  disabled={togglingId === wf.id}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
