import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useCelery, useCeleryTasks } from "@/hooks/use-celery";
import { useTick } from "@/hooks/use-tick";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TaskGroupKpis, computeTaskGroupStats } from "@/components/tasks/task-group-kpis";
import { TaskGroupActive } from "@/components/tasks/task-group-active";
import { TaskGroupHistory } from "@/components/tasks/task-group-history";
import { SendTaskDialog } from "@/components/tasks/send-task-dialog";
import { ArrowLeft, Send, Play, Timer } from "lucide-react";
import { formatSchedule } from "@/lib/scheduler/cron";

interface BeatInfo {
  id: string;
  name: string;
  scheduleType: string;
  intervalSeconds: number | null;
  cronExpression: string | null;
  enabled: boolean | null;
}

export default function TaskGroupPage() {
  const { name } = useParams<{ name: string }>();
  const taskName = decodeURIComponent(name || "");
  useDocumentTitle(taskName || "Task");
  const { completedTasks, knownQueues } = useCelery();
  const activeTasks = useCeleryTasks();
  const tick = useTick();

  const [beatsForTask, setBeatsForTask] = useState<BeatInfo[]>([]);
  const [sendOpen, setSendOpen] = useState(false);

  useEffect(() => {
    apiGet<Array<Record<string, unknown>>>("/api/beats")
      .then((beats) => {
        const matching = beats.filter((b) => {
          const names: string[] = JSON.parse(
            (b.taskNames as string) || "[]"
          );
          return names.includes(taskName);
        });
        setBeatsForTask(
          matching.map((b) => ({
            id: b.id as string,
            name: b.name as string,
            scheduleType: b.scheduleType as string,
            intervalSeconds: b.intervalSeconds as number | null,
            cronExpression: b.cronExpression as string | null,
            enabled: b.enabled as boolean | null,
          }))
        );
      })
      .catch(() => {});
  }, [taskName]);

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

      {/* Scheduled by beats */}
      {beatsForTask.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Timer className="h-4 w-4" />
            Scheduled by
          </h3>
          <div className="flex flex-wrap gap-2">
            {beatsForTask.map((b) => (
              <Link key={b.id} to={`/beats/${b.id}`}>
                <Badge
                  variant="outline"
                  className="gap-1.5 hover:bg-accent cursor-pointer"
                >
                  {b.name}
                  <span className="text-muted-foreground font-mono text-[10px]">
                    {formatSchedule(
                      b.scheduleType,
                      b.intervalSeconds,
                      b.cronExpression
                    )}
                  </span>
                  {!b.enabled && (
                    <span className="text-muted-foreground text-[10px]">
                      (disabled)
                    </span>
                  )}
                </Badge>
              </Link>
            ))}
          </div>
        </section>
      )}

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
