import { Hono } from "hono";
import { getCachedActiveTasks, getCachedTaskHistory, getCachedRegisteredTasks } from "../lib/cache.js";
import { getTaskPayloads } from "../lib/celery.js";
import { gatewayRevokeTask, gatewaySendTask, gatewayGetTaskStatus } from "../lib/celery-gateway.js";
import { sendCeleryTask, getCeleryTaskStatus } from "../lib/celery.js";

const app = new Hono();

// GET /api/tasks/active
app.get("/active", async (c) => {
  const tasks = await getCachedActiveTasks();
  return c.json(tasks);
});

// GET /api/tasks/history
app.get("/history", async (c) => {
  const limit = Math.min(
    Math.max(Number(c.req.query("limit")) || 50, 1),
    200,
  );
  const tasks = await getCachedTaskHistory();
  return c.json(tasks.slice(0, limit));
});

// GET /api/tasks/registered
app.get("/registered", async (c) => {
  const data = await getCachedRegisteredTasks();
  return c.json(data);
});

// GET /api/tasks/payloads
app.get("/payloads", async (c) => {
  const name = c.req.query("name");
  if (!name) {
    return c.json({ error: "name is required" }, 400);
  }

  try {
    const payloads = await getTaskPayloads(name);
    return c.json(payloads);
  } catch (err) {
    return c.json(
      { error: `Failed to fetch payloads: ${err}` },
      500
    );
  }
});

// POST /api/tasks/:id/revoke
app.post("/:id/revoke", async (c) => {
  const id = c.req.param("id");

  try {
    const body = await c.req.json().catch(() => ({}));
    const terminate = body?.terminate ?? false;
    const ALLOWED_SIGNALS = ["SIGTERM", "SIGKILL"];
    const signal = ALLOWED_SIGNALS.includes(body?.signal) ? body.signal : "SIGTERM";
    const result = await gatewayRevokeTask(id, terminate, signal);
    return c.json(result);
  } catch {
    return c.json(
      { error: "Gateway unavailable" },
      503
    );
  }
});

// POST /api/tasks/send
app.post("/send", async (c) => {
  const body = await c.req.json().catch(() => null);
  if (!body) {
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  const taskName = body.taskName as string;
  const queue = (body.queue as string) || "celery";
  const argsRaw = (body.args as string) || "[]";
  const kwargsRaw = (body.kwargs as string) || "{}";
  const countdown = body.countdown != null ? parseFloat(body.countdown) : null;
  const eta = body.eta || null;
  const priority = body.priority != null ? parseInt(body.priority, 10) : null;

  if (!taskName) {
    return c.json({ error: "Task name is required" }, 400);
  }

  if (!/^[\w.]+$/.test(taskName)) {
    return c.json({ error: "Invalid task name format" }, 400);
  }

  let args: unknown[];
  try {
    args = JSON.parse(argsRaw);
    if (!Array.isArray(args)) {
      return c.json({ error: "Args must be a JSON array" }, 400);
    }
  } catch {
    return c.json({ error: "Invalid JSON for args" }, 400);
  }

  let kwargs: Record<string, unknown>;
  try {
    kwargs = JSON.parse(kwargsRaw);
    if (typeof kwargs !== "object" || Array.isArray(kwargs) || kwargs === null) {
      return c.json({ error: "Kwargs must be a JSON object" }, 400);
    }
  } catch {
    return c.json({ error: "Invalid JSON for kwargs" }, 400);
  }

  // Try gateway first, fall back to direct Redis
  try {
    const res = await gatewaySendTask({
      task_name: taskName,
      args,
      kwargs,
      queue,
      countdown,
      eta,
      priority,
    });
    return c.json({ taskId: res.task_id });
  } catch {
    // Gateway unavailable — fall back to direct Redis
    try {
      const taskId = await sendCeleryTask(taskName, args, kwargs, queue);
      return c.json({ taskId });
    } catch (err) {
      return c.json({ error: `Failed to send task: ${err}` }, 500);
    }
  }
});

// GET /api/tasks/:id/status
app.get("/:id/status", async (c) => {
  const taskId = c.req.param("id");

  // Try gateway first, fall back to direct Redis
  try {
    const res = await gatewayGetTaskStatus(taskId);
    return c.json({ status: res.status, result: res.result });
  } catch {
    try {
      const result = await getCeleryTaskStatus(taskId);
      if (!result) return c.json(null);
      return c.json({ status: result.status, result: result.result });
    } catch {
      return c.json(null);
    }
  }
});

export default app;
