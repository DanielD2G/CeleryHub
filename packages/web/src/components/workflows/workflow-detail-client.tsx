import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import type { Workflow, WorkflowRun } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { parseJson } from "@/lib/workflow-utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  WorkflowForm,
  type CreateWorkflowInput,
} from "@/components/workflows/workflow-form";
import { apiToStepEditor } from "@/components/workflows/workflow-step-editor";
import { WorkflowRunHistory } from "@/components/workflows/workflow-run-history";
import { WorkflowDag } from "@/components/workflows/workflow-dag";
import { formatSchedule } from "@/lib/scheduler/cron";
import { apiPost, apiPut, apiDelete } from "@/lib/api";
import { WorkflowDurationChart } from "@/components/workflows/workflow-duration-chart";
import { ArrowLeft, Play, Pencil, Trash2, Loader2, Download, Copy } from "lucide-react";

function _InfoRow({
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

function _workflowToExportJson(workflow: Workflow): string {
  return JSON.stringify(
    {
      name: workflow.name,
      description: workflow.description,
      scheduleType: workflow.scheduleType,
      intervalSeconds: workflow.intervalSeconds,
      cronExpression: workflow.cronExpression,
      enabled: workflow.enabled,
      maxRunCount: workflow.maxRunCount,
      steps: workflow.steps.map((s) => ({
        id: s.id,
        label: s.label,
        taskNames: parseJson<string[]>(s.taskNames, []),
        args: s.args,
        kwargs: s.kwargs,
        queue: s.queue,
        dependsOn: parseJson<string[]>(s.dependsOn, []),
        condition: s.condition,
      })),
    },
    null,
    2
  );
}

export function WorkflowDetailClient({
  workflow,
  runs,
  onRefresh,
}: {
  workflow: Workflow;
  runs: WorkflowRun[];
  onRefresh?: () => void;
}) {
  const navigate = useNavigate();
  const [editOpen, setEditOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [duplicateName, setDuplicateName] = useState("");
  const [copied, setCopied] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [runResult, setRunResult] = useState<{
    runId?: string;
    error?: string;
  } | null>(null);

  const handleToggle = async () => {
    setIsPending(true);
    try {
      await apiPost(`/api/workflows/${workflow.id}/toggle`);
      onRefresh?.();
    } catch {
      // ignore
    } finally {
      setIsPending(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Delete this workflow? This cannot be undone.")) return;
    setIsPending(true);
    try {
      await apiDelete(`/api/workflows/${workflow.id}`);
      navigate("/workflows");
    } catch {
      // ignore
    } finally {
      setIsPending(false);
    }
  };

  const handleRunNow = async () => {
    setIsPending(true);
    try {
      const result = await apiPost<{ runId?: string; error?: string }>(
        `/api/workflows/${workflow.id}/run-now`
      );
      setRunResult(result);
      onRefresh?.();
    } catch {
      setRunResult({ error: "Failed to run workflow" });
    } finally {
      setIsPending(false);
    }
  };

  const handleDuplicate = async () => {
    setIsPending(true);
    try {
      const result = await apiPost<{ id?: string; error?: string }>(
        `/api/workflows/${workflow.id}/duplicate`,
        { name: duplicateName || null }
      );
      if (result.id) {
        setDuplicateOpen(false);
        navigate(`/workflows/${result.id}`);
      }
    } catch {
      // ignore
    } finally {
      setIsPending(false);
    }
  };

  const handleCopyExport = async () => {
    await navigator.clipboard.writeText(_workflowToExportJson(workflow));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to="/workflows"
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <h2 className="text-2xl font-bold tracking-tight">{workflow.name}</h2>
          {workflow.description && (
            <p className="mt-0.5 text-sm text-muted-foreground">
              {workflow.description}
            </p>
          )}
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
            <DialogContent className="sm:max-w-6xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Edit Workflow</DialogTitle>
              </DialogHeader>
              <WorkflowForm
                initialValues={{
                  name: workflow.name,
                  description: workflow.description,
                  scheduleType: workflow.scheduleType,
                  intervalSeconds: workflow.intervalSeconds ?? undefined,
                  cronExpression: workflow.cronExpression ?? undefined,
                  enabled: workflow.enabled,
                  maxRunCount: workflow.maxRunCount,
                  steps: workflow.steps.map(apiToStepEditor),
                }}
                onSubmit={async (input: CreateWorkflowInput) => {
                  try {
                    const result = await apiPut<{ error?: string }>(
                      `/api/workflows/${workflow.id}`,
                      input
                    );
                    if (!result.error) {
                      setEditOpen(false);
                      onRefresh?.();
                    }
                    return result;
                  } catch (e) {
                    return {
                      error: e instanceof Error ? e.message : "Failed to update",
                    };
                  }
                }}
                submitLabel="Save Changes"
              />
            </DialogContent>
          </Dialog>

          <Dialog
            open={duplicateOpen}
            onOpenChange={(v) => {
              setDuplicateOpen(v);
              if (v) setDuplicateName(`${workflow.name} (Copy)`);
            }}
          >
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Copy className="mr-2 h-4 w-4" />
                Duplicate
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Duplicate Workflow</DialogTitle>
              </DialogHeader>
              <div className="space-y-2">
                <Label htmlFor="dup-name">Name</Label>
                <Input
                  id="dup-name"
                  value={duplicateName}
                  onChange={(e) => setDuplicateName(e.target.value)}
                  placeholder="New workflow name"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleDuplicate();
                    }
                  }}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setDuplicateOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleDuplicate} disabled={isPending || !duplicateName.trim()}>
                  {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Duplicate
                </Button>
              </div>
            </DialogContent>
          </Dialog>

          <Dialog
            open={exportOpen}
            onOpenChange={(v) => {
              setExportOpen(v);
              if (!v) setCopied(false);
            }}
          >
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Download className="mr-2 h-4 w-4" />
                Export
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle>Export Workflow</DialogTitle>
              </DialogHeader>
              <p className="text-sm text-muted-foreground">
                Copy this JSON to import the workflow into another CeleryHub instance.
              </p>
              <textarea
                readOnly
                value={_workflowToExportJson(workflow)}
                className="min-h-[300px] w-full rounded-md border border-input bg-muted/50 px-3 py-2 font-mono text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                rows={15}
              />
              <div className="flex justify-end">
                <Button onClick={handleCopyExport}>
                  {copied ? "Copied!" : "Copy to clipboard"}
                </Button>
              </div>
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
              <p className="text-sm">
                Workflow run started:{" "}
                <Link
                  to={`/workflows/${workflow.id}/runs/${runResult.runId}`}
                  className="font-mono text-xs hover:underline"
                >
                  {runResult.runId?.slice(0, 8)}...
                </Link>
              </p>
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
            <_InfoRow label="Schedule">
              <Badge variant="outline" className="font-mono text-xs">
                {formatSchedule(
                  workflow.scheduleType,
                  workflow.intervalSeconds,
                  workflow.cronExpression
                )}
              </Badge>
            </_InfoRow>
            <_InfoRow label="Steps">{workflow.steps.length}</_InfoRow>
            <_InfoRow label="Max Runs">
              {workflow.maxRunCount != null ? workflow.maxRunCount : "Unlimited"}
            </_InfoRow>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="flex items-center justify-between py-1.5">
              <Label
                htmlFor="wf-detail-enabled"
                className="text-sm text-muted-foreground"
              >
                Enabled
              </Label>
              <Switch
                id="wf-detail-enabled"
                checked={workflow.enabled}
                onCheckedChange={handleToggle}
                disabled={isPending}
              />
            </div>
            <_InfoRow label="Total Runs">{workflow.totalRunCount}</_InfoRow>
            <_InfoRow label="Last Run">
              {workflow.lastRunAt
                ? new Date(workflow.lastRunAt).toLocaleString()
                : "Never"}
            </_InfoRow>
            <_InfoRow label="Next Run">
              {workflow.enabled && workflow.nextRunAt
                ? new Date(workflow.nextRunAt).toLocaleString()
                : "—"}
            </_InfoRow>
            <_InfoRow label="Created">
              {new Date(workflow.createdAt).toLocaleString()}
            </_InfoRow>
          </CardContent>
        </Card>
      </div>

      {workflow.steps.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-lg font-semibold">Workflow DAG</h3>
          <WorkflowDag steps={workflow.steps} scheduleType={workflow.scheduleType} />
        </div>
      )}

      <div className="space-y-4">
        <h3 className="text-lg font-semibold">Run History</h3>
        <div className="space-y-4">
          <WorkflowDurationChart workflowId={workflow.id} />
          <WorkflowRunHistory runs={runs} workflowId={workflow.id} />
        </div>
      </div>
    </div>
  );
}
