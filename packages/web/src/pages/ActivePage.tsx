import { PageHeader } from "@/components/page-header";
import { ActiveTasks } from "@/components/tasks/active-tasks";

export default function ActivePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Active Tasks"
        description="Currently running task executions"
      />

      <ActiveTasks />
    </div>
  );
}
