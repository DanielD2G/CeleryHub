import { useContext } from "react";
import { CeleryContext } from "@/components/event-provider";

export function useCelery() {
  const ctx = useContext(CeleryContext);
  if (!ctx) throw new Error("useCelery must be used within EventProvider");
  return ctx;
}

export function useCeleryWorkers() {
  const { workers } = useCelery();
  return workers;
}

export function useCeleryTasks() {
  const { activeTasks } = useCelery();
  return activeTasks;
}

export function useCeleryEvents() {
  const { recentEvents } = useCelery();
  return recentEvents;
}
