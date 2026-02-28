import { PageHeader } from "@/components/page-header";
import { StatsCards } from "@/components/dashboard/stats-cards";
import { LiveFeed } from "@/components/dashboard/live-feed";
import { TaskStatusChart } from "@/components/dashboard/task-status-chart";
import { TopTasksChart } from "@/components/dashboard/top-tasks-chart";
import { EventTimelineChart } from "@/components/dashboard/event-timeline-chart";
import {
  ActiveByWorkerChart,
  ActiveByTypeChart,
} from "@/components/dashboard/active-breakdown-charts";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Real-time overview of your Celery cluster"
      />

      {/* KPIs with embedded sparklines */}
      <StatsCards />

      {/* Task Analysis */}
      <div className="grid gap-4 lg:grid-cols-2">
        <TaskStatusChart />
        <TopTasksChart />
      </div>

      {/* Live Activity */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ActiveByWorkerChart />
        <ActiveByTypeChart />
      </div>

      {/* Event Stream */}
      <div className="grid gap-4 lg:grid-cols-2">
        <EventTimelineChart />
        <LiveFeed />
      </div>
    </div>
  );
}
