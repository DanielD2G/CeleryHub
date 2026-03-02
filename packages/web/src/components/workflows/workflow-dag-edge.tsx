interface DagEdgeProps {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  status?: string;
  label?: string;
}

export function WorkflowDagEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  status,
  label,
}: DagEdgeProps) {
  const midX = (sourceX + targetX) / 2;
  const midY = (sourceY + targetY) / 2;
  const d = `M ${sourceX} ${sourceY} C ${midX} ${sourceY}, ${midX} ${targetY}, ${targetX} ${targetY}`;

  let strokeColor = "var(--color-muted-foreground)";
  if (status === "succeeded") strokeColor = "var(--color-chart-2)";
  if (status === "failed") strokeColor = "var(--color-destructive)";
  if (status === "running") strokeColor = "var(--color-chart-1)";
  if (status === "skipped") strokeColor = "var(--color-muted-foreground)";

  return (
    <g>
      <path
        d={d}
        fill="none"
        stroke={strokeColor}
        strokeWidth={2.5}
        opacity={0.95}
        strokeDasharray={status === "skipped" ? "4 4" : undefined}
      />
      <circle cx={sourceX} cy={sourceY} r={3.5} fill={strokeColor} />
      <circle cx={targetX} cy={targetY} r={3.5} fill={strokeColor} />
      {label && (
        <text
          x={midX}
          y={midY - 6}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={11}
          fill="var(--color-foreground)"
          stroke="var(--color-background)"
          strokeWidth={4}
          paintOrder="stroke"
        >
          {label}
        </text>
      )}
    </g>
  );
}
