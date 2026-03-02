import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { WorkflowDetailClient } from "@/components/workflows/workflow-detail-client";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet } from "@/lib/api";
import type { Workflow, WorkflowRun } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  useDocumentTitle(workflow?.name ?? "Workflow Detail");
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(() => {
    if (!id) return;

    Promise.all([
      apiGet<Workflow>(`/api/workflows/${id}`).catch(() => null),
      apiGet<WorkflowRun[]>(`/api/workflows/${id}/runs`).catch(() => []),
    ])
      .then(([workflowData, runsData]) => {
        if (!workflowData) {
          navigate("/workflows", { replace: true });
          return;
        }
        setWorkflow(workflowData);
        setRuns(runsData);
      })
      .catch(() => {
        navigate("/workflows", { replace: true });
      })
      .finally(() => setLoading(false));
  }, [id, navigate]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!workflow) return null;

  return <WorkflowDetailClient workflow={workflow} runs={runs} onRefresh={fetchData} />;
}
