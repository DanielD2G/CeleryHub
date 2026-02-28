const GATEWAY_URL =
  process.env.CELERY_GATEWAY_URL || "http://localhost:8000";

async function gatewayFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${GATEWAY_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Gateway error ${res.status}: ${error}`);
  }
  return res.json() as T;
}

// --- Tasks ---

export interface GatewaySendTaskRequest {
  task_name: string;
  args?: unknown[];
  kwargs?: Record<string, unknown>;
  queue?: string;
  countdown?: number | null;
  eta?: string | null;
  expires?: number | string | null;
  priority?: number | null;
  task_id?: string | null;
}

export interface GatewaySendTaskResponse {
  task_id: string;
  status: string;
}

export async function gatewaySendTask(
  req: GatewaySendTaskRequest
): Promise<GatewaySendTaskResponse> {
  return gatewayFetch("/tasks/send", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export interface GatewayTaskStatus {
  task_id: string;
  status: string;
  result: unknown;
  traceback: string | null;
  date_done: string | null;
  name: string | null;
  worker: string | null;
  runtime: number | null;
}

export async function gatewayGetTaskStatus(
  taskId: string
): Promise<GatewayTaskStatus> {
  return gatewayFetch(`/tasks/${taskId}/status`);
}

export async function gatewayRevokeTask(
  taskId: string,
  terminate = false,
  signal = "SIGTERM"
): Promise<{ task_id: string; revoked: boolean }> {
  return gatewayFetch(`/tasks/${taskId}/revoke`, {
    method: "POST",
    body: JSON.stringify({ terminate, signal }),
  });
}

// --- Active & Registered Tasks ---

export interface GatewayActiveTask {
  id: string;
  name: string;
  args: string | null;
  kwargs: string | null;
  worker: string;
  time_start: number | null;
  acknowledged: boolean;
}

export interface GatewayActiveTasksResponse {
  tasks: GatewayActiveTask[];
  by_worker: Record<string, GatewayActiveTask[]>;
}

export async function gatewayGetActiveTasks(
  refresh = false
): Promise<GatewayActiveTasksResponse> {
  const params = refresh ? "?refresh=true" : "";
  return gatewayFetch(`/tasks/active${params}`);
}

export interface GatewayRegisteredResponse {
  tasks: string[];
  by_worker: Record<string, string[]>;
}

export async function gatewayGetRegisteredTasks(
  refresh = false
): Promise<GatewayRegisteredResponse> {
  const params = refresh ? "?refresh=true" : "";
  return gatewayFetch(`/tasks/registered${params}`);
}

// --- Workers ---

export interface GatewayWorkerInspect {
  active?: Record<string, unknown[]>;
  registered?: Record<string, string[]>;
  reserved?: Record<string, unknown[]>;
  scheduled?: Record<string, unknown[]>;
  stats?: Record<string, Record<string, unknown>>;
  conf?: Record<string, Record<string, unknown>>;
  active_queues?: Record<string, unknown[]>;
  timestamp: string;
  cached: boolean;
}

export async function gatewayInspectWorkers(
  methods = "active,registered,stats,active_queues",
  refresh = false
): Promise<GatewayWorkerInspect> {
  const params = new URLSearchParams({ methods });
  if (refresh) params.set("refresh", "true");
  return gatewayFetch(`/workers/inspect?${params}`);
}

// --- Queues ---

export interface GatewayQueueInfo {
  name: string;
  depth: number;
  consumers: string[];
}

export interface GatewayQueuesResponse {
  queues: GatewayQueueInfo[];
}

export async function gatewayGetQueues(
  refresh = false
): Promise<GatewayQueuesResponse> {
  const params = refresh ? "?refresh=true" : "";
  return gatewayFetch(`/queues${params}`);
}

// --- Control ---

export interface GatewayControlResponse {
  action: string;
  success: boolean;
  responses: Record<string, unknown>;
  errors: Record<string, string>;
}

export async function gatewayControl(
  action: string,
  body: Record<string, unknown> = {}
): Promise<GatewayControlResponse> {
  return gatewayFetch(`/control/${action}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// --- Health ---

export interface GatewayHealth {
  status: string;
  broker_connected: boolean;
  workers_reachable: number;
  version: string;
}

export async function gatewayHealth(): Promise<GatewayHealth> {
  return gatewayFetch("/health");
}
