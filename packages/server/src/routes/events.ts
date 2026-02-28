import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { onCeleryEvent } from "../lib/event-collector.js";

const app = new Hono();

app.get("/events", async (c) => {
  return streamSSE(c, async (stream) => {
    await stream.writeSSE({ data: JSON.stringify({ type: "connected" }) });

    const unsubscribe = onCeleryEvent((event) => {
      stream.writeSSE({ data: JSON.stringify(event) }).catch(() => {});
    });

    stream.onAbort(() => {
      unsubscribe();
    });

    while (true) {
      await new Promise((resolve) => setTimeout(resolve, 30000));
      if (stream.aborted) break;
    }
  });
});

export default app;
