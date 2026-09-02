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
import { apiGet } from "@/lib/api";

const MAX_EVENTS = 100;
// taskId -> consecutive active-polls that did not report it
const _missedPolls = new Map<string, number>();
const MAX_COMPLETED = 500;
const HEARTBEAT_TIMEOUT = 30_000; // 30s

function _cappedCompletedTasks(
  map: Map<string, CompletedTaskMeta>
): Map<string, CompletedTaskMeta> {
  if (map.size <= MAX_COMPLETED) return map;
  const entries = Array.from(map.entries())
    .sort(([, a], [, b]) => b.completedAt - a.completedAt)
    .slice(0, MAX_COMPLETED);
  return new Map(entries);
}

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
      const recentEvents = [event, ...state.recentEvents];
      if (recentEvents.length > MAX_EVENTS) recentEvents.length = MAX_EVENTS;

      switch (event.type) {
        case "worker-online": {
          const e = event as CeleryEvent & { sw_ver?: string; sw_sys?: string };
          const workers = new Map(state.workers);
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
          return { ...state, workers, recentEvents };
        }

        case "worker-heartbeat": {
          const e = event as CeleryEvent & {
            active?: number;
            processed?: number;
            sw_ver?: string;
            sw_sys?: string;
          };
          const workers = new Map(state.workers);
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
          return { ...state, workers, recentEvents };
        }

        case "worker-offline": {
          const existing = state.workers.get(event.hostname);
          if (!existing) return { ...state, recentEvents };
          const workers = new Map(state.workers);
          workers.set(event.hostname, { ...existing, status: "offline" });
          return { ...state, workers, recentEvents };
        }

        case "task-sent": {
          const e = event as CeleryEvent & {
            uuid?: string;
            name?: string;
            queue?: string;
            args?: string;
            kwargs?: string;
          };
          if (!e.uuid || !e.name) return { ...state, recentEvents };
          const activeTasks = new Map(state.activeTasks);
          const knownTaskNames = new Set(state.knownTaskNames);
          const knownQueues = e.queue
            ? new Set(state.knownQueues).add(e.queue)
            : state.knownQueues;
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
          return { ...state, activeTasks, knownTaskNames, knownQueues, recentEvents };
        }

        case "task-received": {
          const e = event as CeleryEvent & { uuid?: string; name?: string };
          if (!e.uuid) return { ...state, recentEvents };
          const activeTasks = new Map(state.activeTasks);
          const existing = activeTasks.get(e.uuid);
          activeTasks.set(e.uuid, {
            taskId: e.uuid,
            name: e.name || existing?.name || "unknown",
            worker: event.hostname,
            startedAt: existing?.startedAt || event.timestamp,
            status: "received",
          });
          if (e.name) {
            const knownTaskNames = new Set(state.knownTaskNames);
            knownTaskNames.add(e.name);
            return { ...state, activeTasks, knownTaskNames, recentEvents };
          }
          return { ...state, activeTasks, recentEvents };
        }

        case "task-started": {
          const e = event as CeleryEvent & { uuid?: string };
          if (!e.uuid) return { ...state, recentEvents };
          const activeTasks = new Map(state.activeTasks);
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
          return { ...state, activeTasks, recentEvents };
        }

        case "task-succeeded": {
          const e = event as CeleryEvent & {
            uuid?: string;
            runtime?: number;
            result?: string;
          };
          if (!e.uuid) return { ...state, recentEvents };
          const activeTasks = new Map(state.activeTasks);
          const completedTasks = new Map(state.completedTasks);
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
          return {
            ...state,
            activeTasks,
            completedTasks: _cappedCompletedTasks(completedTasks),
            recentEvents,
          };
        }

        case "task-failed": {
          const e = event as CeleryEvent & {
            uuid?: string;
            exception?: string;
            traceback?: string;
          };
          if (!e.uuid) return { ...state, recentEvents };
          const activeTasks = new Map(state.activeTasks);
          const completedTasks = new Map(state.completedTasks);
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
          return {
            ...state,
            activeTasks,
            completedTasks: _cappedCompletedTasks(completedTasks),
            recentEvents,
          };
        }

        case "task-revoked": {
          const e = event as CeleryEvent & { uuid?: string };
          if (!e.uuid) return { ...state, recentEvents };
          const activeTasks = new Map(state.activeTasks);
          const completedTasks = new Map(state.completedTasks);
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
          return {
            ...state,
            activeTasks,
            completedTasks: _cappedCompletedTasks(completedTasks),
            recentEvents,
          };
        }

        case "task-retried": {
          const e = event as CeleryEvent & { uuid?: string };
          if (!e.uuid) return { ...state, recentEvents };
          const existing = state.activeTasks.get(e.uuid);
          if (!existing) return { ...state, recentEvents };
          const activeTasks = new Map(state.activeTasks);
          activeTasks.set(e.uuid, { ...existing, status: "sent" });
          return { ...state, activeTasks, recentEvents };
        }

        default:
          return { ...state, recentEvents };
      }
    }

    case "load-active": {
      const activeTasks = new Map(state.activeTasks);
      const knownTaskNames = new Set(state.knownTaskNames);
      const polledIds = new Set(action.payload.map((t) => t.taskId));
      let changed = false;
      let namesChanged = false;

      // Add/update tasks from API — only flag a change when the entry is
      // actually new or different, otherwise every poll produced a fresh
      // state object and re-rendered every consumer.
      for (const task of action.payload) {
        if (!state.completedTasks.has(task.taskId)) {
          const prev = activeTasks.get(task.taskId);
          if (
            !prev ||
            prev.status !== task.status ||
            prev.worker !== task.worker ||
            prev.startedAt !== task.startedAt
          ) {
            activeTasks.set(task.taskId, task);
            changed = true;
          }
          _missedPolls.delete(task.taskId);
        }
        if (task.name && task.name !== "unknown" && !knownTaskNames.has(task.name)) {
          knownTaskNames.add(task.name);
          namesChanged = true;
        }
      }

      // Evict tasks the gateway stopped reporting. Known-completed ones go
      // immediately; unknown ones (worker died, lost terminal event) after
      // three consecutive misses, so they can't sit in "Active" forever.
      for (const id of activeTasks.keys()) {
        if (polledIds.has(id)) continue;
        if (state.completedTasks.has(id)) {
          activeTasks.delete(id);
          _missedPolls.delete(id);
          changed = true;
          continue;
        }
        const misses = (_missedPolls.get(id) ?? 0) + 1;
        if (misses >= 3) {
          activeTasks.delete(id);
          _missedPolls.delete(id);
          changed = true;
        } else {
          _missedPolls.set(id, misses);
        }
      }

      return changed || namesChanged
        ? { ...state, activeTasks, knownTaskNames }
        : state;
    }

    case "load-history": {
      const completedTasks = new Map(state.completedTasks);
      const knownTaskNames = new Set(state.knownTaskNames);
      let changed = false;

      for (const task of action.payload) {
        const existing = completedTasks.get(task.taskId);
        if (!existing) {
          completedTasks.set(task.taskId, task);
          changed = true;
        } else if (
          (existing.name === "unknown" && task.name && task.name !== "unknown") ||
          (!existing.exception && task.exception)
        ) {
          // The SSE event arrived without a name (e.g. a NotRegistered
          // failure emits only task-failed); the REST history has the
          // backfilled one — upgrade the entry instead of keeping "unknown".
          completedTasks.set(task.taskId, { ...existing, ...task });
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

    apiGet<CompletedTaskMeta[]>("/api/tasks/history?limit=50")
      .then((tasks) => {
        if (!cancelled && tasks.length > 0) {
          dispatch({ type: "load-history", payload: tasks });
        }
      })
      .catch(() => {});

    // Registered tasks: fetch now and re-poll periodically so tasks added
    // to a worker (e.g. after a worker redeploy) show up without reloading
    // the app.
    const pollRegistered = () => {
      if (document.hidden) return;
      apiGet<{ tasks: string[] }>("/api/tasks/registered")
        .then((data) => {
          if (!cancelled && data?.tasks?.length) {
            dispatch({ type: "load-registered", payload: data.tasks });
          }
        })
        .catch(() => {});
    };
    pollRegistered();
    const registeredInterval = setInterval(pollRegistered, 60_000);

    return () => {
      cancelled = true;
      clearInterval(registeredInterval);
    };
  }, []);

  // Poll active tasks — fast (2s) when tasks are running, slow (10s) otherwise
  const hasActiveTasks = state.activeTasks.size > 0;
  useEffect(() => {
    let cancelled = false;
    let seq = 0;
    let inFlight: AbortController | null = null;

    const pollActive = () => {
      if (document.hidden) return; // don't hammer the API from background tabs
      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;
      const mySeq = ++seq;
      apiGet<ActiveTask[]>("/api/tasks/active", controller.signal)
        .then((tasks) => {
          // Out-of-order guard: a slow response must not clobber a newer one.
          if (!cancelled && mySeq === seq) {
            dispatch({ type: "load-active", payload: tasks });
          }
        })
        .catch(() => {});
    };

    pollActive(); // immediate first fetch
    const interval = hasActiveTasks ? 2000 : 4000;
    const id = setInterval(pollActive, interval);
    const onVisible = () => {
      if (!document.hidden) pollActive();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      inFlight?.abort();
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [hasActiveTasks]);

  return (
    <CeleryContext.Provider value={state}>{children}</CeleryContext.Provider>
  );
}
