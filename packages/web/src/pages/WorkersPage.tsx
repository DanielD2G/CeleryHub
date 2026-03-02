import { useCeleryWorkers } from "@/hooks/use-celery";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import { WorkerCard } from "@/components/workers/worker-card";

export default function WorkersPage() {
  useDocumentTitle("Workers");
  const workers = useCeleryWorkers();
  const workerList = Array.from(workers.values()).sort((a, b) =>
    a.status === b.status
      ? a.hostname.localeCompare(b.hostname)
      : a.status === "online"
        ? -1
        : 1
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workers"
        description={`${workerList.filter((w) => w.status === "online").length} online of ${workerList.length} total`}
      />

      {workerList.length === 0 ? (
        <p className="text-muted-foreground">
          No workers discovered yet. Waiting for events...
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workerList.map((worker) => (
            <WorkerCard key={worker.hostname} worker={worker} />
          ))}
        </div>
      )}
    </div>
  );
}
