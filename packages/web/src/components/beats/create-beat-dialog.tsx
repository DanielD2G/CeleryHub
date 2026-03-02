import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { BeatForm } from "./beat-form";
import { apiPost } from "@/lib/api";
import { Plus } from "lucide-react";

export function CreateBeatDialog({ onCreated }: { onCreated?: () => void }) {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Create Beat
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Beat Schedule</DialogTitle>
        </DialogHeader>
        <BeatForm
          onSubmit={async (input) => {
            try {
              const result = await apiPost<{ id?: string; error?: string }>("/api/beats", input);
              if (!result.error && result.id) {
                setOpen(false);
                onCreated?.();
              }
              return result;
            } catch (e) {
              return { error: e instanceof Error ? e.message : "Failed to create" };
            }
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
