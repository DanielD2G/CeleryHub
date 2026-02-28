import {
  createContext,
  useCallback,
  useEffect,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import type {
  ActiveTask,
  CeleryEvent,
  CeleryState,
  CompletedTaskMeta,
} from "@/lib/types";

const MAX_EVENTS = 100;
const HEARTBEAT_TIMEOUT = 30_000; // 30s

type Action =
  | { type: "event"; payload: CeleryEvent }
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "check-stale" }
  | { type: "load-history"; payload: CompletedTaskMeta[] }
  | { type: "load-active"; payload: ActiveTask[] }
  | { type: "load-registered"; payload: string[] };

function celeryReducer(state: CeleryState, action: Action): CeleryState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true };

    case "disconnected":
      return { ...state, connected: false };

    case "check-stale": {
      const now = Date.now() / 1000;
      const workers = new Map(state.workers);
      let changed = false;
      for (const [hostname, worker] of workers) {
        if (
          worker.status === "online" &&
          now - worker.lastHeartbeat > HEARTBEAT_TIMEOUT / 1000
        ) {
          workers.set(hostname, { ...worker, status: "offline" });
          changed = true;
        }
      }
      return changed ? { ...state, workers } : state;
    }

    case "event": {
      const event = action.payload;
      const workers = new Map(state.workers);
      const activeTasks = new Map(state.activeTasks);
      const completedTasks = new Map(state.completedTasks);
      const knownTaskNames = new Set(state.knownTaskNames);
      const knownQueues = new Set(state.knownQueues);
      const recentEvents = [...state.recentEvents];

      // Add to recent events
      recentEvents.unshift(event);
      if (recentEvents.length > MAX_EVENTS) recentEvents.length = MAX_EVENTS;

      switch (event.type) {
        case "worker-online": {
          const e = event as CeleryEvent & {
            sw_ver?: string;
            sw_sys?: string;
          };
          workers.set(event.hostname, {
            hostname: event.hostname,
            status: "online",
            lastHeartbeat: event.timestamp,
            active: 0,
            processed: 0,
            swVer: e.sw_ver || "",
            swSys: e.sw_sys || "",
            pid: event.pid,
          });
          break;
        }

        case "worker-heartbeat": {
          const e = event as CeleryEvent & {
            active?: number;
            processed?: number;
            freq?: number;
            sw_ver?: string;
            sw_sys?: string;
          };
          const existing = workers.get(event.hostname);
          workers.set(event.hostname, {
            hostname: event.hostname,
            status: "online",
            lastHeartbeat: event.timestamp,
            active: e.active ?? existing?.active ?? 0,
            processed: e.processed ?? existing?.processed ?? 0,
            swVer: e.sw_ver ?? existing?.swVer ?? "",
            swSys: e.sw_sys ?? existing?.swSys ?? "",
            pid: event.pid || existing?.pid || 0,
          });
          break;
        }

        case "worker-offline": {
          const existing = workers.get(event.hostname);
          if (existing) {
            workers.set(event.hostname, { ...existing, status: "offline" });
          }
          break;
        }

        case "task-sent": {
          const e = event as CeleryEvent & {
            uuid?: string;
            name?: string;
            queue?: string;
            args?: string;
            kwargs?: string;
          };
          if (e.uuid && e.name) {
            activeTasks.set(e.uuid, {
              taskId: e.uuid,
              name: e.name,
              worker: "",
              startedAt: event.timestamp,
              status: "sent",
              args: e.args,
              kwargs: e.kwargs,
            });
            knownTaskNames.add(e.name);
            if (e.queue) knownQueues.add(e.queue);
          }
          break;
        }

        case "task-received": {
          const e = event as CeleryEvent & { uuid?: string; name?: string };
          if (e.uuid) {
            const existing = activeTasks.get(e.uuid);
            activeTasks.set(e.uuid, {
              taskId: e.uuid,
              name: e.name || existing?.name || "unknown",
              worker: event.hostname,
              startedAt: existing?.startedAt || event.timestamp,
              status: "received",
            });
            if (e.name) knownTaskNames.add(e.name);
          }
          break;
        }

        case "task-started": {
          const e = event as CeleryEvent & { uuid?: string };
          if (e.uuid) {
            const existing = activeTasks.get(e.uuid);
            if (existing) {
              activeTasks.set(e.uuid, {
                ...existing,
                worker: event.hostname || existing.worker,
                status: "started",
              });
            } else {
              activeTasks.set(e.uuid, {
                taskId: e.uuid,
                name: "unknown",
                worker: event.hostname,
                startedAt: event.timestamp,
                status: "started",
              });
            }
          }
          break;
        }

        case "task-succeeded": {
          const e = event as CeleryEvent & {
            uuid?: string;
            runtime?: number;
            result?: string;
          };
          if (e.uuid) {
            const active = activeTasks.get(e.uuid);
            completedTasks.set(e.uuid, {
              taskId: e.uuid,
              name: active?.name || "unknown",
              worker: active?.worker || event.hostname,
              status: "SUCCESS",
              runtime: e.runtime,
              result: e.result,
              args: active?.args,
              kwargs: active?.kwargs,
              completedAt: event.timestamp,
            });
            activeTasks.delete(e.uuid);
          }
          break;
        }

        case "task-failed": {
          const e = event as CeleryEvent & {
            uuid?: string;
            exception?: string;
            traceback?: string;
          };
          if (e.uuid) {
            const active = activeTasks.get(e.uuid);
            completedTasks.set(e.uuid, {
              taskId: e.uuid,
              name: active?.name || "unknown",
              worker: active?.worker || event.hostname,
              status: "FAILURE",
              exception: e.exception,
              traceback: e.traceback,
              args: active?.args,
              kwargs: active?.kwargs,
              completedAt: event.timestamp,
            });
            activeTasks.delete(e.uuid);
          }
          break;
        }

        case "task-revoked": {
          const e = event as CeleryEvent & { uuid?: string };
          if (e.uuid) {
            const active = activeTasks.get(e.uuid);
            completedTasks.set(e.uuid, {
              taskId: e.uuid,
              name: active?.name || "unknown",
              worker: active?.worker || event.hostname,
              status: "REVOKED",
              args: active?.args,
              kwargs: active?.kwargs,
              completedAt: event.timestamp,
            });
            activeTasks.delete(e.uuid);
          }
          break;
        }

        case "task-retried": {
          const e = event as CeleryEvent & { uuid?: string };
          if (e.uuid) {
            const existing = activeTasks.get(e.uuid);
            if (existing) {
              activeTasks.set(e.uuid, { ...existing, status: "sent" });
            }
          }
          break;
        }
      }

      return {
        ...state,
        workers,
        activeTasks,
        completedTasks,
        recentEvents,
        knownTaskNames,
        knownQueues,
      };
    }

    case "load-active": {
      const activeTasks = new Map(state.activeTasks);
      const knownTaskNames = new Set(state.knownTaskNames);
      const polledIds = new Set(action.payload.map((t) => t.taskId));
      let changed = false;

      // Add/update tasks from API
      for (const task of action.payload) {
        if (!state.completedTasks.has(task.taskId)) {
          activeTasks.set(task.taskId, task);
          changed = true;
        }
        if (task.name && task.name !== "unknown") {
          knownTaskNames.add(task.name);
        }
      }

      // Only remove tasks the API confirms are gone AND that we already
      // know completed (in completedTasks). Don't remove SSE-tracked tasks
      // the gateway hasn't seen yet.
      for (const id of activeTasks.keys()) {
        if (!polledIds.has(id) && state.completedTasks.has(id)) {
          activeTasks.delete(id);
          changed = true;
        }
      }

      return changed
        ? { ...state, activeTasks, knownTaskNames }
        : state;
    }

    case "load-history": {
      const completedTasks = new Map(state.completedTasks);
      const knownTaskNames = new Set(state.knownTaskNames);
      let changed = false;

      for (const task of action.payload) {
        // Don't overwrite real-time data
        if (!completedTasks.has(task.taskId)) {
          completedTasks.set(task.taskId, task);
          changed = true;
        }
        if (task.name && task.name !== "unknown") {
          knownTaskNames.add(task.name);
        }
      }

      return changed
        ? { ...state, completedTasks, knownTaskNames }
        : state;
    }

    case "load-registered": {
      const knownTaskNames = new Set(state.knownTaskNames);
      let changed = false;

      for (const name of action.payload) {
        if (!knownTaskNames.has(name)) {
          knownTaskNames.add(name);
          changed = true;
        }
      }

      return changed ? { ...state, knownTaskNames } : state;
    }

    default:
      return state;
  }
}

const initialState: CeleryState = {
  workers: new Map(),
  activeTasks: new Map(),
  completedTasks: new Map(),
  recentEvents: [],
  knownTaskNames: new Set(),
  knownQueues: new Set(["celery"]),
  connected: false,
};

export const CeleryContext = createContext<CeleryState>(initialState);

export function EventProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(celeryReducer, initialState);
  const eventSourceRef = useRef<EventSource | null>(null);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout>>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource("/api/events");
    eventSourceRef.current = es;

    es.onopen = () => {
      dispatch({ type: "connected" });
    };

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        if (event.type === "connected") {
          dispatch({ type: "connected" });
          return;
        }
        dispatch({ type: "event", payload: event });
      } catch {
        // skip malformed
      }
    };

    es.onerror = () => {
      dispatch({ type: "disconnected" });
      es.close();
      eventSourceRef.current = null;

      // Auto-retry in 3s
      retryTimeoutRef.current = setTimeout(() => {
        connect();
      }, 3000);
    };
  }, []);

  useEffect(() => {
    connect();

    // Check for stale workers every 10s
    const staleInterval = setInterval(() => {
      dispatch({ type: "check-stale" });
    }, 10_000);

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
      clearInterval(staleInterval);
    };
  }, [connect]);

  // Load historical tasks and registered tasks on mount
  useEffect(() => {
    let cancelled = false;

    fetch("/api/tasks/history?limit=50")
      .then((res) => (res.ok ? res.json() : []))
      .then((tasks: CompletedTaskMeta[]) => {
        if (!cancelled && tasks.length > 0) {
          dispatch({ type: "load-history", payload: tasks });
        }
      })
      .catch(() => {});

    fetch("/api/tasks/registered")
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { tasks: string[] } | null) => {
        if (!cancelled && data?.tasks?.length) {
          dispatch({ type: "load-registered", payload: data.tasks });
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, []);

  // Poll active tasks — fast (2s) when tasks are running, slow (10s) otherwise
  const hasActiveTasks = state.activeTasks.size > 0;
  useEffect(() => {
    let cancelled = false;

    const pollActive = () => {
      fetch("/api/tasks/active")
        .then((res) => (res.ok ? res.json() : []))
        .then((tasks: ActiveTask[]) => {
          if (!cancelled) {
            dispatch({ type: "load-active", payload: tasks });
          }
        })
        .catch(() => {});
    };

    pollActive(); // immediate first fetch
    const interval = hasActiveTasks ? 2000 : 10000;
    const id = setInterval(pollActive, interval);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [hasActiveTasks]);

  return (
    <CeleryContext.Provider value={state}>{children}</CeleryContext.Provider>
  );
}
