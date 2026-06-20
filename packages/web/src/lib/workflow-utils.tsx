import { Badge } from "@/components/ui/badge";
import type { WorkflowNode, Workflow } from "@/lib/types";

/** Populate `position` from raw `positionX`/`positionY` columns returned by the API. */
export function normalizeWorkflowNode(node: WorkflowNode): WorkflowNode {
  return {
    ...node,
    position:
      node.positionX != null && node.positionY != null
        ? { x: node.positionX, y: node.positionY }
        : null,
  };
}

/** Normalize all nodes in a fetched Workflow so `node.position` is consistently set. */
export function normalizeWorkflow(workflow: Workflow): Workflow {
  return { ...workflow, nodes: workflow.nodes.map(normalizeWorkflowNode) };
}

export function formatWorkflowDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function WorkflowStatusBadge({ status }: { status: string }) {
  const variant =
    status === "succeeded"
      ? "default"
      : status === "failed"
        ? "destructive"
        : "outline";
  return <Badge variant={variant}>{status}</Badge>;
}

export function formatWorkflowDuration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60000)}m`;
}

export function parseJson<T>(json: string | null, fallback: T): T {
  if (!json) return fallback;
  try {
    return JSON.parse(json) as T;
  } catch {
    return fallback;
  }
}
