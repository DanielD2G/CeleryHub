import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { WorkflowNode, NodeRun } from "@/lib/types";
import { CanvasNode } from "./canvas-node";
import { CanvasEdge } from "./canvas-edge";
import { nodesToFlow, wouldCreateCycle } from "@/lib/workflow-graph";

const nodeTypes = { canvas: CanvasNode };
const edgeTypes = { canvas: CanvasEdge };

export interface WorkflowCanvasProps {
  nodes: WorkflowNode[];
  runs?: NodeRun[];
  readOnly?: boolean;
  onChange?: (nodes: WorkflowNode[]) => void;
  onSelectNode?: (id: string | null) => void;
  onInsertNode?: (edgeId: string) => void;
}

/** Rebuild WorkflowNode[] from current flow state, preserving non-position/dependsOn fields. */
export function flowToWorkflowNodes(
  flowNodes: Node[],
  flowEdges: Edge[],
  base: WorkflowNode[],
): WorkflowNode[] {
  const depsByTarget = new Map<string, string[]>();
  for (const e of flowEdges) {
    const list = depsByTarget.get(e.target) ?? [];
    list.push(e.source);
    depsByTarget.set(e.target, list);
  }
  return flowNodes.map((n) => {
    const baseNode = base.find((b) => b.id === n.id)!;
    return {
      ...baseNode,
      position: { x: n.position.x, y: n.position.y },
      dependsOn: JSON.stringify(depsByTarget.get(n.id) ?? []),
    };
  });
}

function _Inner(props: WorkflowCanvasProps) {
  const { readOnly, onChange, onSelectNode, onInsertNode } = props;

  const initial = useMemo(() => nodesToFlow(props.nodes, props.runs), []);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(
    initial.flowNodes.map((n) => ({
      ...n,
      type: "canvas" as const,
    })),
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    initial.flowEdges.map((e) => ({
      ...e,
      type: "canvas" as const,
      data: readOnly ? {} : { onInsert: onInsertNode },
    })),
  );

  /** Emit onChange with the latest ns/es. Avoids stale closure issues. */
  const emit = useCallback(
    (ns: Node[], es: Edge[]) => {
      if (!onChange) return;
      onChange(flowToWorkflowNodes(ns, es, props.nodes));
    },
    [onChange, props.nodes],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      // Apply changes and emit — position changes (drags) propagate here
      setNodes((ns) => {
        const next = applyNodeChanges(changes, ns);
        // Only emit on position/remove changes that settle
        const hasMutation = changes.some(
          (c) => c.type === "remove" || (c.type === "position" && !c.dragging),
        );
        if (hasMutation) {
          // Use functional form of edges to get current value
          emit(next, edges);
        }
        return next;
      });
      onNodesChange(changes);
    },
    [onNodesChange, setNodes, emit, edges],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      // Apply changes and emit — edge deletions propagate here
      setEdges((es) => {
        const next = applyEdgeChanges(changes, es);
        const hasMutation = changes.some((c) => c.type === "remove" || c.type === "add");
        if (hasMutation) {
          emit(nodes, next);
        }
        return next;
      });
      onEdgesChange(changes);
    },
    [onEdgesChange, setEdges, emit, nodes],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      if (!c.source || !c.target) return;
      if (wouldCreateCycle(edges, c.source, c.target)) return;
      setEdges((es) => {
        const next = addEdge(
          { ...c, type: "canvas" as const, data: { onInsert: onInsertNode } },
          es,
        );
        emit(nodes, next);
        return next;
      });
    },
    [edges, nodes, emit, onInsertNode, setEdges],
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={readOnly ? onNodesChange : handleNodesChange}
      onEdgesChange={readOnly ? onEdgesChange : handleEdgesChange}
      onNodeDragStop={(_, n) => {
        // Drag stop: emit with latest state including dragged node position
        setNodes((ns) => {
          const updated = ns.map((fn) =>
            fn.id === n.id ? { ...fn, position: n.position } : fn,
          );
          emit(updated, edges);
          return updated;
        });
      }}
      onConnect={readOnly ? undefined : onConnect}
      onNodeClick={(_, n) => onSelectNode?.(n.id)}
      onPaneClick={() => onSelectNode?.(null)}
      nodesDraggable={!readOnly}
      nodesConnectable={!readOnly}
      elementsSelectable
      fitView
    >
      <Background />
      <Controls />
    </ReactFlow>
  );
}

export function WorkflowCanvas(props: WorkflowCanvasProps) {
  return (
    <div className="h-[560px] w-full rounded-md border">
      <ReactFlowProvider>
        <_Inner {...props} />
      </ReactFlowProvider>
    </div>
  );
}
