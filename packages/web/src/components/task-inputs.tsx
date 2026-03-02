import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Plus, Trash2, ChevronDown } from "lucide-react";

// --- Queue selector ---

export function QueueSelector({
  value,
  onChange,
  queues,
}: {
  value: string;
  onChange: (v: string) => void;
  queues: string[];
}) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState(false);

  return (
    <div className="relative">
      {custom ? (
        <div className="flex gap-2">
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="queue name"
            className="h-8 text-sm"
            autoFocus
          />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 text-xs shrink-0"
            onClick={() => {
              setCustom(false);
              if (!value) onChange("celery");
            }}
          >
            Cancel
          </Button>
        </div>
      ) : (
        <button
          type="button"
          className="flex h-8 w-full items-center justify-between rounded-md border bg-background px-3 text-sm hover:bg-accent transition-colors"
          onClick={() => setOpen(!open)}
        >
          <span>{value}</span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      )}

      {open && !custom && (
        <div className="absolute top-full left-0 z-10 mt-1 w-full rounded-md border bg-popover p-1 shadow-md">
          {queues.map((q) => (
            <button
              key={q}
              type="button"
              className={`w-full rounded-sm px-2 py-1.5 text-left text-sm hover:bg-accent ${q === value ? "bg-accent" : ""}`}
              onClick={() => {
                onChange(q);
                setOpen(false);
              }}
            >
              {q}
            </button>
          ))}
          <div className="border-t my-1" />
          <button
            type="button"
            className="flex w-full items-center gap-1.5 rounded-sm px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => {
              setCustom(true);
              setOpen(false);
              onChange("");
            }}
          >
            <Plus className="h-3 w-3" />
            Custom queue
          </button>
        </div>
      )}
    </div>
  );
}

// --- Args list builder ---

export function ArgsBuilder({
  items,
  onChange,
}: {
  items: string[];
  onChange: (items: string[]) => void;
}) {
  const addItem = () => onChange([...items, ""]);
  const removeItem = (i: number) => onChange(items.filter((_, idx) => idx !== i));
  const updateItem = (i: number, val: string) =>
    onChange(items.map((v, idx) => (idx === i ? val : v)));

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            value={item}
            onChange={(e) => updateItem(i, e.target.value)}
            placeholder={`arg ${i}`}
            className="h-8 text-sm font-mono"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
            onClick={() => removeItem(i)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-full"
        onClick={addItem}
      >
        <Plus className="mr-1.5 h-3 w-3" />
        Add argument
      </Button>
    </div>
  );
}

// --- Kwargs key-value builder ---

export function KwargsBuilder({
  pairs,
  onChange,
}: {
  pairs: [string, string][];
  onChange: (pairs: [string, string][]) => void;
}) {
  const addPair = () => onChange([...pairs, ["", ""]]);
  const removePair = (i: number) => onChange(pairs.filter((_, idx) => idx !== i));
  const updateKey = (i: number, key: string) =>
    onChange(pairs.map((p, idx) => (idx === i ? [key, p[1]] : p)));
  const updateValue = (i: number, val: string) =>
    onChange(pairs.map((p, idx) => (idx === i ? [p[0], val] : p)));

  return (
    <div className="space-y-2">
      {pairs.map(([key, val], i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            value={key}
            onChange={(e) => updateKey(i, e.target.value)}
            placeholder="key"
            className="h-8 text-sm font-mono w-2/5"
          />
          <Input
            value={val}
            onChange={(e) => updateValue(i, e.target.value)}
            placeholder="value"
            className="h-8 text-sm font-mono flex-1"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
            onClick={() => removePair(i)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-full"
        onClick={addPair}
      >
        <Plus className="mr-1.5 h-3 w-3" />
        Add parameter
      </Button>
    </div>
  );
}

// --- Serialize helpers ---

export function serializeArgs(items: string[]): string {
  const parsed = items.map((v) => {
    const trimmed = v.trim();
    if (!trimmed) return null;
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed; // treat as string
    }
  }).filter((v) => v !== null);
  return JSON.stringify(parsed);
}

export function serializeKwargs(pairs: [string, string][]): string {
  const obj: Record<string, unknown> = {};
  for (const [key, val] of pairs) {
    const k = key.trim();
    if (!k) continue;
    const v = val.trim();
    try {
      obj[k] = JSON.parse(v);
    } catch {
      obj[k] = v; // treat as string
    }
  }
  return JSON.stringify(obj);
}

// --- Parse helpers (JSON string → builder state) ---

export function parseArgsToItems(jsonStr: string): string[] {
  try {
    const arr = JSON.parse(jsonStr);
    if (!Array.isArray(arr)) return [];
    return arr.map((v) => (typeof v === "string" ? v : JSON.stringify(v)));
  } catch {
    return [];
  }
}

export function parseKwargsToPairs(jsonStr: string): [string, string][] {
  try {
    const obj = JSON.parse(jsonStr);
    if (typeof obj !== "object" || Array.isArray(obj) || obj === null) return [];
    return Object.entries(obj).map(([k, v]) => [
      k,
      typeof v === "string" ? v : JSON.stringify(v),
    ]);
  } catch {
    return [];
  }
}
