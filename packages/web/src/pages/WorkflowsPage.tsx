import { useState, useEffect, useCallback } from "react";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import { WorkflowTable } from "@/components/workflows/workflow-table";
import { CreateWorkflowDialog } from "@/components/workflows/create-workflow-dialog";
import { ImportWorkflowDialog } from "@/components/workflows/import-workflow-dialog";
import { apiGet } from "@/lib/api";
import type { WorkflowSummary } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";

export default function WorkflowsPage() {
  useDocumentTitle("Workflows");
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchWorkflows = useCallback(async () => {
    try {
      setWorkflows(await apiGet<WorkflowSummary[]>("/api/workflows"));
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorkflows();
    const id = setInterval(fetchWorkflows, 5000);
    return () => clearInterval(id);
  }, [fetchWorkflows]);

  return (
    <div className="space-y-6">
      <PageHeader title="Workflows" description="Orchestrate multi-step task pipelines">
        <ImportWorkflowDialog onImported={fetchWorkflows} />
        <CreateWorkflowDialog onCreated={fetchWorkflows} />
      </PageHeader>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : (
        <WorkflowTable workflows={workflows} onRefresh={fetchWorkflows} />
      )}
    </div>
  );
}
