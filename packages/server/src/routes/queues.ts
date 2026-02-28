import { Hono } from "hono";
import { getCachedQueueDetails } from "../lib/cache.js";

const app = new Hono();

// GET /api/queues
app.get("/", async (c) => {
  const details = await getCachedQueueDetails();
  return c.json(details);
});

export default app;
