import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface PendingTask {
  taskId: string;
  taskName: string;
  enqueuedAt: string;
}

export function QueueCard({
  name,
  depth,
  pending,
}: {
  name: string;
  depth: number;
  pending: PendingTask[];
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{name}</CardTitle>
        <Badge variant={depth > 0 ? "default" : "secondary"}>{depth}</Badge>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-3xl font-bold">{depth}</p>

        {pending.length > 0 ? (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Pending tasks:</p>
            {pending.map((task) => (
              <div
                key={task.taskId}
                className="flex items-center justify-between text-xs"
              >
                <span className="truncate font-medium">{task.taskName}</span>
                <span className="font-mono text-muted-foreground">
                  {task.taskId.slice(0, 8)}...
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Queue is empty</p>
        )}
      </CardContent>
    </Card>
  );
}
