import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { BeatDetailClient } from "@/components/beats/beat-detail-client";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet } from "@/lib/api";
import type { BeatSchedule, BeatRun } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";

export default function BeatDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [beat, setBeat] = useState<BeatSchedule | null>(null);
  useDocumentTitle(beat?.name ?? "Beat Detail");
  const [runs, setRuns] = useState<BeatRun[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(() => {
    if (!id) return;

    Promise.all([
      apiGet<BeatSchedule>(`/api/beats/${id}`).catch(() => null),
      apiGet<BeatRun[]>(`/api/beats/${id}/runs`).catch(() => []),
    ])
      .then(([beatData, runsData]) => {
        if (!beatData) {
          navigate("/beats", { replace: true });
          return;
        }
        setBeat(beatData);
        setRuns(runsData);
      })
      .catch(() => {
        navigate("/beats", { replace: true });
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

  if (!beat) return null;

  return <BeatDetailClient beat={beat} runs={runs} onRefresh={fetchData} />;
}
