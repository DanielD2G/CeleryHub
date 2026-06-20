// Base Celery event
export interface CeleryEvent {
  type: string;
  hostname: string;
  timestamp: number;
  pid: number;
  clock: number;
}

// Worker events
export interface WorkerOnlineEvent extends CeleryEvent {
  type: "worker-online";
  sw_ver: string;
  sw_sys: string;
}

export interface WorkerHeartbeatEvent extends CeleryEvent {
  type: "worker-heartbeat";
  active: number;
  processed: number;
  freq: number;
}

export interface WorkerOfflineEvent extends CeleryEvent {
  type: "worker-offline";
}

// Task events
export interface TaskSentEvent extends CeleryEvent {
  type: "task-sent";
  uuid: string;
  name: string;
  args: string;
  kwargs: string;
  queue: string;
}

export interface TaskReceivedEvent extends CeleryEvent {
  type: "task-received";
  uuid: string;
  name: string;
}

export interface TaskStartedEvent extends CeleryEvent {
  type: "task-started";
  uuid: string;
}

export interface TaskSucceededEvent extends CeleryEvent {
  type: "task-succeeded";
  uuid: string;
  result: string;
  runtime: number;
}

export interface TaskFailedEvent extends CeleryEvent {
  type: "task-failed";
  uuid: string;
  exception: string;
  traceback: string;
}

export interface TaskRetriedEvent extends CeleryEvent {
  type: "task-retried";
  uuid: string;
  exception: string;
}

export interface TaskRevokedEvent extends CeleryEvent {
  type: "task-revoked";
  uuid: string;
  terminated: boolean;
  signum: string;
}

export type CeleryWorkerEvent =
  | WorkerOnlineEvent
  | WorkerHeartbeatEvent
  | WorkerOfflineEvent;

export type CeleryTaskEvent =
  | TaskSentEvent
  | TaskReceivedEvent
  | TaskStartedEvent
  | TaskSucceededEvent
  | TaskFailedEvent
  | TaskRetriedEvent
  | TaskRevokedEvent;

export type AnyCeleryEvent = CeleryWorkerEvent | CeleryTaskEvent;

// Accumulated state
export interface WorkerState {
  hostname: string;
  status: "online" | "offline";
  lastHeartbeat: number;
  active: number;
  processed: number;
  swVer: string;
  swSys: string;
  pid: number;
  // Enriched from celery-gateway inspect
  registeredTasks?: string[];
  activeQueues?: string[];
  stats?: Record<string, unknown>;
  reservedCount?: number;
  scheduledCount?: number;
}

export interface ActiveTask {
  taskId: string;
  name: string;
  worker: string;
  startedAt: number;
  status: "sent" | "received" | "started";
  args?: string;
  kwargs?: string;
}

export interface TaskResult {
  taskId: string;
  status: string;
  result: unknown;
  traceback: string | null;
  dateDone: string;
  name?: string;
  worker?: string;
  runtime?: number;
  args?: string;
  kwargs?: string;
}

// Full task record built from events when tasks complete
export interface CompletedTaskMeta {
  taskId: string;
  name: string;
  worker: string;
  status: "SUCCESS" | "FAILURE" | "REVOKED" | "RETRIED";
  runtime?: number;
  result?: string;
  exception?: string;
  traceback?: string;
  args?: string;
  kwargs?: string;
  completedAt: number;
}

// Workflow types
export interface WorkflowNode {
  id: string;
  label: string;
  taskName: string;
  args: string | null;
  kwargs: string | null;
  queue: string | null;
  dependsOn: string; // JSON-encoded string[] of node IDs — parse with parseJson<string[]>(node.dependsOn, [])
  condition: string;
  timeoutSeconds: number | null;
  /** Raw columns returned by the API; null means no saved position */
  positionX: number | null;
  positionY: number | null;
  /** Convenience form preferred by nodesToFlow; set when caller has already merged positionX/Y */
  position?: { x: number; y: number } | null;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  scheduleType: string;
  intervalSeconds: number | null;
  cronExpression: string | null;
  enabled: boolean;
  maxRunCount: number | null;
  totalRunCount: number;
  lastRunAt: string | null;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
  nodes: WorkflowNode[];
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string | null;
  scheduleType: string;
  intervalSeconds: number | null;
  cronExpression: string | null;
  enabled: boolean;
  maxRunCount: number | null;
  totalRunCount: number;
  lastRunAt: string | null;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
  nodeCount: number;
}

export interface NodeRun {
  id: string;
  nodeId: string;
  label: string;
  taskName: string;
  celeryTaskId: string | null;
  status: string;
  error: string | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface WorkflowRun {
  id: string;
  workflowId: string;
  status: string;
  trigger: string;
  startedAt: string;
  finishedAt: string | null;
}

export interface WorkflowRunDetail {
  id: string;
  workflowId: string;
  status: string;
  trigger: string;
  startedAt: string;
  finishedAt: string | null;
  nodeRuns: NodeRun[];
}

// Event provider state
export interface CeleryState {
  workers: Map<string, WorkerState>;
  activeTasks: Map<string, ActiveTask>;
  completedTasks: Map<string, CompletedTaskMeta>;
  recentEvents: CeleryEvent[];
  knownTaskNames: Set<string>;
  knownQueues: Set<string>;
  connected: boolean;
}
