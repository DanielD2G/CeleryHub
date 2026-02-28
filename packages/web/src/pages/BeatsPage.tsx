import { useState, useEffect } from "react";
import { PageHeader } from "@/components/page-header";
import { BeatTable } from "@/components/beats/beat-table";
import { CreateBeatDialog } from "@/components/beats/create-beat-dialog";
import { Skeleton } from "@/components/ui/skeleton";

interface BeatSchedule {
  id: string;
  name: string;
  taskNames: string;
  scheduleType: string;
  intervalSeconds: number | null;
  cronExpression: string | null;
  queue: string;
  enabled: boolean | null;
  lastRunAt: string | null;
  nextRunAt: string | null;
  totalRunCount: number;
  maxRunCount: number | null;
}

export default function BeatsPage() {
  const [beats, setBeats] = useState<BeatSchedule[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchBeats = async () => {
    try {
      const res = await fetch("/api/beats");
      if (res.ok) {
        setBeats(await res.json());
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBeats();
    const id = setInterval(fetchBeats, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader title="Beats" description="Manage periodic task schedules">
        <CreateBeatDialog onCreated={fetchBeats} />
      </PageHeader>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : (
        <BeatTable beats={beats} onRefresh={fetchBeats} />
      )}
    </div>
  );
}
