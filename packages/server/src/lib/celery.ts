import { v4 as uuidv4 } from "uuid";
import { getRedis } from "./redis.js";
import type { ActiveTask, CompletedTaskMeta, TaskResult } from "./types.js";

export async function sendCeleryTask(
  taskName: string,
  args: unknown[] = [],
  kwargs: Record<string, unknown> = {},
  queue = "celery"
): Promise<string> {
  const redis = getRedis();
  const taskId = uuidv4();

  // Celery v2 protocol message
  const message = {
    body: Buffer.from(
      JSON.stringify([args, kwargs, { callbacks: null, errbacks: null, chain: null, chord: null }])
    ).toString("base64"),
    "content-encoding": "utf-8",
    "content-type": "application/json",
    headers: {
      lang: "py",
      task: taskName,
      id: taskId,
      root_id: taskId,
      parent_id: null,
      group: null,
      meth: null,
      shadow: null,
      eta: null,
      expires: null,
      retries: 0,
      timelimit: [null, null],
      argsrepr: JSON.stringify(args),
      kwargsrepr: JSON.stringify(kwargs),
      origin: "CeleryHub",
    },
    properties: {
      correlation_id: taskId,
      reply_to: "",
      delivery_mode: 2,
      delivery_info: {
        exchange: "",
        routing_key: queue,
      },
      priority: 0,
      body_encoding: "base64",
      delivery_tag: uuidv4(),
    },
  };

  await redis.lpush(queue, JSON.stringify(message));
  return taskId;
}

export async function getCeleryTaskStatus(
  taskId: string
): Promise<TaskResult | null> {
  const redis = getRedis();
  const raw = await redis.get(`celery-task-meta-${taskId}`);
  if (!raw) return null;

  try {
    const data = JSON.parse(raw);
    return {
      taskId: data.task_id || taskId,
      status: data.status || "UNKNOWN",
      result: data.result,
      traceback: data.traceback || null,
      dateDone: data.date_done || "",
      name: data.name,
      worker: data.worker,
      runtime: data.runtime,
    };
  } catch {
    return null;
  }
}

export async function getRecentResults(limit = 50): Promise<TaskResult[]> {
  const redis = getRedis();
  const results: TaskResult[] = [];
  let cursor = "0";

  do {
    const [nextCursor, keys] = await redis.scan(
      cursor,
      "MATCH",
      "celery-task-meta-*",
      "COUNT",
      100
    );
    cursor = nextCursor;

    if (keys.length > 0) {
      const pipeline = redis.pipeline();
      for (const key of keys) {
        pipeline.get(key);
      }
      const values = await pipeline.exec();

      if (values) {
        for (const [err, val] of values) {
          if (err || !val) continue;
          try {
            const data = JSON.parse(val as string);
            results.push({
              taskId: data.task_id || "",
              status: data.status || "UNKNOWN",
              result: data.result,
              traceback: data.traceback || null,
              dateDone: data.date_done || "",
              name: data.name,
              worker: data.worker,
              runtime: data.runtime,
            });
          } catch {
            // skip unparseable
          }
        }
      }
    }

    // Stop if we have enough
    if (results.length >= limit * 2) break;
  } while (cursor !== "0");

  // Sort by date_done desc and limit
  results.sort(
    (a, b) => new Date(b.dateDone).getTime() - new Date(a.dateDone).getTime()
  );
  return results.slice(0, limit);
}

export async function getActiveTasks(): Promise<ActiveTask[]> {
  const redis = getRedis();
  const uuids = await redis.smembers("celeryhub:active-tasks");
  if (uuids.length === 0) return [];

  const pipeline = redis.pipeline();
  for (const uuid of uuids) {
    pipeline.hgetall(`celeryhub:tasks:${uuid}`);
  }
  const values = await pipeline.exec();

  const tasks: ActiveTask[] = [];
  const staleUuids: string[] = [];

  for (let i = 0; i < uuids.length; i++) {
    const meta =
      values && values[i] && !values[i][0]
        ? (values[i][1] as Record<string, string>)
        : null;

    // If metadata is gone or task already completed, mark for cleanup
    if (
      !meta ||
      Object.keys(meta).length === 0 ||
      meta.status === "SUCCESS" ||
      meta.status === "FAILURE"
    ) {
      staleUuids.push(uuids[i]);
      continue;
    }

    const statusMap: Record<string, ActiveTask["status"]> = {
      STARTED: "started",
      RECEIVED: "received",
    };

    tasks.push({
      taskId: uuids[i],
      name: meta.name || "unknown",
      worker: meta.worker || "",
      startedAt: meta.started_at ? parseFloat(meta.started_at) : Date.now() / 1000,
      status: statusMap[meta.status] || "received",
    });
  }

  // Clean up stale entries
  if (staleUuids.length > 0) {
    redis.srem("celeryhub:active-tasks", ...staleUuids).catch(() => {});
  }

  return tasks;
}

const TERMINAL_STATES = new Set(["SUCCESS", "FAILURE", "REVOKED"]);

export async function getHistoricalTasks(
  limit = 50
): Promise<CompletedTaskMeta[]> {
  const redis = getRedis();
  const results = await getRecentResults(limit);

  // Filter to terminal states only
  const terminal = results.filter((r) => TERMINAL_STATES.has(r.status));

  if (terminal.length === 0) return [];

  // Enrich with metadata from celeryhub:tasks:{uuid}
  const metaPipeline = redis.pipeline();
  for (const r of terminal) {
    metaPipeline.hgetall(`celeryhub:tasks:${r.taskId}`);
  }
  const metaValues = await metaPipeline.exec();

  const tasks: CompletedTaskMeta[] = [];
  for (let i = 0; i < terminal.length; i++) {
    const r = terminal[i];
    const meta =
      metaValues && metaValues[i] && !metaValues[i][0]
        ? (metaValues[i][1] as Record<string, string> | null)
        : null;

    tasks.push({
      taskId: r.taskId,
      name: r.name || meta?.name || "unknown",
      worker: r.worker || meta?.worker || "",
      status: r.status as "SUCCESS" | "FAILURE" | "REVOKED",
      runtime: r.runtime ?? (meta?.runtime ? parseFloat(meta.runtime) : undefined),
      result: r.result != null ? String(r.result) : undefined,
      traceback: r.traceback || undefined,
      args: meta?.args,
      kwargs: meta?.kwargs,
      completedAt: r.dateDone
        ? new Date(r.dateDone).getTime() / 1000
        : Date.now() / 1000,
    });
  }

  return tasks;
}

export async function getKnownTaskNames(): Promise<string[]> {
  const redis = getRedis();
  const names = await redis.smembers("celeryhub:known-tasks");
  return names.sort();
}

export async function getQueueLengths(
  queues = ["celery"]
): Promise<Map<string, number>> {
  const redis = getRedis();
  const result = new Map<string, number>();

  const pipeline = redis.pipeline();
  for (const q of queues) {
    pipeline.llen(q);
  }
  const values = await pipeline.exec();

  if (values) {
    queues.forEach((q, i) => {
      const [err, len] = values[i];
      result.set(q, err ? 0 : (len as number));
    });
  }

  return result;
}

export interface TaskPayload {
  args: string;
  kwargs: string;
  queue: string;
  timestamp: number;
}

export async function getTaskPayloads(
  taskName: string,
  limit = 10
): Promise<TaskPayload[]> {
  const redis = getRedis();
  const raw = await redis.lrange(`celeryhub:payloads:${taskName}`, 0, limit - 1);
  const payloads: TaskPayload[] = [];

  for (const item of raw) {
    try {
      payloads.push(JSON.parse(item));
    } catch {
      // skip unparseable
    }
  }

  return payloads;
}

export async function getPendingTasks(
  queue = "celery",
  limit = 20
): Promise<{ taskId: string; taskName: string; enqueuedAt: string }[]> {
  const redis = getRedis();
  const raw = await redis.lrange(queue, 0, limit - 1);
  const tasks: { taskId: string; taskName: string; enqueuedAt: string }[] = [];

  for (const item of raw) {
    try {
      const msg = JSON.parse(item);
      const taskId =
        msg.headers?.id ||
        msg.properties?.correlation_id ||
        "";
      const taskName = msg.headers?.task || "unknown";
      tasks.push({
        taskId,
        taskName,
        enqueuedAt: new Date().toISOString(),
      });
    } catch {
      // skip unparseable
    }
  }

  return tasks;
}
