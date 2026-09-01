import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useDocumentTitle } from "@/hooks/use-document-title";
import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
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
import { Bell, Pencil, Plus, Send, Trash2 } from "lucide-react";
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

interface FormState {
  id: string | null; // null = creating
  name: string;
  kind: string;
  url: string;
  botToken: string;
  chatId: string;
  enabled: boolean;
  rules: Record<string, boolean>;
}

const EMPTY_FORM: FormState = {
  id: null,
  name: "",
  kind: "webhook",
  url: "",
  botToken: "",
  chatId: "",
  enabled: true,
  rules: {},
};

export default function AlertsPage() {
  useDocumentTitle("Alerts");
  const [channels, setChannels] = useState<Channel[] | null>(null);
  const [events, setEvents] = useState<AlertEventItem[]>([]);
  const [allRules, setAllRules] = useState<string[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  const refresh = useCallback(() => {
    Promise.all([
      apiGet<Channel[]>("/api/alerts/channels"),
      apiGet<AlertEventItem[]>("/api/alerts/events?limit=50"),
      apiGet<string[]>("/api/alerts/rules"),
    ])
      .then(([chs, evs, rules]) => {
        setChannels(chs);
        setEvents(evs);
        setAllRules(rules);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const openCreate = () => setForm({ ...EMPTY_FORM });

  const openEdit = (c: Channel) =>
    setForm({
      id: c.id,
      name: c.name,
      kind: c.kind,
      url: c.config.url ?? "",
      botToken: c.config.botToken ?? "",
      chatId: c.config.chatId ?? "",
      enabled: c.enabled,
      rules: Object.fromEntries(
        Object.entries(c.rules).map(([k, v]) => [k, !!v.enabled])
      ),
    });

  const submit = async () => {
    if (!form || saving) return;
    setSaving(true);
    const config =
      form.kind === "telegram"
        ? { botToken: form.botToken, chatId: form.chatId }
        : { url: form.url };
    const body = {
      name: form.name,
      kind: form.kind,
      config,
      enabled: form.enabled,
      rules: Object.fromEntries(
        Object.entries(form.rules)
          .filter(([, v]) => v)
          .map(([k]) => [k, { enabled: true }])
      ),
    };
    try {
      if (form.id) {
        await apiPut(`/api/alerts/channels/${form.id}`, body);
        toast.success("Channel updated");
      } else {
        await apiPost("/api/alerts/channels", body);
        toast.success("Channel created");
      }
      setForm(null);
      refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save channel");
    } finally {
      setSaving(false);
    }
  };

  const toggleChannel = async (c: Channel) => {
    try {
      await apiPut(`/api/alerts/channels/${c.id}`, {
        name: c.name,
        kind: c.kind,
        config: c.config,
        enabled: !c.enabled,
        rules: c.rules,
      });
      refresh();
    } catch {
      toast.error("Toggle failed — nothing was changed");
    }
  };

  const removeChannel = async (c: Channel) => {
    if (!confirm(`Delete channel "${c.name}"? Alerts will stop going there.`)) {
      return;
    }
    try {
      await apiDelete(`/api/alerts/channels/${c.id}`);
      toast.success("Channel deleted");
      refresh();
    } catch {
      toast.error("Delete failed");
    }
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
      <PageHeader
        title="Alerts"
        description="Outbound notifications: failed workflows, missed schedules, offline workers, anomalies."
      >
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Channel
        </Button>
      </PageHeader>

      {form && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {form.id ? `Edit channel — ${form.name}` : "New channel"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="ch-name">Name</Label>
                <Input
                  id="ch-name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="ops-discord"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Kind</Label>
                <Select
                  value={form.kind}
                  onValueChange={(v) => setForm({ ...form, kind: v })}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="webhook">Generic webhook</SelectItem>
                    <SelectItem value="discord">Discord webhook</SelectItem>
                    <SelectItem value="telegram">Telegram bot</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {form.kind !== "telegram" ? (
                <div className="space-y-1.5 md:col-span-2">
                  <Label htmlFor="ch-url">Webhook URL</Label>
                  <Input
                    id="ch-url"
                    value={form.url}
                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                    placeholder="https://…"
                    autoComplete="off"
                  />
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="ch-token">Bot token</Label>
                    <Input
                      id="ch-token"
                      type="password"
                      autoComplete="off"
                      value={form.botToken}
                      onChange={(e) =>
                        setForm({ ...form, botToken: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="ch-chat">Chat ID</Label>
                    <Input
                      id="ch-chat"
                      value={form.chatId}
                      onChange={(e) =>
                        setForm({ ...form, chatId: e.target.value })
                      }
                    />
                  </div>
                </>
              )}
            </div>
            <div className="space-y-2">
              <Label>Rules</Label>
              {allRules.map((r) => (
                <div key={r} className="flex items-center gap-2">
                  <Switch
                    id={`rule-${r}`}
                    checked={!!form.rules[r]}
                    onCheckedChange={(v) =>
                      setForm({ ...form, rules: { ...form.rules, [r]: v } })
                    }
                  />
                  <Label htmlFor={`rule-${r}`} className="font-normal">
                    {RULE_LABELS[r] ?? r}
                  </Label>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button onClick={submit} disabled={!form.name || saving}>
                {form.id ? "Save" : "Create"}
              </Button>
              <Button variant="outline" onClick={() => setForm(null)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loadError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load alert configuration — the API is unreachable. Retrying
          automatically.
        </div>
      ) : channels === null ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-36" />
          <Skeleton className="h-36" />
        </div>
      ) : channels.length === 0 && !form ? (
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
                    <Switch
                      checked={c.enabled}
                      onCheckedChange={() => toggleChannel(c)}
                      aria-label={`Enable channel ${c.name}`}
                    />
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
                    <span className="text-xs text-muted-foreground">
                      no rules enabled
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <Button size="sm" variant="outline" onClick={() => testChannel(c)}>
                    <Send className="mr-1.5 h-3.5 w-3.5" />
                    Test
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openEdit(c)}
                    aria-label={`Edit channel ${c.name}`}
                  >
                    <Pencil className="mr-1.5 h-3.5 w-3.5" />
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => removeChannel(c)}
                    aria-label={`Delete channel ${c.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                  {testResult[c.id] && (
                    <span className="text-xs text-muted-foreground">
                      {testResult[c.id]}
                    </span>
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
                    <TableCell>
                      <Badge variant="outline" className="text-xs">{e.rule}</Badge>
                    </TableCell>
                    <TableCell className="max-w-md truncate text-sm">
                      {e.message}
                    </TableCell>
                    <TableCell>
                      {e.delivered ? (
                        <Badge>sent</Badge>
                      ) : (
                        <Badge variant="destructive">
                          {e.error ? "failed" : "no"}
                        </Badge>
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
