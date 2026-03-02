/**
 * Format a schedule for display.
 */
export function formatSchedule(
  scheduleType: string,
  intervalSeconds: number | null,
  cronExpression: string | null
): string {
  if (scheduleType === "none") return "manual";

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
