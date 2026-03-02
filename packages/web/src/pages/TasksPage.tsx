import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import { TaskCards } from "@/components/tasks/task-cards";

export default function TasksPage() {
  useDocumentTitle("Tasks");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tasks"
        description="Select a task to send, monitor or review executions"
      />

      <TaskCards />
    </div>
  );
}
