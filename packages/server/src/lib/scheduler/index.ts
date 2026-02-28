import { getDb } from "../db/index.js";
import { beatSchedules, beatRuns } from "../db/schema.js";
import { computeNextRunAt } from "./cron.js";
import { eq, and, lte } from "drizzle-orm";
import { v4 as uuidv4 } from "uuid";
import { gatewaySendTask } from "../celery-gateway.js";
import { sendCeleryTask } from "../celery.js";

let schedulerStarted = false;
let schedulerHandle: ReturnType<typeof setInterval> | undefined;
let ticking = false;

export function isSchedulerRunning() {
  return schedulerStarted === true;
}

async function dispatchTask(
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

async function tick() {
  if (ticking) return;
  ticking = true;
  try {
    const db = getDb();
    const now = new Date().toISOString();

    const dueBeats = db
      .select()
      .from(beatSchedules)
      .where(
        and(
          eq(beatSchedules.enabled, true),
          lte(beatSchedules.nextRunAt, now)
        )
      )
      .all();

    if (dueBeats.length > 0) {
      console.log(`[CeleryHub Scheduler] ${dueBeats.length} beat(s) due`);
    }

    for (const beat of dueBeats) {
      const scheduledAt = beat.nextRunAt || now;

      const taskNames: string[] = JSON.parse(beat.taskNames || "[]");
      const args = JSON.parse(beat.args || "[]");
      const kwargs = JSON.parse(beat.kwargs || "{}");
      const queue = beat.queue || "celery";

      // Calculate next run BEFORE dispatching to prevent duplicate dispatch
      const newTotalRunCount = (beat.totalRunCount || 0) + 1;
      const shouldDisable =
        beat.maxRunCount != null && newTotalRunCount >= beat.maxRunCount;

      let nextRunAt: string | null = null;
      if (!shouldDisable) {
        try {
          nextRunAt = computeNextRunAt(
            beat.scheduleType as "interval" | "cron",
            beat.intervalSeconds,
            beat.cronExpression
          ).toISOString();
        } catch {
          nextRunAt = null;
        }
      }

      // Update the beat immediately so no other tick can pick it up
      db.update(beatSchedules)
        .set({
          nextRunAt,
          totalRunCount: newTotalRunCount,
          enabled: shouldDisable ? false : beat.enabled,
          updatedAt: now,
        })
        .where(eq(beatSchedules.id, beat.id))
        .run();

      // Now dispatch tasks (network calls)
      for (const taskName of taskNames) {
        let taskId: string | undefined;
        let error: string | undefined;
        let status = "SENT";

        try {
          taskId = await dispatchTask(taskName, args, kwargs, queue);
          console.log(`[CeleryHub Scheduler] Dispatched ${taskName} -> ${taskId}`);
        } catch (e) {
          error = e instanceof Error ? e.message : String(e);
          status = "FAILURE";
          console.error(`[CeleryHub Scheduler] Failed to dispatch ${taskName}: ${error}`);
        }

        const sentAt = new Date().toISOString();
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
            scheduledAt,
            sentAt,
          })
          .run();
      }

      db.update(beatSchedules)
        .set({ lastRunAt: new Date().toISOString() })
        .where(eq(beatSchedules.id, beat.id))
        .run();
    }
  } catch (e) {
    console.error("[CeleryHub Scheduler] Tick error:", e);
  } finally {
    ticking = false;
  }
}

export function startScheduler() {
  if (schedulerStarted) return;
  schedulerStarted = true;

  console.log("[CeleryHub Scheduler] Started");
  tick();
  schedulerHandle = setInterval(tick, 1000);
}

export function stopScheduler() {
  if (schedulerHandle) {
    clearInterval(schedulerHandle);
    schedulerHandle = undefined;
  }
  schedulerStarted = false;
  console.log("[CeleryHub Scheduler] Stopped");
}
