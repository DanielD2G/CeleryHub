import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import type { BeatSchedule, BeatRun } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { BeatForm, type CreateBeatInput } from "@/components/beats/beat-form";
import { BeatRunHistory } from "@/components/beats/beat-run-history";
import { formatSchedule } from "@/lib/scheduler/cron";
import { apiPost, apiPut, apiDelete } from "@/lib/api";
import {
  ArrowLeft,
  Play,
  Pencil,
  Trash2,
  Loader2,
} from "lucide-react";

function InfoRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between py-1.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export function BeatDetailClient({
  beat,
  runs,
  onRefresh,
}: {
  beat: BeatSchedule;
  runs: BeatRun[];
  onRefresh?: () => void;
}) {
  const navigate = useNavigate();
  const [editOpen, setEditOpen] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [runResult, setRunResult] = useState<{
    taskIds?: string[];
    error?: string;
  } | null>(null);

  const taskNames: string[] = JSON.parse(beat.taskNames || "[]");

  const handleToggle = async () => {
    setIsPending(true);
    try {
      await apiPost(`/api/beats/${beat.id}/toggle`);
      onRefresh?.();
    } catch {
      // ignore
    } finally {
      setIsPending(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Delete this beat schedule? This cannot be undone.")) return;
    setIsPending(true);
    try {
      await apiDelete(`/api/beats/${beat.id}`);
      navigate("/beats");
    } catch {
      // ignore
    } finally {
      setIsPending(false);
    }
  };

  const handleRunNow = async () => {
    setIsPending(true);
    try {
      const result = await apiPost<{ taskIds?: string[]; error?: string }>(`/api/beats/${beat.id}/run-now`);
      setRunResult(result);
      onRefresh?.();
    } catch {
      setRunResult({ error: "Failed to run beat" });
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to="/beats"
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <h2 className="text-2xl font-bold tracking-tight">{beat.name}</h2>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {taskNames.map((t) => (
              <Link key={t} to={`/tasks/${encodeURIComponent(t)}`}>
                <Badge
                  variant="outline"
                  className="font-mono text-xs hover:bg-accent cursor-pointer"
                >
                  {t}
                </Badge>
              </Link>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRunNow}
            disabled={isPending}
          >
            {isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Run Now
          </Button>

          <Dialog open={editOpen} onOpenChange={setEditOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Pencil className="mr-2 h-4 w-4" />
                Edit
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Edit Beat Schedule</DialogTitle>
              </DialogHeader>
              <BeatForm
                initialValues={{
                  name: beat.name,
                  taskNames,
                  args: beat.args || "[]",
                  kwargs: beat.kwargs || "{}",
                  queue: beat.queue || "celery",
                  scheduleType: beat.scheduleType as "interval" | "cron",
                  intervalSeconds: beat.intervalSeconds ?? undefined,
                  cronExpression: beat.cronExpression ?? undefined,
                  enabled: beat.enabled ?? true,
                  maxRunCount: beat.maxRunCount,
                }}
                onSubmit={async (input: CreateBeatInput) => {
                  try {
                    const result = await apiPut<{ error?: string }>(`/api/beats/${beat.id}`, input);
                    if (!result.error) {
                      setEditOpen(false);
                      onRefresh?.();
                    }
                    return result;
                  } catch (e) {
                    return { error: e instanceof Error ? e.message : "Failed to update" };
                  }
                }}
                submitLabel="Save Changes"
              />
            </DialogContent>
          </Dialog>

          <Button
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            disabled={isPending}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {runResult && (
        <Card>
          <CardContent className="pt-4">
            {runResult.error ? (
              <p className="text-sm text-destructive">{runResult.error}</p>
            ) : (
              <div className="space-y-1">
                <p className="text-sm">
                  Dispatched {runResult.taskIds?.length || 0} task
                  {(runResult.taskIds?.length || 0) !== 1 ? "s" : ""}:
                </p>
                {runResult.taskIds?.map((id) => (
                  <code key={id} className="block text-xs text-muted-foreground">
                    {id}
                  </code>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="py-1.5">
              <span className="text-sm text-muted-foreground">Tasks</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {taskNames.map((t) => (
                  <Link key={t} to={`/tasks/${encodeURIComponent(t)}`}>
                    <Badge
                      variant="secondary"
                      className="font-mono text-xs hover:bg-accent cursor-pointer"
                    >
                      {t}
                    </Badge>
                  </Link>
                ))}
              </div>
            </div>
            <InfoRow label="Schedule">
              <Badge variant="outline" className="font-mono text-xs">
                {formatSchedule(
                  beat.scheduleType,
                  beat.intervalSeconds,
                  beat.cronExpression
                )}
              </Badge>
            </InfoRow>
            <InfoRow label="Queue">{beat.queue}</InfoRow>
            <InfoRow label="Args">
              <code className="text-xs">{beat.args}</code>
            </InfoRow>
            <InfoRow label="Kwargs">
              <code className="text-xs">{beat.kwargs}</code>
            </InfoRow>
            <InfoRow label="Max Runs">
              {beat.maxRunCount != null ? beat.maxRunCount : "Unlimited"}
            </InfoRow>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="flex items-center justify-between py-1.5">
              <Label htmlFor="beat-detail-enabled" className="text-sm text-muted-foreground">Enabled</Label>
              <Switch
                id="beat-detail-enabled"
                checked={beat.enabled ?? false}
                onCheckedChange={handleToggle}
                disabled={isPending}
              />
            </div>
            <InfoRow label="Total Runs">{beat.totalRunCount}</InfoRow>
            <InfoRow label="Last Run">
              {beat.lastRunAt
                ? new Date(beat.lastRunAt).toLocaleString()
                : "Never"}
            </InfoRow>
            <InfoRow label="Next Run">
              {beat.enabled && beat.nextRunAt
                ? new Date(beat.nextRunAt).toLocaleString()
                : "—"}
            </InfoRow>
            <InfoRow label="Created">
              {new Date(beat.createdAt).toLocaleString()}
            </InfoRow>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold">Execution Log</h3>
        <BeatRunHistory runs={runs} />
      </div>
    </div>
  );
}
