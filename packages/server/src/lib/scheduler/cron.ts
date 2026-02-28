import { CronExpressionParser } from "cron-parser";

/**
 * Calculate the next run time for a schedule.
 */
export function computeNextRunAt(
  scheduleType: "interval" | "cron",
  intervalSeconds: number | null,
  cronExpression: string | null,
  fromDate?: Date
): Date {
  const from = fromDate || new Date();

  if (scheduleType === "interval") {
    if (!intervalSeconds || intervalSeconds <= 0) {
      throw new Error("intervalSeconds must be a positive number");
    }
    return new Date(from.getTime() + intervalSeconds * 1000);
  }

  if (scheduleType === "cron") {
    if (!cronExpression) {
      throw new Error("cronExpression is required for cron schedules");
    }
    const parsed = CronExpressionParser.parse(cronExpression, {
      currentDate: from,
    });
    return parsed.next().toDate();
  }

  throw new Error(`Unknown schedule type: ${scheduleType}`);
}

/**
 * Validate a cron expression. Returns null if valid, error message if invalid.
 */
export function validateCronExpression(expr: string): string | null {
  try {
    CronExpressionParser.parse(expr);
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : "Invalid cron expression";
  }
}

/**
 * Format a schedule for display.
 */
export function formatSchedule(
  scheduleType: string,
  intervalSeconds: number | null,
  cronExpression: string | null
): string {
  if (scheduleType === "cron" && cronExpression) {
    return `cron: ${cronExpression}`;
  }

  if (scheduleType === "interval" && intervalSeconds) {
    if (intervalSeconds < 60) return `every ${intervalSeconds}s`;
    if (intervalSeconds < 3600) return `every ${Math.round(intervalSeconds / 60)}m`;
    if (intervalSeconds < 86400) return `every ${Math.round(intervalSeconds / 3600)}h`;
    return `every ${Math.round(intervalSeconds / 86400)}d`;
  }

  return "unknown";
}
