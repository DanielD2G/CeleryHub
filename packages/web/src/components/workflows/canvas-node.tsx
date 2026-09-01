import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Badge } from "@/components/ui/badge";

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-blue-500/15 text-blue-600",
  succeeded: "bg-green-500/15 text-green-600",
  failed: "bg-red-500/15 text-red-600",
  skipped: "bg-amber-500/15 text-amber-600",
};

export function CanvasNode({ data, selected }: NodeProps) {
  const status = data.status as string | undefined;
  return (
    <div
      className={`rounded-md border bg-card px-3 py-2 shadow-sm w-[260px] ${
        selected ? "ring-2 ring-primary" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} />
      <div className="text-sm font-medium truncate">{data.label as string}</div>
      <div className="text-xs text-muted-foreground truncate">
        {data.taskName as string}
      </div>
      {status && (
        <Badge className={`mt-1 ${STATUS_COLOR[status] ?? ""}`}>{status}</Badge>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
