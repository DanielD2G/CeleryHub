import { useCallback, useEffect, useState } from "react";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Bell, Plus, Send, Trash2 } from "lucide-react";
import { formatWorkflowDate } from "@/lib/workflow-utils";

interface Channel {
  id: string;
  name: string;
  kind: string;
  config: Record<string, string>;
  enabled: boolean;
  rules: Record<string, { enabled: boolean }>;
  createdAt: string;
}

interface AlertEventItem {
  id: string;
  rule: string;
  subject: string;
  message: string;
  delivered: boolean;
  error: string | null;
  firedAt: string;
}

const RULE_LABELS: Record<string, string> = {
  workflow_failed: "Workflow run failed",
  dead_mans_switch: "Workflow missed its success window",
  worker_offline: "Worker count dropped",
  persister_lag: "Event persister behind",
  anomaly: "Task anomaly (slow run / failure streak)",
};

export default function AlertsPage() {
  useDocumentTitle("Alerts");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [events, setEvents] = useState<AlertEventItem[]>([]);
  const [rules, setRules] = useState<string[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  // form state
  const [name, setName] = useState("");
  const [kind, setKind] = useState("webhook");
  const [url, setUrl] = useState("");
  const [botToken, setBotToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [formRules, setFormRules] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    apiGet<Channel[]>("/api/alerts/channels").then(setChannels).catch(() => {});
    apiGet<AlertEventItem[]>("/api/alerts/events?limit=50")
      .then(setEvents)
      .catch(() => {});
    apiGet<string[]>("/api/alerts/rules").then(setRules).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const submit = async () => {
    setError(null);
    const config =
      kind === "telegram" ? { botToken, chatId } : { url };
    const rulesBody = Object.fromEntries(
      Object.entries(formRules)
        .filter(([, v]) => v)
        .map(([k]) => [k, { enabled: true }])
    );
    try {
      await apiPost("/api/alerts/channels", {
        name,
        kind,
        config,
        enabled: true,
        rules: rulesBody,
      });
      setShowForm(false);
      setName("");
      setUrl("");
      setBotToken("");
      setChatId("");
      setFormRules({});
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create channel");
    }
  };

  const toggleChannel = async (c: Channel) => {
    await apiPut(`/api/alerts/channels/${c.id}`, {
      name: c.name,
      kind: c.kind,
      config: c.config,
      enabled: !c.enabled,
      rules: c.rules,
    });
    refresh();
  };

  const removeChannel = async (c: Channel) => {
    await apiDelete(`/api/alerts/channels/${c.id}`);
    refresh();
  };

  const testChannel = async (c: Channel) => {
    setTestResult((p) => ({ ...p, [c.id]: "…" }));
    try {
      const r = await apiPost<{ delivered: boolean; error: string | null }>(
        `/api/alerts/channels/${c.id}/test`
      );
      setTestResult((p) => ({
        ...p,
        [c.id]: r.delivered ? "delivered ✓" : `failed: ${r.error}`,
      }));
    } catch {
      setTestResult((p) => ({ ...p, [c.id]: "request failed" }));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Alerts</h2>
          <p className="text-sm text-muted-foreground">
            Outbound notifications: failed workflows, missed schedules, offline
            workers, anomalies.
          </p>
        </div>
        <Button onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Channel
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">New channel</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="ops-discord" />
              </div>
              <div className="space-y-1.5">
                <Label>Kind</Label>
                <Select value={kind} onValueChange={setKind}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="webhook">Generic webhook</SelectItem>
                    <SelectItem value="discord">Discord webhook</SelectItem>
                    <SelectItem value="telegram">Telegram bot</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {kind !== "telegram" ? (
                <div className="space-y-1.5 md:col-span-2">
                  <Label>Webhook URL</Label>
                  <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label>Bot token</Label>
                    <Input value={botToken} onChange={(e) => setBotToken(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Chat ID</Label>
                    <Input value={chatId} onChange={(e) => setChatId(e.target.value)} />
                  </div>
                </>
              )}
            </div>
            <div className="space-y-2">
              <Label>Rules</Label>
              {rules.map((r) => (
                <div key={r} className="flex items-center gap-2">
                  <Switch
                    checked={!!formRules[r]}
                    onCheckedChange={(v) => setFormRules((p) => ({ ...p, [r]: v }))}
                  />
                  <span className="text-sm">{RULE_LABELS[r] ?? r}</span>
                </div>
              ))}
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="flex gap-2">
              <Button onClick={submit} disabled={!name}>Create</Button>
              <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {channels.length === 0 && !showForm ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12 text-center">
          <Bell className="mb-2 h-8 w-8 text-muted-foreground" />
          <p className="text-muted-foreground">
            No channels yet — alerts are detected but go nowhere.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {channels.map((c) => (
            <Card key={c.id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{c.name}</CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{c.kind}</Badge>
                    <Switch checked={c.enabled} onCheckedChange={() => toggleChannel(c)} />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(c.rules)
                    .filter(([, v]) => v.enabled)
                    .map(([r]) => (
                      <Badge key={r} variant="outline" className="text-xs">
                        {RULE_LABELS[r] ?? r}
                      </Badge>
                    ))}
                  {Object.values(c.rules).every((v) => !v.enabled) && (
                    <span className="text-xs text-muted-foreground">no rules enabled</span>
                  )}
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <Button size="sm" variant="outline" onClick={() => testChannel(c)}>
                    <Send className="mr-1.5 h-3.5 w-3.5" />
                    Test
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => removeChannel(c)}>
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                  {testResult[c.id] && (
                    <span className="text-xs text-muted-foreground">{testResult[c.id]}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <h3 className="text-lg font-semibold">Recent alerts</h3>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing fired yet.</p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Rule</TableHead>
                  <TableHead>Message</TableHead>
                  <TableHead>Delivered</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatWorkflowDate(e.firedAt)}
                    </TableCell>
                    <TableCell><Badge variant="outline" className="text-xs">{e.rule}</Badge></TableCell>
                    <TableCell className="max-w-md truncate text-sm">{e.message}</TableCell>
                    <TableCell>
                      {e.delivered ? (
                        <Badge variant="secondary" className="text-emerald-500">sent</Badge>
                      ) : (
                        <Badge variant="destructive">{e.error ? "failed" : "no"}</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
