import type { ActiveTask, CompletedTaskMeta } from "./types.js";
import type { GatewayWorkerInspect } from "./celery-gateway.js";
import { gatewayGetActiveTasks } from "./celery-gateway.js";
import { getActiveTasks, getHistoricalTasks, getKnownTaskNames, getQueueLengths, getPendingTasks } from "./celery.js";
import { gatewayGetQueues, gatewayGetRegisteredTasks, gatewayInspectWorkers } from "./celery-gateway.js";
import { getRedis } from "./redis.js";

// ---------------------------------------------------------------------------
// Generic cache infrastructure
// ---------------------------------------------------------------------------

interface CacheEntry<T = unknown> {
  data: T;
  updatedAt: number;
  ttlMs: number;
  timer: ReturnType<typeof setInterval> | null;
  inflight: Promise<T> | null;
  refreshFn: () => Promise<T>;
}

class CeleryCache {
  private entries = new Map<string, CacheEntry>();

  constructor() {
    this.register("active-tasks", 2_000, refreshActiveTasks);
    this.register("queue-depths", 30_000, refreshQueueDepths);
    this.register("task-history", 10_000, refreshTaskHistory);
    this.register("worker-inspect", 15_000, refreshWorkerInspect);
    this.register("registered-tasks", 60_000, refreshRegisteredTasks);
    this.register("queue-details", 5_000, refreshQueueDetails);
  }

  private register<T>(
    key: string,
    ttlMs: number,
    refreshFn: () => Promise<T>,
  ): void {
    this.entries.set(key, {
      data: undefined as T,
      updatedAt: 0,
      ttlMs,
      timer: null,
      inflight: null,
      refreshFn,
    } as CacheEntry);
  }

  /**
   * Read cached data. First call awaits the initial fetch and starts the
   * background timer. Subsequent calls return instantly from memory.
   */
  async get<T>(key: string): Promise<T> {
    const entry = this.entries.get(key) as CacheEntry<T> | undefined;
    if (!entry) throw new Error(`Unknown cache key: ${key}`);

    // Cold start – first access
    if (entry.updatedAt === 0) {
      await this.refresh(key);
      this.startTimer(key);
    }

    return entry.data;
  }

  /**
   * Execute the refresh function. Deduplicates concurrent calls and serves
   * stale data on error.
   */
  private async refresh(key: string): Promise<void> {
    const entry = this.entries.get(key)!;

    if (entry.inflight) {
      await entry.inflight.catch(() => {});
      return;
    }

    const promise = entry.refreshFn();
    entry.inflight = promise;

    try {
      const data = await promise;
      entry.data = data;
      entry.updatedAt = Date.now();
    } catch (err) {
      console.warn(`[cache] refresh failed for "${key}":`, err);
    } finally {
      entry.inflight = null;
    }
  }

  private startTimer(key: string): void {
    const entry = this.entries.get(key)!;
    if (entry.timer) return;

    entry.timer = setInterval(() => {
      this.refresh(key).catch(() => {});
    }, entry.ttlMs);

    // Don't keep the Node process alive just for cache timers
    if (entry.timer && typeof entry.timer === "object" && "unref" in entry.timer) {
      entry.timer.unref();
    }
  }
}

// ---------------------------------------------------------------------------
// Singleton (simple module-level variable)
// ---------------------------------------------------------------------------

let cache: CeleryCache | null = null;

function getCache(): CeleryCache {
  if (!cache) cache = new CeleryCache();
  return cache;
}

// ---------------------------------------------------------------------------
// Refresh functions – absorb the gateway-first / Redis-fallback logic
// ---------------------------------------------------------------------------

async function refreshActiveTasks(): Promise<ActiveTask[]> {
  try {
    const { tasks } = await gatewayGetActiveTasks();
    return tasks.map((t) => ({
      taskId: t.id,
      name: t.name,
      worker: t.worker,
      startedAt: t.time_start ?? Date.now() / 1000,
      status: t.acknowledged ? ("started" as const) : ("received" as const),
      args: t.args ?? undefined,
      kwargs: t.kwargs ?? undefined,
    }));
  } catch {
    try {
      return await getActiveTasks();
    } catch {
      return [];
    }
  }
}

async function refreshQueueDepths(): Promise<Record<string, number>> {
  try {
    const { queues } = await gatewayGetQueues();
    const result: Record<string, number> = {};
    for (const q of queues) {
      result[q.name] = q.depth;
    }
    return result;
  } catch {
    try {
      const depths = await getQueueLengths(["celery"]);
      const result: Record<string, number> = {};
      for (const [key, value] of depths) {
        result[key] = value;
      }
      return result;
    } catch {
      return { celery: 0 };
    }
  }
}

async function refreshTaskHistory(): Promise<CompletedTaskMeta[]> {
  try {
    const tasks = await getHistoricalTasks(50);

    // Backfill known task names (side effect preserved from original route)
    const names = tasks
      .map((t) => t.name)
      .filter((n) => n && n !== "unknown");
    if (names.length > 0) {
      getRedis().sadd("celeryhub:known-tasks", ...names).catch(() => {});
    }

    return tasks;
  } catch {
    return [];
  }
}

async function refreshWorkerInspect(): Promise<GatewayWorkerInspect | null> {
  try {
    return await gatewayInspectWorkers();
  } catch {
    return null;
  }
}

export interface RegisteredTasksResult {
  byWorker: Record<string, string[]>;
  tasks: string[];
}

async function refreshRegisteredTasks(): Promise<RegisteredTasksResult> {
  try {
    const knownNames = await getKnownTaskNames();

    let byWorker: Record<string, string[]> = {};
    try {
      const registered = await gatewayGetRegisteredTasks();
      byWorker = registered.by_worker;
    } catch {
      // Gateway unavailable – still have persistent names
    }

    const allTasks = new Set<string>(knownNames);
    for (const tasks of Object.values(byWorker)) {
      for (const t of tasks) allTasks.add(t);
    }

    return { byWorker, tasks: Array.from(allTasks).sort() };
  } catch {
    return { byWorker: {}, tasks: [] };
  }
}

export interface QueueDetailsResult {
  queueNames: string[];
  depths: Record<string, number>;
  pending: Record<
    string,
    { taskId: string; taskName: string; enqueuedAt: string }[]
  >;
}

async function refreshQueueDetails(): Promise<QueueDetailsResult> {
  const c = getCache();

  let depths: Record<string, number>;
  try {
    depths = await c.get<Record<string, number>>("queue-depths");
  } catch {
    depths = { celery: 0 };
  }

  const queueNames = Object.keys(depths);
  const pending: QueueDetailsResult["pending"] = {};

  await Promise.all(
    queueNames.map(async (q) => {
      try {
        pending[q] = await getPendingTasks(q, 20);
      } catch {
        pending[q] = [];
      }
    }),
  );

  return { queueNames, depths, pending };
}

// ---------------------------------------------------------------------------
// Public typed convenience accessors
// ---------------------------------------------------------------------------

export async function getCachedActiveTasks(): Promise<ActiveTask[]> {
  return getCache().get<ActiveTask[]>("active-tasks");
}

export async function getCachedQueueDepths(): Promise<Record<string, number>> {
  return getCache().get<Record<string, number>>("queue-depths");
}

export async function getCachedTaskHistory(): Promise<CompletedTaskMeta[]> {
  return getCache().get<CompletedTaskMeta[]>("task-history");
}

export async function getCachedWorkerInspect(): Promise<GatewayWorkerInspect | null> {
  return getCache().get<GatewayWorkerInspect | null>("worker-inspect");
}

export async function getCachedRegisteredTasks(): Promise<RegisteredTasksResult> {
  return getCache().get<RegisteredTasksResult>("registered-tasks");
}

export async function getCachedQueueDetails(): Promise<QueueDetailsResult> {
  return getCache().get<QueueDetailsResult>("queue-details");
}
