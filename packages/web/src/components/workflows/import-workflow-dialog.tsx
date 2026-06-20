import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/api";
import { Upload, Loader2 } from "lucide-react";

export function ImportWorkflowDialog({ onImported }: { onImported?: () => void }) {
  const [open, setOpen] = useState(false);
  const [json, setJson] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleImport = async () => {
    setError(null);

    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      setError("Invalid JSON format");
      return;
    }

    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      setError("Expected a JSON object");
      return;
    }

    const obj = parsed as Record<string, unknown>;

    // Reject old steps/taskNames format
    if ("steps" in obj) {
      setError(
        'This JSON uses the old "steps" format and cannot be imported. ' +
          'Please export it from a CeleryHub instance that uses the current "nodes" format.'
      );
      return;
    }
    if (
      Array.isArray(obj.nodes) &&
      obj.nodes.length > 0 &&
      typeof (obj.nodes as Record<string, unknown>[])[0] === "object" &&
      "taskNames" in ((obj.nodes as Record<string, unknown>[])[0] as object)
    ) {
      setError(
        'This JSON uses the old "taskNames" format per node and cannot be imported. ' +
          'Please export it from a CeleryHub instance that uses the current "taskName" (single) format.'
      );
      return;
    }

    // Require nodes array
    if (!Array.isArray(obj.nodes)) {
      setError('Invalid workflow format: expected a "nodes" array.');
      return;
    }

    setSubmitting(true);
    try {
      const result = await apiPost<{ id?: string; error?: string }>(
        "/api/workflows",
        parsed
      );
      if (result.error) {
        setError(result.error);
      } else {
        setOpen(false);
        setJson("");
        onImported?.();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to import workflow");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) {
          setJson("");
          setError(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Upload className="mr-2 h-4 w-4" />
          Import
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import Workflow</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Paste a workflow JSON exported from another CeleryHub instance.
        </p>
        <textarea
          value={json}
          onChange={(e) => setJson(e.target.value)}
          placeholder='{"name": "My Workflow", "scheduleType": "none", "nodes": [...]}'
          className="min-h-[200px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          rows={10}
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleImport} disabled={submitting || !json.trim()}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Import
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
