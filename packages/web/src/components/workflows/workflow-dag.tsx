import { useMemo, useState, useCallback } from "react";
import dagre from "@dagrejs/dagre";
import type { WorkflowStep, StepRunDetail } from "@/lib/types";
import { WorkflowDagNode } from "./workflow-dag-node";
import { WorkflowDagEdge } from "./workflow-dag-edge";
import { Button } from "@/components/ui/button";
import { Plus, Minus } from "lucide-react";
import { parseJson } from "@/lib/workflow-utils";

interface WorkflowDagProps {
  steps: WorkflowStep[];
  stepRuns?: StepRunDetail[];
  scheduleType?: string;
}

const _NODE_WIDTH = 280;
const _NODE_HEIGHT = 100;
const _ZOOM_STEP = 0.15;
const _MIN_ZOOM = 0.3;
const _MAX_ZOOM = 2;
const _LEFT_GUTTER = 140;


function _rootTriggerLabel(scheduleType?: string): string {
  if (scheduleType === "cron") return "cron";
  if (scheduleType === "interval") return "interval";
  return "manual";
}

function _ZoomControls({
  zoom,
  onZoomIn,
  onZoomOut,
}: {
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
}) {
  return (
    <div className="absolute top-2 right-2 z-10 flex items-center gap-1 rounded-md border bg-background/80 p-0.5 backdrop-blur-sm">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        onClick={onZoomOut}
        disabled={zoom <= _MIN_ZOOM}
      >
        <Minus className="h-3.5 w-3.5" />
      </Button>
      <span className="min-w-[3ch] text-center text-xs text-muted-foreground">
        {Math.round(zoom * 100)}%
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        onClick={onZoomIn}
        disabled={zoom >= _MAX_ZOOM}
      >
        <Plus className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

export function WorkflowDag({ steps, stepRuns, scheduleType }: WorkflowDagProps) {
  const [zoom, setZoom] = useState<number>(1);

  const stepRunMap = useMemo(() => {
    if (!stepRuns) return new Map<string, StepRunDetail>();
    return new Map(stepRuns.map((sr) => [sr.stepId, sr]));
  }, [stepRuns]);

  const hasEdges = useMemo(
    () => steps.some((s) => parseJson<string[]>(s.dependsOn, []).length > 0),
    [steps]
  );

  const layout = useMemo(() => {
    if (!hasEdges) return null;
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", ranksep: 80, nodesep: 40 });
    g.setDefaultEdgeLabel(() => ({}));

    for (const step of steps) {
      g.setNode(step.id, { width: _NODE_WIDTH, height: _NODE_HEIGHT });
    }
    for (const step of steps) {
      const deps = parseJson<string[]>(step.dependsOn, []);
      for (const dep of deps) {
        g.setEdge(dep, step.id);
      }
    }
    dagre.layout(g);
    return g;
  }, [steps, hasEdges]);

  // Content size for both modes
  const contentWidth = hasEdges
    ? (layout!.graph().width || 500) + 40 + _LEFT_GUTTER
    : steps.length * (_NODE_WIDTH + 16) + 16;
  const contentHeight = hasEdges
    ? (layout!.graph().height || 200) + 40
    : _NODE_HEIGHT + 20;

  const zoomIn = useCallback(
    () => setZoom((z) => Math.min(_MAX_ZOOM, (z ?? 1) + _ZOOM_STEP)),
    []
  );
  const zoomOut = useCallback(
    () => setZoom((z) => Math.max(_MIN_ZOOM, (z ?? 1) - _ZOOM_STEP)),
    []
  );

  const currentZoom = zoom;

  // No edges: independent steps stacked vertically
  if (!hasEdges) {
    const colGap = 20;
    const nodeX = _LEFT_GUTTER;
    const colNodes = steps.map((step, index) => {
      const y = 36 + index * (_NODE_HEIGHT + colGap);
      const stepRun = stepRunMap.get(step.id);
      return { step, x: nodeX, y, stepRun };
    });

    const startEdges = colNodes.map(({ step, x, y, stepRun }, index) => ({
      key: `independent-start-${step.id}`,
      sourceX: x + _LEFT_GUTTER - 110,
      sourceY: y + _NODE_HEIGHT / 2,
      targetX: x + _LEFT_GUTTER,
      targetY: y + _NODE_HEIGHT / 2,
      status: stepRun?.status,
      label: index === 0 ? _rootTriggerLabel(scheduleType) : undefined,
    }));

    const stackContentWidth = _LEFT_GUTTER * 2 + _NODE_WIDTH + 24;
    const stackContentHeight = Math.max(
      _NODE_HEIGHT + 72,
      36 + steps.length * _NODE_HEIGHT + Math.max(0, steps.length - 1) * colGap + 12
    );

    return (
      <div className="relative min-w-0 max-w-full overflow-hidden rounded-lg border bg-muted/30">
        <_ZoomControls zoom={currentZoom} onZoomIn={zoomIn} onZoomOut={zoomOut} />
        <div className="max-h-[70vh] overflow-auto overscroll-contain p-4">
          <div
            style={{
              width: stackContentWidth * currentZoom,
              height: stackContentHeight * currentZoom,
            }}
          >
            <div
              style={{
                transform: `scale(${currentZoom})`,
                transformOrigin: "top left",
                width: stackContentWidth,
                height: stackContentHeight,
                position: "relative",
              }}
            >
              <svg
                width={stackContentWidth}
                height={stackContentHeight}
                style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
              >
                {startEdges.map(({ key, ...edgeProps }) => (
                  <WorkflowDagEdge key={key} {...edgeProps} />
                ))}
              </svg>
              {colNodes.map(({ step, x, y, stepRun }) => (
                <div
                  key={step.id}
                  style={{
                    position: "absolute",
                    left: x + _LEFT_GUTTER,
                    top: y,
                  }}
                >
                  <WorkflowDagNode
                    label={step.label}
                    taskNames={parseJson<string[]>(step.taskNames, [])}
                    status={stepRun?.status}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // With edges: dagre layout
  const nodes = steps.map((step) => {
    const node = layout!.node(step.id);
    const stepRun = stepRunMap.get(step.id);
    const taskNames = parseJson<string[]>(step.taskNames, []);
    const deps = parseJson<string[]>(step.dependsOn, []);
    return { step, node, stepRun, taskNames, isRoot: deps.length === 0 };
  });

  const edges = layout!.edges().map((e) => {
    const sourceNode = layout!.node(e.v);
    const targetNode = layout!.node(e.w);
    const targetStepRun = stepRunMap.get(e.w);
    return {
      key: `${e.v}-${e.w}`,
      sourceX: sourceNode.x + _NODE_WIDTH / 2 + _LEFT_GUTTER,
      sourceY: sourceNode.y,
      targetX: targetNode.x - _NODE_WIDTH / 2 + _LEFT_GUTTER,
      targetY: targetNode.y,
      status: targetStepRun?.status,
    };
  });

  const startEdges = nodes
    .filter((n) => n.isRoot)
    .map(({ step, node, stepRun }) => ({
      key: `start-${step.id}`,
      sourceX: node.x - _NODE_WIDTH / 2 + _LEFT_GUTTER - 110,
      sourceY: node.y,
      targetX: node.x - _NODE_WIDTH / 2 + _LEFT_GUTTER,
      targetY: node.y,
      status: stepRun?.status,
      label: _rootTriggerLabel(scheduleType),
    }));

  return (
    <div className="relative min-w-0 max-w-full overflow-hidden rounded-lg border bg-muted/30">
      <_ZoomControls zoom={currentZoom} onZoomIn={zoomIn} onZoomOut={zoomOut} />
      <div className="max-h-[70vh] overflow-auto overscroll-contain p-4">
        <div
          style={{
            width: contentWidth * currentZoom,
            height: contentHeight * currentZoom,
          }}
        >
          <div
            style={{
              width: contentWidth,
              height: contentHeight,
              position: "relative",
              transform: `scale(${currentZoom})`,
              transformOrigin: "top left",
            }}
          >
            <svg
              width={contentWidth}
              height={contentHeight}
              style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
            >
              {startEdges.map(({ key, ...edgeProps }) => (
                <WorkflowDagEdge key={key} {...edgeProps} />
              ))}
              {edges.map(({ key, ...edgeProps }) => (
                <WorkflowDagEdge key={key} {...edgeProps} />
              ))}
            </svg>
            {nodes.map(({ step, node, stepRun, taskNames, isRoot }) => (
              <div
                key={step.id}
                style={{
                  position: "absolute",
                  left: node.x - _NODE_WIDTH / 2 + _LEFT_GUTTER,
                  top: node.y - _NODE_HEIGHT / 2,
                }}
              >
                <WorkflowDagNode
                  label={step.label}
                  taskNames={taskNames}
                  status={stepRun?.status}
                />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
