import { sqliteTable, text, integer } from "drizzle-orm/sqlite-core";

export const beatSchedules = sqliteTable("beat_schedules", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  taskNames: text("task_names").default("[]"), // JSON array: ["task.a", "task.b"]
  args: text("args").default("[]"),
  kwargs: text("kwargs").default("{}"),
  queue: text("queue").default("celery"),
  scheduleType: text("schedule_type").notNull(), // 'interval' | 'cron'
  intervalSeconds: integer("interval_seconds"),
  cronExpression: text("cron_expression"),
  enabled: integer("enabled", { mode: "boolean" }).default(true),
  maxRunCount: integer("max_run_count"),
  totalRunCount: integer("total_run_count").default(0),
  lastRunAt: text("last_run_at"),
  nextRunAt: text("next_run_at"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const beatRuns = sqliteTable("beat_runs", {
  id: text("id").primaryKey(),
  scheduleId: text("schedule_id")
    .notNull()
    .references(() => beatSchedules.id, { onDelete: "cascade" }),
  taskId: text("task_id"),
  taskName: text("task_name"),
  args: text("args"),
  kwargs: text("kwargs"),
  queue: text("queue"),
  status: text("status").default("SENT"), // 'SENT' | 'SUCCESS' | 'FAILURE'
  error: text("error"),
  scheduledAt: text("scheduled_at"),
  sentAt: text("sent_at"),
});

export type BeatSchedule = typeof beatSchedules.$inferSelect;
export type NewBeatSchedule = typeof beatSchedules.$inferInsert;
export type BeatRun = typeof beatRuns.$inferSelect;
export type NewBeatRun = typeof beatRuns.$inferInsert;
