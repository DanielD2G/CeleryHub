import { useState, useEffect } from "react";
import { PageHeader } from "@/components/page-header";
import { QueueCard } from "@/components/queues/queue-card";
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
  const [data, setData] = useState<QueueDetails | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const res = await fetch("/api/queues");
      if (res.ok) {
        setData(await res.json());
      }
    } catch {
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
      </PageHeader>

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
