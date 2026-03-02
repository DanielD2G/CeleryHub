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

// Beat schedule (periodic task)
export interface BeatSchedule {
  id: string;
  name: string;
  taskNames: string;
  scheduleType: string;
  intervalSeconds: number | null;
  cronExpression: string | null;
  queue: string;
  args: string | null;
  kwargs: string | null;
  enabled: boolean | null;
  maxRunCount: number | null;
  totalRunCount: number;
  lastRunAt: string | null;
  nextRunAt: string | null;
  createdAt: string;
}

// Beat execution log entry
export interface BeatRun {
  id: string;
  scheduledAt: string | null;
  sentAt: string | null;
  taskId: string | null;
  taskName: string | null;
  status: string | null;
  error: string | null;
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
