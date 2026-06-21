import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface WorkflowSettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  description: string;
  setDescription: (v: string) => void;
  scheduleType: "none" | "interval" | "cron";
  setScheduleType: (v: "none" | "interval" | "cron") => void;
  intervalValue: string;
  setIntervalValue: (v: string) => void;
  intervalUnit: string;
  setIntervalUnit: (v: string) => void;
  cronExpression: string;
  setCronExpression: (v: string) => void;
  maxRunCount: string;
  setMaxRunCount: (v: string) => void;
}

export function WorkflowSettingsDrawer({
  open,
  onClose,
  description,
  setDescription,
  scheduleType,
  setScheduleType,
  intervalValue,
  setIntervalValue,
  intervalUnit,
  setIntervalUnit,
  cronExpression,
  setCronExpression,
  maxRunCount,
  setMaxRunCount,
}: WorkflowSettingsDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <SheetContent side="right" className="w-96 sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Workflow Settings</SheetTitle>
          <SheetDescription>
            Configure the workflow description, schedule, and run limits.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="wf-description">Description (optional)</Label>
            <textarea
              id="wf-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what this workflow does..."
              className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              rows={2}
            />
          </div>

          <div className="space-y-2">
            <Label>Schedule</Label>
            <Tabs value={scheduleType} onValueChange={(v) => setScheduleType(v as "none" | "interval" | "cron")}>
              <TabsList>
                <TabsTrigger value="none">None</TabsTrigger>
                <TabsTrigger value="interval">Interval</TabsTrigger>
                <TabsTrigger value="cron">Cron</TabsTrigger>
              </TabsList>
              <TabsContent value="none">
                <p className="mt-2 text-xs text-muted-foreground">
                  Manual trigger only — use &quot;Run Now&quot; to execute
                </p>
              </TabsContent>
              <TabsContent value="interval">
                <div className="mt-2 flex gap-2">
                  <Input
                    type="number"
                    min="1"
                    value={intervalValue}
                    onChange={(e) => setIntervalValue(e.target.value)}
                    className="w-24"
                  />
                  <Select value={intervalUnit} onValueChange={setIntervalUnit}>
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="seconds">Seconds</SelectItem>
                      <SelectItem value="minutes">Minutes</SelectItem>
                      <SelectItem value="hours">Hours</SelectItem>
                      <SelectItem value="days">Days</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>
              <TabsContent value="cron">
                <Input
                  value={cronExpression}
                  onChange={(e) => setCronExpression(e.target.value)}
                  placeholder="* * * * *"
                  className="mt-2 font-mono"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Format: minute hour day-of-month month day-of-week
                </p>
              </TabsContent>
            </Tabs>
          </div>

          <div className="space-y-2">
            <Label htmlFor="wf-max-runs">Max Run Count (optional)</Label>
            <Input
              id="wf-max-runs"
              type="number"
              min="1"
              value={maxRunCount}
              onChange={(e) => setMaxRunCount(e.target.value)}
              placeholder="Unlimited"
              className="w-40"
            />
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
