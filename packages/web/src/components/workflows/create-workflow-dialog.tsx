import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { WorkflowEditor, _toIntervalSeconds } from "./workflow-editor";
import { apiPost } from "@/lib/api";
import { Plus } from "lucide-react";

export function CreateWorkflowDialog({ onCreated }: { onCreated?: () => void }) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Create Workflow
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Workflow</DialogTitle>
        </DialogHeader>
        <WorkflowEditor
          onSubmit={async (values, nodes) => {
            const intervalSeconds =
              values.scheduleType === "interval"
                ? _toIntervalSeconds(values.intervalValue, values.intervalUnit)
                : undefined;
            const payload = {
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
            const result = await apiPost<{ id?: string; error?: string }>(
              "/api/workflows",
              payload,
            );
            if (!result.error && result.id) {
              setOpen(false);
              onCreated?.();
            }
            if (result.error) throw new Error(result.error);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
