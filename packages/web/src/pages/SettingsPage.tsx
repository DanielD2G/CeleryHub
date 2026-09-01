import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet, apiPut } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

export default function SettingsPage() {
  useDocumentTitle("Settings");
  const [retention, setRetention] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    apiGet<{ retentionDays: number }>("/api/settings/retention")
      .then((r) => setRetention(String(r.retentionDays)))
      .catch(() => setLoadError(true));
  }, []);

  const save = async () => {
    const days = parseInt(retention ?? "", 10);
    if (!Number.isFinite(days) || days < 1) {
      toast.error("Retention must be a positive number of days");
      return;
    }
    setSaving(true);
    try {
      const r = await apiPut<{ retentionDays: number }>(
        "/api/settings/retention",
        { retentionDays: days }
      );
      setRetention(String(r.retentionDays));
      toast.success(`Event retention set to ${r.retentionDays} days`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Gateway configuration" />

      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle className="text-base">Event retention</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Celery events older than this are dropped daily (their partitions
            are removed). Grouped exception history is kept separately and is
            not affected.
          </p>
          {loadError ? (
            <p className="text-sm text-destructive">
              Failed to load current value.
            </p>
          ) : retention === null ? (
            <Skeleton className="h-9 w-40" />
          ) : (
            <div className="flex items-end gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="retention-days">Days</Label>
                <Input
                  id="retention-days"
                  type="number"
                  min={1}
                  className="w-32"
                  value={retention}
                  onChange={(e) => setRetention(e.target.value)}
                />
              </div>
              <Button onClick={save} disabled={saving}>
                Save
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
