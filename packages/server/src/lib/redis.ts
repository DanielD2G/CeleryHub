import Redis from "ioredis";

let cached: Redis | null = null;

function getBrokerUrl(): string {
  const url = process.env.CELERY_BROKER_URL;
  if (!url) throw new Error("CELERY_BROKER_URL is not set");
  return url;
}

export function extractDbNumber(url: string): number {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.replace(/^\//, "");
    const db = parseInt(path, 10);
    return isNaN(db) ? 0 : db;
  } catch {
    return 0;
  }
}

export function getRedis(): Redis {
  if (cached) return cached;
  cached = new Redis(getBrokerUrl(), { maxRetriesPerRequest: 3 });
  return cached;
}

export function createSubscriber(): Redis {
  return new Redis(getBrokerUrl(), { maxRetriesPerRequest: null });
}

export function getDbNumber(): number {
  return extractDbNumber(getBrokerUrl());
}
