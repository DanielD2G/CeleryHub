import { toast } from "sonner";
import { useState, useEffect } from "react";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import { QueueCard } from "@/components/queues/queue-card";
import { apiGet, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

interface QueueDetails {
  queueNames: string[];
  depths: Record<string, number>;
  pending: Record<
    string,
    { taskId: string; taskName: string; enqueuedAt: string }[]
  >;
}

export default function QueuesPage() {
  useDocumentTitle("Queues");
  const [data, setData] = useState<QueueDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const fetchData = async () => {
    try {
      setData(await apiGet<QueueDetails>("/api/queues"));
      setLoadError(false);
    } catch {
      setLoadError(true);
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleRefresh = () => {
    setLoading(true);
    fetchData();
  };

  const [purging, setPurging] = useState(false);
  const handlePurge = async () => {
    if (
      !confirm(
        "Purge ALL queues? Every pending (not yet started) task will be permanently discarded."
      )
    ) {
      return;
    }
    setPurging(true);
    try {
      const r = await apiPost<{ responses?: { purged?: number } }>(
        "/api/control/purge"
      );
      toast.success(`Purged ${r.responses?.purged ?? 0} pending task(s)`);
      fetchData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Purge failed");
    } finally {
      setPurging(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Queues" description="Queue depths and pending tasks">
        <Button
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={handleRefresh}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
        <Button
          variant="destructive"
          size="sm"
          disabled={purging}
          onClick={handlePurge}
        >
          Purge all queues
        </Button>
      </PageHeader>

      {loadError && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          Failed to refresh queues — showing last known data.
        </div>
      )}

      {loading && !data ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : data ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data.queueNames.map((q) => (
            <QueueCard
              key={q}
              name={q}
              depth={data.depths[q] ?? 0}
              pending={data.pending[q] ?? []}
            />
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground">Failed to load queue data.</p>
      )}
    </div>
  );
}
