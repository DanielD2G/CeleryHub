import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import type { Workflow, WorkflowNode } from "@/lib/types";
import { apiGet, apiPost, apiPut } from "@/lib/api";
import { normalizeWorkflow } from "@/lib/workflow-utils";
import {
  WorkflowEditor,
  _detectIntervalUnit,
  _toIntervalSeconds,
  type WorkflowFormValues,
} from "@/components/workflows/workflow-editor";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Loader2 } from "lucide-react";

function _buildPayload(values: WorkflowFormValues, nodes: WorkflowNode[]) {
  const intervalSeconds =
    values.scheduleType === "interval"
      ? _toIntervalSeconds(values.intervalValue, values.intervalUnit)
      : undefined;
  return {
    name: values.name,
    description: values.description || null,
    scheduleType: values.scheduleType,
    intervalSeconds,
    cronExpression:
      values.scheduleType === "cron" ? values.cronExpression : undefined,
    enabled: values.enabled,
    maxRunCount: values.maxRunCount ? parseInt(values.maxRunCount, 10) : null,
    nodes: nodes.map((n) => ({
      id: n.id,
      label: n.label,
      taskName: n.taskName,
      args: n.args ?? "[]",
      kwargs: n.kwargs ?? "{}",
      queue: n.queue,
      dependsOn: JSON.parse(n.dependsOn),
      condition: n.condition,
      timeoutSeconds: n.timeoutSeconds,
      positionX: n.position?.x ?? n.positionX ?? null,
      positionY: n.position?.y ?? n.positionY ?? null,
    })),
  };
}

function _toDefaults(workflow: Workflow): Partial<WorkflowFormValues> {
  return {
    name: workflow.name,
    description: workflow.description ?? "",
    scheduleType: workflow.scheduleType as "none" | "interval" | "cron",
    intervalValue: workflow.intervalSeconds
      ? String(_detectIntervalUnit(workflow.intervalSeconds).value)
      : "10",
    intervalUnit: workflow.intervalSeconds
      ? _detectIntervalUnit(workflow.intervalSeconds).unit
      : "seconds",
    cronExpression: workflow.cronExpression ?? "* * * * *",
    enabled: workflow.enabled,
    maxRunCount:
      workflow.maxRunCount != null ? String(workflow.maxRunCount) : "",
  };
}

export function WorkflowEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEdit = Boolean(id);

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(isEdit);

  useEffect(() => {
    if (!id) return;
    let active = true;
    apiGet<Workflow>(`/api/workflows/${id}`)
      .catch(() => null)
      .then((wf) => {
        if (!active) return;
        setWorkflow(wf ? normalizeWorkflow(wf) : null);
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  const handleSubmit = async (
    values: WorkflowFormValues,
    nodes: WorkflowNode[],
  ) => {
    const payload = _buildPayload(values, nodes);
    if (isEdit) {
      const result = await apiPut<{ error?: string }>(
        `/api/workflows/${id}`,
        payload,
      );
      if (result.error) throw new Error(result.error);
      navigate(`/workflows/${id}`);
    } else {
      const result = await apiPost<{ id?: string; error?: string }>(
        "/api/workflows",
        payload,
      );
      if (result.error) throw new Error(result.error);
      if (result.id) navigate(`/workflows/${result.id}`);
    }
  };

  const backTo = isEdit ? `/workflows/${id}` : "/workflows";

  if (isEdit && loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isEdit && !workflow) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Workflow not found</p>
        <Button asChild variant="outline">
          <Link to="/workflows">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to workflows
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <WorkflowEditor
        key={workflow?.id ?? "new"}
        defaultValues={workflow ? _toDefaults(workflow) : undefined}
        nodes={workflow?.nodes}
        onBack={() => navigate(backTo)}
        onSubmit={handleSubmit}
        submitLabel={isEdit ? "Save Changes" : "Create Workflow"}
      />
    </div>
  );
}
