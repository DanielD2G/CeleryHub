import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { cors } from "hono/cors";
import { bodyLimit } from "hono/body-limit";
import { existsSync, readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// Import route modules
import tasks from "./routes/tasks.js";
import workers from "./routes/workers.js";
import queues from "./routes/queues.js";
import beats from "./routes/beats.js";
import control from "./routes/control.js";
import events from "./routes/events.js";

// Import scheduler & event collector
import { startScheduler } from "./lib/scheduler/index.js";
import { startEventCollector } from "./lib/event-collector.js";
import { ensureSchema } from "./lib/db/migrate.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

const app = new Hono();

// CORS
app.use("/*", cors({
  origin: process.env.CORS_ORIGINS?.split(",") || ["*"],
}));

// Request body size limit
app.use("/api/*", bodyLimit({ maxSize: 1024 * 1024 }));

// API routes
app.route("/api/tasks", tasks);
app.route("/api/workers", workers);
app.route("/api/queues", queues);
app.route("/api/beats", beats);
app.route("/api/control", control);
app.route("/api", events);

// Serve static files (production)
const webDistPath = resolve(__dirname, "../../web/dist");
if (existsSync(webDistPath)) {
  const indexHtml = readFileSync(resolve(webDistPath, "index.html"), "utf-8");

  app.use("/*", serveStatic({ root: webDistPath }));
  // SPA fallback: serve index.html for any non-API, non-file request
  app.get("*", (c) => c.html(indexHtml));
}

// Initialize
await ensureSchema();
startScheduler();
startEventCollector();

const port = parseInt(process.env.PORT || "3000");
console.log(`[CeleryHub] Server running on port ${port}`);

export default {
  fetch: app.fetch,
  port,
};
