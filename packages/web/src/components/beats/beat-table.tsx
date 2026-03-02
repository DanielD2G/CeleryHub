import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { BeatSchedule } from "@/lib/types";
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

function computeRelativeLabel(iso: string): string {
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

function RelativeTime({ iso, warnIfPast }: { iso: string | null; warnIfPast?: boolean }) {
  const [label, setLabel] = useState(() =>
    iso ? computeRelativeLabel(iso) : "—"
  );
  const [isPast, setIsPast] = useState(() =>
    iso ? new Date(iso).getTime() < Date.now() : false
  );

  useEffect(() => {
    if (!iso) return;
    const update = () => {
      setLabel(computeRelativeLabel(iso));
      setIsPast(new Date(iso).getTime() < Date.now());
    };
    update();
    const id = setInterval(update, 5000);
    return () => clearInterval(id);
  }, [iso]);

  if (!iso) return <span className="text-muted-foreground">—</span>;
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

export function BeatTable({ beats, onRefresh }: { beats: BeatSchedule[]; onRefresh?: () => void }) {
  const navigate = useNavigate();
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const handleToggle = async (id: string) => {
    setTogglingId(id);
    try {
      await apiPost(`/api/beats/${id}/toggle`);
      onRefresh?.();
    } catch {
      // ignore
    } finally {
      setTogglingId(null);
    }
  };

  if (beats.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12 text-center">
        <p className="text-muted-foreground">No beat schedules yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Create one to start dispatching periodic tasks
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
            <TableHead>Tasks</TableHead>
            <TableHead>Schedule</TableHead>
            <TableHead>Queue</TableHead>
            <TableHead>Last Run</TableHead>
            <TableHead>Next Run</TableHead>
            <TableHead className="text-center">Runs</TableHead>
            <TableHead className="text-center">Enabled</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {beats.map((beat) => (
            <TableRow
              key={beat.id}
              className="cursor-pointer"
              onClick={() => navigate(`/beats/${beat.id}`)}
            >
              <TableCell className="font-medium">{beat.name}</TableCell>
              <TableCell className="font-mono text-xs" onClick={(e) => e.stopPropagation()}>
                {(() => {
                  const names: string[] = JSON.parse(beat.taskNames || "[]");
                  if (names.length === 0) return "—";
                  return names.map((n, i) => (
                    <span key={n}>
                      {i > 0 && <span className="text-muted-foreground">, </span>}
                      <Link to={`/tasks/${encodeURIComponent(n)}`} className="hover:underline">
                        {n}
                      </Link>
                    </span>
                  ));
                })()}
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="font-mono text-xs">
                  {formatSchedule(
                    beat.scheduleType,
                    beat.intervalSeconds,
                    beat.cronExpression
                  )}
                </Badge>
              </TableCell>
              <TableCell>{beat.queue}</TableCell>
              <TableCell className="text-sm">
                <RelativeTime iso={beat.lastRunAt} />
              </TableCell>
              <TableCell className="text-sm">
                {beat.enabled ? (
                  <RelativeTime iso={beat.nextRunAt} warnIfPast />
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                {beat.totalRunCount}
                {beat.maxRunCount != null && (
                  <span className="text-muted-foreground">
                    /{beat.maxRunCount}
                  </span>
                )}
              </TableCell>
              <TableCell
                className="text-center"
                onClick={(e) => e.stopPropagation()}
              >
                <Switch
                  checked={beat.enabled ?? false}
                  onCheckedChange={() => handleToggle(beat.id)}
                  disabled={togglingId === beat.id}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
