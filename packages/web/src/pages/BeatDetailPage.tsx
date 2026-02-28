import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { BeatDetailClient } from "@/components/beats/beat-detail-client";
import { Skeleton } from "@/components/ui/skeleton";

interface BeatSchedule {
  id: string;
  name: string;
  taskNames: string;
  scheduleType: string;
  intervalSeconds: number | null;
  cronExpression: string | null;
  queue: string;
  args: string | null;
  kwargs: string | null;
  enabled: boolean | null;
  maxRunCount: number | null;
  totalRunCount: number;
  lastRunAt: string | null;
  nextRunAt: string | null;
  createdAt: string;
}

interface BeatRun {
  id: string;
  scheduledAt: string | null;
  sentAt: string | null;
  taskId: string | null;
  taskName: string | null;
  status: string | null;
  error: string | null;
}

export default function BeatDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [beat, setBeat] = useState<BeatSchedule | null>(null);
  const [runs, setRuns] = useState<BeatRun[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(() => {
    if (!id) return;

    Promise.all([
      fetch(`/api/beats/${id}`).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/beats/${id}/runs`).then((r) => (r.ok ? r.json() : [])),
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
