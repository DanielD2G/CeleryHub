import { useMemo } from "react";
import { useCelery, useCeleryTasks } from "@/hooks/use-celery";
import { timeAgo } from "@/lib/task-utils";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { ListTodo, Play } from "lucide-react";
import { Link } from "react-router-dom";

interface TaskGroup {
  name: string;
  count: number;
  lastRun: number;
  failureCount: number;
  activeCount: number;
}

export function TaskCards() {
  const { completedTasks, knownTaskNames } = useCelery();
  const activeTasks = useCeleryTasks();

  const groups = useMemo(() => {
    // Count active tasks per name
    const activeByName = new Map<string, number>();
    for (const task of activeTasks.values()) {
      if (task.name && task.name !== "unknown") {
        activeByName.set(task.name, (activeByName.get(task.name) ?? 0) + 1);
      }
    }

    // Build groups
    const map = new Map<
      string,
      { count: number; lastRun: number; failureCount: number }
    >();

    for (const task of completedTasks.values()) {
      const name = task.name || "unknown";
      if (name === "unknown") continue;
      const existing = map.get(name);
      if (existing) {
        existing.count++;
        existing.lastRun = Math.max(existing.lastRun, task.completedAt);
        if (task.status === "FAILURE") existing.failureCount++;
      } else {
        map.set(name, {
          count: 1,
          lastRun: task.completedAt,
          failureCount: task.status === "FAILURE" ? 1 : 0,
        });
      }
    }

    for (const name of knownTaskNames) {
      if (!map.has(name) && name !== "unknown") {
        map.set(name, { count: 0, lastRun: 0, failureCount: 0 });
      }
    }

    // Also add names that only appear in active (not yet completed)
    for (const name of activeByName.keys()) {
      if (!map.has(name)) {
        map.set(name, { count: 0, lastRun: 0, failureCount: 0 });
      }
    }

    return Array.from(map.entries())
      .map(([name, data]): TaskGroup => ({
        name,
        ...data,
        activeCount: activeByName.get(name) ?? 0,
      }))
      .sort((a, b) => {
        if (a.activeCount > 0 && b.activeCount === 0) return -1;
        if (b.activeCount > 0 && a.activeCount === 0) return 1;
        return b.lastRun - a.lastRun;
      });
  }, [completedTasks, knownTaskNames, activeTasks]);

  if (groups.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No known tasks yet. Tasks will appear here as they are discovered from
        events.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {groups.map((group) => (
        <Link
          key={group.name}
          to={`/tasks/${encodeURIComponent(group.name)}`}
        >
          <Card
            className={`h-full transition-all hover:shadow-md hover:border-foreground/20 ${group.activeCount > 0 ? "border-emerald-500/40" : ""}`}
          >
            <CardHeader>
              <div className="flex items-center gap-2">
                <ListTodo className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="min-w-0 truncate text-sm" title={group.name}>
                {group.name}
              </CardTitle>
                {group.activeCount > 0 && (
                  <Badge
                    variant="outline"
                    className="ml-auto text-[10px] px-1.5 py-0 border-emerald-500/50 text-emerald-500"
                  >
                    <Play className="mr-0.5 h-2 w-2 fill-current" />
                    {group.activeCount} running
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  {group.lastRun > 0
                    ? `Last run ${timeAgo(group.lastRun)}`
                    : "Never executed"}
                </span>
                <div className="flex items-center gap-2">
                  {group.count > 0 && (
                    <span>{group.count} executions</span>
                  )}
                  {group.failureCount > 0 && (
                    <Badge
                      variant="destructive"
                      className="text-[10px] px-1.5 py-0"
                    >
                      {group.failureCount} failed
                    </Badge>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
