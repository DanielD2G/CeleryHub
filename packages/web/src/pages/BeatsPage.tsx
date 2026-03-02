import { useState, useEffect } from "react";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { PageHeader } from "@/components/page-header";
import { BeatTable } from "@/components/beats/beat-table";
import { CreateBeatDialog } from "@/components/beats/create-beat-dialog";
import { apiGet } from "@/lib/api";
import type { BeatSchedule } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";

export default function BeatsPage() {
  useDocumentTitle("Beats");
  const [beats, setBeats] = useState<BeatSchedule[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchBeats = async () => {
    try {
      setBeats(await apiGet<BeatSchedule[]>("/api/beats"));
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
