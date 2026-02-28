import type { CeleryEvent } from "./types.js";

export function parseKombuMessage(
  raw: string,
  channelEventType?: string
): CeleryEvent | null {
  try {
    const msg = JSON.parse(raw);

    // Format 1: Kombu envelope with body field
    if (msg.body) {
      let body: Record<string, unknown>;

      if (typeof msg.body === "string") {
        // body_encoding can be in properties, headers, or top-level
        const encoding =
          msg.properties?.body_encoding ||
          msg.headers?.body_encoding ||
          msg["body-encoding"];

        if (encoding === "base64") {
          const decoded = Buffer.from(msg.body, "base64").toString("utf-8");
          body = JSON.parse(decoded);
        } else {
          body = JSON.parse(msg.body);
        }
      } else {
        body = msg.body;
      }

      // Kombu wraps event data in an array: [{...event...}]
      if (Array.isArray(body)) {
        body = (body[0] as Record<string, unknown>) || {};
      }

      const event = (body as Record<string, unknown>) || {};

      // Normalize the type field
      if (!event.type && channelEventType) {
        event.type = channelEventType;
      }

      // Merge headers into event if present (but don't overwrite body fields)
      if (msg.headers && typeof msg.headers === "object") {
        for (const [key, value] of Object.entries(
          msg.headers as Record<string, unknown>
        )) {
          if (!(key in event)) {
            event[key] = value;
          }
        }
      }

      return normalizeEvent(event as Record<string, unknown>);
    }

    // Format 2: Raw event with type field directly
    if (msg.type) {
      return normalizeEvent(msg);
    }

    // Format 3: No type field, use channel info
    if (channelEventType) {
      msg.type = channelEventType;
      return normalizeEvent(msg);
    }

    return null;
  } catch {
    return null;
  }
}

function normalizeEvent(raw: Record<string, unknown>): CeleryEvent {
  // Celery events use dots in type (worker.online), we use dashes for consistency
  const type =
    typeof raw.type === "string"
      ? raw.type.replace(/\./g, "-")
      : "unknown";

  return {
    ...raw,
    type,
    hostname: (raw.hostname as string) || "unknown",
    timestamp: (raw.timestamp as number) || Date.now() / 1000,
    pid: (raw.pid as number) || 0,
    clock: (raw.clock as number) || 0,
  } as CeleryEvent;
}
