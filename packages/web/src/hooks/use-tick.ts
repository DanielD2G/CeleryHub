import { useEffect, useState } from "react";

/**
 * Shared 1-second timer. Returns a tick counter that increments every second,
 * triggering a re-render. Useful for Duration components to avoid per-row intervals.
 */
export function useTick(): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  return tick;
}
