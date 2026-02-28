import { createSubscriber, getDbNumber, getRedis } from "./redis.js";
import { parseKombuMessage } from "./parse-event.js";
import { getDb } from "./db/index.js";
import { beatRuns } from "./db/schema.js";
import { eq } from "drizzle-orm";
import type { CeleryEvent } from "./types.js";

const TASK_META_KEY = "celeryhub:tasks";
const ACTIVE_SET_KEY = "celeryhub:active-tasks";
const PAYLOADS_KEY = "celeryhub:payloads";
const KNOWN_TASKS_KEY = "celeryhub:known-tasks";

// 0 = no expiration (persist forever). Set CELERYHUB_TASK_TTL env var in seconds.
function getTaskTtl(): number {
  const raw = process.env.CELERYHUB_TASK_TTL;
  if (!raw || raw === "0") return 0;
  const ttl = parseInt(raw, 10);
  return isNaN(ttl) || ttl < 0 ? 0 : ttl;
}

type EventListener = (event: CeleryEvent) => void;

let started = false;
const listeners = new Set<EventListener>();

export function onCeleryEvent(fn: EventListener) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

function expireIfNeeded(redis: ReturnType<typeof getRedis>, key: string) {
  const ttl = getTaskTtl();
  if (ttl > 0) redis.expire(key, ttl).catch(() => {});
}

function persistEvent(event: CeleryEvent) {
  const redis = getRedis();
  const e = event as unknown as Record<string, unknown>;
  const uuid = e.uuid as string | undefined;
  if (!uuid) return;

  const eventType = event.type;

  if ((eventType === "task-sent" || eventType === "task-received") && e.name) {
    const metaFields: string[] = [
      "name", e.name as string,
      "worker", (event.hostname as string) || "",
      "started_at", String(event.timestamp),
    ];
    if (e.args != null) metaFields.push("args", String(e.args));
    if (e.kwargs != null) metaFields.push("kwargs", String(e.kwargs));
    redis.hset(`${TASK_META_KEY}:${uuid}`, ...metaFields).catch(() => {});
    expireIfNeeded(redis, `${TASK_META_KEY}:${uuid}`);
    redis.sadd(KNOWN_TASKS_KEY, e.name as string).catch(() => {});
    redis.sadd(ACTIVE_SET_KEY, uuid).catch(() => {});
  }

  if (eventType === "task-started") {
    redis.hset(
      `${TASK_META_KEY}:${uuid}`,
      "status", "STARTED",
      "worker", (event.hostname as string) || "",
      "started_at", String(event.timestamp),
    ).catch(() => {});
    redis.sadd(ACTIVE_SET_KEY, uuid).catch(() => {});
  }

  if (eventType === "task-sent" && e.name) {
    const payload = JSON.stringify({
      args: e.args ?? "[]",
      kwargs: e.kwargs ?? "{}",
      queue: e.queue ?? "celery",
      timestamp: event.timestamp,
    });
    const payloadKey = `${PAYLOADS_KEY}:${e.name as string}`;
    redis.lpush(payloadKey, payload).catch(() => {});
    redis.ltrim(payloadKey, 0, 9).catch(() => {});
    expireIfNeeded(redis, payloadKey);
  }

  if (eventType === "task-succeeded") {
    const fields: string[] = ["status", "SUCCESS"];
    if (e.runtime != null) fields.push("runtime", String(e.runtime));
    if (event.hostname) fields.push("worker", event.hostname as string);
    redis.hset(`${TASK_META_KEY}:${uuid}`, ...fields).catch(() => {});
    redis.srem(ACTIVE_SET_KEY, uuid).catch(() => {});
    try {
      getDb().update(beatRuns).set({ status: "SUCCESS" }).where(eq(beatRuns.taskId, uuid)).run();
    } catch { /* ignore */ }
  }

  if (eventType === "task-failed") {
    const fields = [
      "status", "FAILURE",
      ...(e.exception ? ["exception", e.exception as string] : []),
    ];
    if (event.hostname) fields.push("worker", event.hostname as string);
    redis.hset(`${TASK_META_KEY}:${uuid}`, ...fields).catch(() => {});
    redis.srem(ACTIVE_SET_KEY, uuid).catch(() => {});
    try {
      getDb().update(beatRuns).set({
        status: "FAILURE",
        error: (e.exception as string) || null,
      }).where(eq(beatRuns.taskId, uuid)).run();
    } catch { /* ignore */ }
  }

  if (eventType === "task-revoked") {
    redis.srem(ACTIVE_SET_KEY, uuid).catch(() => {});
  }
}

export function startEventCollector() {
  if (started) return;
  if (!process.env.CELERY_BROKER_URL) {
    console.log("[CeleryHub EventCollector] Skipped — CELERY_BROKER_URL not set");
    return;
  }
  started = true;

  const db = getDbNumber();
  const pattern = `/${db}.celeryev/*`;
  const subscriber = createSubscriber();

  subscriber.on("pmessage", (_pattern: string, channel: string, message: string) => {
    try {
      const parts = channel.split("/");
      const rawEventType = parts[parts.length - 1];
      const event = parseKombuMessage(message, rawEventType);
      if (event) {
        persistEvent(event);
        for (const fn of listeners) {
          try { fn(event); } catch { /* ignore */ }
        }
      }
    } catch { /* skip malformed */ }
  });

  subscriber.psubscribe(pattern).then(() => {
    console.log("[CeleryHub EventCollector] Subscribed to Celery events");
  }).catch((err) => {
    console.error("[CeleryHub EventCollector] Subscribe failed:", err);
  });
}
