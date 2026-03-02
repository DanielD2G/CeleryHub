export function statusVariant(
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "SUCCESS":
      return "default";
    case "FAILURE":
      return "destructive";
    case "REVOKED":
      return "outline";
    default:
      return "secondary";
  }
}

export function normalizeArgs(raw: string | undefined): string {
  if (!raw || raw === "()" || raw === "null") return "[]";
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(Array.isArray(parsed) ? parsed : []);
  } catch {
    return "[]";
  }
}

export function normalizeKwargs(raw: string | undefined): string {
  if (!raw || raw === "null") return "{}";
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {});
  } catch {
    return "{}";
  }
}

export function timeAgo(timestamp: number): string {
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return `${Math.floor(seconds / 2592000)} months ago`;
}
