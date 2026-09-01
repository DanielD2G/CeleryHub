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
  const [loadError, setLoadError] = useState(false);

  const fetchWorkflows = useCallback(async () => {
    try {
      setWorkflows(await apiGet<WorkflowSummary[]>("/api/workflows"));
      setLoadError(false);
    } catch {
      setLoadError(true);
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
        <>
          {loadError && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              Failed to load workflows — showing last known data. Retrying
              automatically.
            </div>
          )}
          <WorkflowTable workflows={workflows} onRefresh={fetchWorkflows} />
        </>
      )}
    </div>
  );
}
