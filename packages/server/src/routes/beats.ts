import { Hono } from "hono";
import { getDb } from "../lib/db/index.js";
import { beatSchedules, beatRuns } from "../lib/db/schema.js";
import { computeNextRunAt, validateCronExpression } from "../lib/scheduler/cron.js";
import { eq, desc } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import { gatewaySendTask } from "../lib/celery-gateway.js";
import { sendCeleryTask } from "../lib/celery.js";
import { startScheduler, isSchedulerRunning } from "../lib/scheduler/index.js";

const app = new Hono();

interface CreateBeatInput {
  name: string;
  taskNames: string[];
  args?: string;
  kwargs?: string;
  queue?: string;
  scheduleType: "interval" | "cron";
  intervalSeconds?: number;
  cronExpression?: string;
  enabled?: boolean;
  maxRunCount?: number | null;
}

async function dispatchOneTask(
  taskName: string,
  args: unknown[],
  kwargs: Record<string, unknown>,
  queue: string
): Promise<string> {
  try {
    const res = await gatewaySendTask({
      task_name: taskName,
      args,
      kwargs,
      queue,
    });
    return res.task_id;
  } catch {
    return await sendCeleryTask(taskName, args, kwargs, queue);
  }
}

// GET /api/beats — list all beats
app.get("/", async (c) => {
  if (!isSchedulerRunning()) startScheduler();
  const db = getDb();
  const beats = db
    .select()
    .from(beatSchedules)
    .orderBy(desc(beatSchedules.createdAt))
    .all();
  return c.json(beats);
});

// POST /api/beats — create beat
app.post("/", async (c) => {
  const input = await c.req.json<CreateBeatInput>().catch(() => null);
  if (!input) {
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  if (!input.name) {
    return c.json({ error: "Name is required" }, 400);
  }
  if (!input.taskNames || input.taskNames.length === 0) {
    return c.json({ error: "At least one task must be selected" }, 400);
  }

  if (input.scheduleType === "interval") {
    if (!input.intervalSeconds || input.intervalSeconds <= 0) {
      return c.json({ error: "Interval seconds must be a positive number" }, 400);
    }
  } else if (input.scheduleType === "cron") {
    if (!input.cronExpression) {
      return c.json({ error: "Cron expression is required" }, 400);
    }
    const cronError = validateCronExpression(input.cronExpression);
    if (cronError) {
      return c.json({ error: `Invalid cron: ${cronError}` }, 400);
    }
  } else {
    return c.json({ error: "Schedule type must be 'interval' or 'cron'" }, 400);
  }

  try {
    if (input.args) JSON.parse(input.args);
  } catch {
    return c.json({ error: "Invalid JSON for args" }, 400);
  }
  try {
    if (input.kwargs) JSON.parse(input.kwargs);
  } catch {
    return c.json({ error: "Invalid JSON for kwargs" }, 400);
  }

  const id = uuidv4();
  const now = new Date().toISOString();
  const enabled = input.enabled !== false;

  let nextRunAt: string | null = null;
  if (enabled) {
    try {
      nextRunAt = computeNextRunAt(
        input.scheduleType,
        input.intervalSeconds || null,
        input.cronExpression || null
      ).toISOString();
    } catch (e) {
      return c.json(
        { error: `Failed to compute next run: ${e instanceof Error ? e.message : e}` },
        400
      );
    }
  }

  if (!isSchedulerRunning()) startScheduler();
  const db = getDb();
  db.insert(beatSchedules)
    .values({
      id,
      name: input.name,
      taskNames: JSON.stringify(input.taskNames),
      args: input.args || "[]",
      kwargs: input.kwargs || "{}",
      queue: input.queue || "celery",
      scheduleType: input.scheduleType,
      intervalSeconds: input.intervalSeconds || null,
      cronExpression: input.cronExpression || null,
      enabled,
      maxRunCount: input.maxRunCount ?? null,
      totalRunCount: 0,
      nextRunAt,
      createdAt: now,
      updatedAt: now,
    })
    .run();

  return c.json({ id }, 201);
});

// GET /api/beats/:id — get single beat
app.get("/:id", async (c) => {
  const id = c.req.param("id");
  const db = getDb();
  const beat = db
    .select()
    .from(beatSchedules)
    .where(eq(beatSchedules.id, id))
    .get();

  if (!beat) {
    return c.json({ error: "Beat not found" }, 404);
  }
  return c.json(beat);
});

// PUT /api/beats/:id — update beat
app.put("/:id", async (c) => {
  const id = c.req.param("id");
  const input = await c.req.json<Partial<CreateBeatInput>>().catch(() => null);
  if (!input) {
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  const db = getDb();
  const existing = db
    .select()
    .from(beatSchedules)
    .where(eq(beatSchedules.id, id))
    .get();

  if (!existing) return c.json({ error: "Beat not found" }, 404);

  if (input.taskNames !== undefined && input.taskNames.length === 0) {
    return c.json({ error: "At least one task must be selected" }, 400);
  }

  const scheduleType = input.scheduleType || existing.scheduleType;
  const intervalSeconds =
    input.intervalSeconds !== undefined
      ? input.intervalSeconds
      : existing.intervalSeconds;
  const cronExpression =
    input.cronExpression !== undefined
      ? input.cronExpression
      : existing.cronExpression;

  if (scheduleType === "cron" && cronExpression) {
    const cronError = validateCronExpression(cronExpression);
    if (cronError) return c.json({ error: `Invalid cron: ${cronError}` }, 400);
  }

  if (input.args) {
    try {
      JSON.parse(input.args);
    } catch {
      return c.json({ error: "Invalid JSON for args" }, 400);
    }
  }
  if (input.kwargs) {
    try {
      JSON.parse(input.kwargs);
    } catch {
      return c.json({ error: "Invalid JSON for kwargs" }, 400);
    }
  }

  const enabled = input.enabled !== undefined ? input.enabled : existing.enabled;
  const now = new Date().toISOString();

  let nextRunAt = existing.nextRunAt;
  if (
    input.scheduleType !== undefined ||
    input.intervalSeconds !== undefined ||
    input.cronExpression !== undefined
  ) {
    if (enabled) {
      try {
        nextRunAt = computeNextRunAt(
          scheduleType as "interval" | "cron",
          intervalSeconds || null,
          cronExpression || null
        ).toISOString();
      } catch {
        nextRunAt = null;
      }
    }
  }

  db.update(beatSchedules)
    .set({
      name: input.name || existing.name,
      taskNames:
        input.taskNames !== undefined
          ? JSON.stringify(input.taskNames)
          : existing.taskNames,
      args: input.args !== undefined ? input.args : existing.args,
      kwargs: input.kwargs !== undefined ? input.kwargs : existing.kwargs,
      queue: input.queue !== undefined ? input.queue : existing.queue,
      scheduleType: scheduleType,
      intervalSeconds: intervalSeconds || null,
      cronExpression: cronExpression || null,
      enabled,
      maxRunCount:
        input.maxRunCount !== undefined ? input.maxRunCount : existing.maxRunCount,
      nextRunAt,
      updatedAt: now,
    })
    .where(eq(beatSchedules.id, id))
    .run();

  return c.json({ ok: true });
});

// DELETE /api/beats/:id — delete beat
app.delete("/:id", async (c) => {
  const id = c.req.param("id");
  const db = getDb();
  db.delete(beatSchedules).where(eq(beatSchedules.id, id)).run();
  return c.json({ ok: true });
});

// POST /api/beats/:id/toggle — toggle beat
app.post("/:id/toggle", async (c) => {
  const id = c.req.param("id");
  const db = getDb();
  const existing = db
    .select()
    .from(beatSchedules)
    .where(eq(beatSchedules.id, id))
    .get();

  if (!existing) return c.json({ error: "Beat not found" }, 404);

  const newEnabled = !existing.enabled;
  const now = new Date().toISOString();

  let nextRunAt = existing.nextRunAt;
  if (newEnabled && !nextRunAt) {
    try {
      nextRunAt = computeNextRunAt(
        existing.scheduleType as "interval" | "cron",
        existing.intervalSeconds,
        existing.cronExpression
      ).toISOString();
    } catch {
      // leave null
    }
  }

  db.update(beatSchedules)
    .set({
      enabled: newEnabled,
      nextRunAt: newEnabled ? nextRunAt : null,
      updatedAt: now,
    })
    .where(eq(beatSchedules.id, id))
    .run();

  return c.json({ enabled: newEnabled });
});

// POST /api/beats/:id/run-now — run beat immediately
app.post("/:id/run-now", async (c) => {
  const id = c.req.param("id");
  const db = getDb();
  const beat = db
    .select()
    .from(beatSchedules)
    .where(eq(beatSchedules.id, id))
    .get();

  if (!beat) return c.json({ error: "Beat not found" }, 404);

  const taskNames: string[] = JSON.parse(beat.taskNames || "[]");
  if (taskNames.length === 0) return c.json({ error: "No tasks configured" }, 400);

  const args = JSON.parse(beat.args || "[]");
  const kwargs = JSON.parse(beat.kwargs || "{}");
  const queue = beat.queue || "celery";
  const now = new Date().toISOString();
  const dispatched: string[] = [];

  for (const taskName of taskNames) {
    let taskId: string | undefined;
    let error: string | undefined;
    let status = "SENT";

    try {
      taskId = await dispatchOneTask(taskName, args, kwargs, queue);
      dispatched.push(taskId);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      status = "FAILURE";
    }

    db.insert(beatRuns)
      .values({
        id: uuidv4(),
        scheduleId: beat.id,
        taskId: taskId || null,
        taskName,
        args: beat.args,
        kwargs: beat.kwargs,
        queue: beat.queue,
        status,
        error: error || null,
        scheduledAt: now,
        sentAt: now,
      })
      .run();
  }

  db.update(beatSchedules)
    .set({
      lastRunAt: now,
      totalRunCount: (beat.totalRunCount || 0) + 1,
      updatedAt: now,
    })
    .where(eq(beatSchedules.id, beat.id))
    .run();

  return c.json({ taskIds: dispatched });
});

// GET /api/beats/:id/runs — get beat run history
app.get("/:id/runs", async (c) => {
  const scheduleId = c.req.param("id");
  const limit = Math.min(
    Math.max(Number(c.req.query("limit")) || 50, 1),
    200,
  );
  const db = getDb();
  const runs = db
    .select()
    .from(beatRuns)
    .where(eq(beatRuns.scheduleId, scheduleId))
    .orderBy(desc(beatRuns.sentAt))
    .limit(limit)
    .all();
  return c.json(runs);
});

export default app;
