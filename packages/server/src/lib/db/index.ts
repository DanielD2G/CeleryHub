import { drizzle } from "drizzle-orm/bun-sqlite";
import { Database } from "bun:sqlite";
import { mkdirSync } from "fs";
import { dirname } from "path";
import * as schema from "./schema.js";

let cached: ReturnType<typeof drizzle<typeof schema>> | null = null;

function getDbPath(): string {
  return process.env.CELERYHUB_DB_PATH || "./data/celeryhub.db";
}

function createTables(sqlite: Database) {
  sqlite.exec(`
    CREATE TABLE IF NOT EXISTS beat_schedules (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      task_names TEXT DEFAULT '[]',
      args TEXT DEFAULT '[]',
      kwargs TEXT DEFAULT '{}',
      queue TEXT DEFAULT 'celery',
      schedule_type TEXT NOT NULL,
      interval_seconds INTEGER,
      cron_expression TEXT,
      enabled INTEGER DEFAULT 1,
      max_run_count INTEGER,
      total_run_count INTEGER DEFAULT 0,
      last_run_at TEXT,
      next_run_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS beat_runs (
      id TEXT PRIMARY KEY,
      schedule_id TEXT NOT NULL REFERENCES beat_schedules(id) ON DELETE CASCADE,
      task_id TEXT,
      task_name TEXT,
      args TEXT,
      kwargs TEXT,
      queue TEXT,
      status TEXT DEFAULT 'SENT',
      error TEXT,
      scheduled_at TEXT,
      sent_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_beat_runs_schedule_id ON beat_runs(schedule_id);
    CREATE INDEX IF NOT EXISTS idx_beat_schedules_next_run ON beat_schedules(enabled, next_run_at);
  `);

  // Migration: add task_names column if upgrading from old schema with task_name
  try {
    sqlite.exec(`ALTER TABLE beat_schedules ADD COLUMN task_names TEXT DEFAULT '[]'`);
  } catch {
    // Column already exists — ignore
  }
  try {
    sqlite.exec(`
      UPDATE beat_schedules SET task_names = '["' || task_name || '"]'
      WHERE (task_names IS NULL OR task_names = '[]')
        AND task_name IS NOT NULL AND task_name != ''
    `);
  } catch {
    // No task_name column or no data — ignore
  }
}

export function getDb() {
  if (cached) return cached;

  const dbPath = getDbPath();

  // Ensure directory exists
  mkdirSync(dirname(dbPath), { recursive: true });

  const sqlite = new Database(dbPath, { create: true });
  sqlite.run("PRAGMA journal_mode = WAL");
  sqlite.run("PRAGMA foreign_keys = ON");

  createTables(sqlite);

  cached = drizzle(sqlite, { schema });
  return cached;
}
