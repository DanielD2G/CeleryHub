import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useCelery, useCeleryTasks } from "@/hooks/use-celery";
import { useTick } from "@/hooks/use-tick";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TaskGroupKpis, computeTaskGroupStats } from "@/components/tasks/task-group-kpis";
import { TaskGroupActive } from "@/components/tasks/task-group-active";
import { TaskGroupHistory } from "@/components/tasks/task-group-history";
import { SendTaskDialog } from "@/components/tasks/send-task-dialog";
import { ArrowLeft, Send, Play } from "lucide-react";

export default function TaskGroupPage() {
  const { name } = useParams<{ name: string }>();
  const taskName = decodeURIComponent(name || "");
  useDocumentTitle(taskName || "Task");
  const { completedTasks, knownQueues } = useCelery();
  const activeTasks = useCeleryTasks();
  const tick = useTick();

  const [sendOpen, setSendOpen] = useState(false);

  const queues = Array.from(knownQueues).sort();

  const history = Array.from(completedTasks.values())
    .filter((t) => t.name === taskName)
    .sort((a, b) => b.completedAt - a.completedAt);

  const activeForTask = Array.from(activeTasks.values()).filter(
    (t) => t.name === taskName
  );

  const { avgRuntime, runtimeSamples } = computeTaskGroupStats(history);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link
          to="/tasks"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Tasks
        </Link>

        <Button onClick={() => setSendOpen(true)}>
          <Send className="mr-2 h-4 w-4" />
          Send Task
        </Button>
      </div>

      <div>
        <h2 className="text-xl font-bold tracking-tight lg:text-2xl">{taskName}</h2>
        {activeForTask.length > 0 && (
          <div className="mt-1">
            <Badge
              variant="outline"
              className="border-emerald-500/50 text-emerald-500"
            >
              <Play className="mr-0.5 h-2.5 w-2.5 fill-current" />
              {activeForTask.length} running
            </Badge>
          </div>
        )}
      </div>

      {/* KPIs */}
      {history.length > 0 && <TaskGroupKpis history={history} />}

      {/* Active runs */}
      <TaskGroupActive
        tasks={activeForTask}
        avgRuntime={avgRuntime}
        runtimeSamples={runtimeSamples}
        tick={tick}
      />

      {/* Past executions */}
      <TaskGroupHistory history={history} taskName={taskName} />

      {/* Send dialog */}
      <SendTaskDialog
        taskName={taskName}
        queues={queues}
        open={sendOpen}
        onOpenChange={setSendOpen}
      />
    </div>
  );
}
