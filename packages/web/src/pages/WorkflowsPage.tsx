import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import { WorkflowTable } from "@/components/workflows/workflow-table";
import { ImportWorkflowDialog } from "@/components/workflows/import-workflow-dialog";
import { Button } from "@/components/ui/button";
import { apiGet } from "@/lib/api";
import type { WorkflowSummary } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus } from "lucide-react";

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
        <Button asChild>
          <Link to="/workflows/new">
            <Plus className="mr-2 h-4 w-4" />
            Create Workflow
          </Link>
        </Button>
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
