import { Hono } from "hono";
import { gatewayControl } from "../lib/celery-gateway.js";

const app = new Hono();

const validActions = [
  "pool-grow",
  "pool-shrink",
  "rate-limit",
  "add-consumer",
  "cancel-consumer",
  "shutdown",
  "purge",
];

// POST /api/control/:action
app.post("/:action", async (c) => {
  const action = c.req.param("action");

  if (!validActions.includes(action)) {
    return c.json(
      { error: `Invalid action: ${action}` },
      400
    );
  }

  try {
    const body = await c.req.json();
    const result = await gatewayControl(action, body);
    return c.json(result);
  } catch {
    return c.json(
      { error: "Gateway unavailable" },
      503
    );
  }
});

export default app;
