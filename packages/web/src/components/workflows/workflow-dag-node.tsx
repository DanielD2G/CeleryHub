import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, Clock, Loader2, SkipForward } from "lucide-react";

interface DagNodeProps {
  label: string;
  taskName: string;
  status?: string;
}

const _statusConfig: Record<string, { icon: React.ElementType; className: string }> = {
  pending: { icon: Clock, className: "text-muted-foreground" },
  running: { icon: Loader2, className: "text-chart-1 animate-spin" },
  succeeded: { icon: CheckCircle2, className: "text-chart-2" },
  failed: { icon: XCircle, className: "text-destructive" },
  skipped: { icon: SkipForward, className: "text-muted-foreground" },
};

export function WorkflowDagNode({ label, taskName, status }: DagNodeProps) {
  const config = status ? _statusConfig[status] : undefined;
  const StatusIcon = config?.icon;

  return (
    <Card className="w-[280px] p-3 shadow-sm">
      <div className="flex items-center gap-2">
        {StatusIcon && <StatusIcon className={`h-4 w-4 shrink-0 ${config!.className}`} />}
        <span className="text-sm font-medium truncate">{label}</span>
      </div>
      <div className="mt-1.5">
        <Badge variant="secondary" className="font-mono text-[10px] px-1.5 py-0 max-w-full truncate">
          {taskName}
        </Badge>
      </div>
    </Card>
  );
}
