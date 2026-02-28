import { Hono } from "hono";
import { getCachedWorkerInspect } from "../lib/cache.js";

const app = new Hono();

// GET /api/workers/inspect
app.get("/inspect", async (c) => {
  const data = await getCachedWorkerInspect();
  if (!data) {
    return c.json({ error: "Gateway unavailable" }, 503);
  }
  return c.json(data);
});

export default app;
