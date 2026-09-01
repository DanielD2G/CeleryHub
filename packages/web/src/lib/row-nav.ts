import type { KeyboardEvent } from "react";

/**
 * Props for a clickable table row that is also reachable by keyboard.
 * Spread onto a <TableRow>: role, tabIndex, onClick and Enter/Space handling.
 */
export function clickableRow(onActivate: () => void) {
  return {
    role: "link" as const,
    tabIndex: 0,
    className: "cursor-pointer",
    onClick: onActivate,
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onActivate();
      }
    },
  };
}
