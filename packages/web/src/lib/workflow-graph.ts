import dagre from "@dagrejs/dagre";
import type { WorkflowNode, NodeRun } from "@/lib/types";
import { parseJson } from "@/lib/workflow-utils";

export interface FlowNode {
  id: string;
  position: { x: number; y: number };
  data: { label: string; taskName: string; status?: string };
}
export interface FlowEdge {
  id: string;
  source: string;
  target: string;
}

const NODE_W = 280;
const NODE_H = 100;

export function nodesToFlow(
  nodes: WorkflowNode[],
  runs?: NodeRun[],
): { flowNodes: FlowNode[]; flowEdges: FlowEdge[] } {
  const statusByNodeId = new Map<string, string>();
  for (const r of runs ?? []) statusByNodeId.set(r.nodeId, r.status);

  const flowNodes: FlowNode[] = nodes.map((n) => {
    // Prefer explicit position object, then fall back to positionX/Y columns, then origin
    let position: { x: number; y: number };
    if (n.position != null) {
      position = n.position;
    } else if (n.positionX != null && n.positionY != null) {
      position = { x: n.positionX, y: n.positionY };
    } else {
      position = { x: 0, y: 0 };
    }
    return {
      id: n.id,
      position,
      data: { label: n.label, taskName: n.taskName, status: statusByNodeId.get(n.id) },
    };
  });

  const flowEdges: FlowEdge[] = [];
  for (const n of nodes) {
    for (const dep of parseJson<string[]>(n.dependsOn, [])) {
      flowEdges.push({ id: `${dep}->${n.id}`, source: dep, target: n.id });
    }
  }
  return { flowNodes, flowEdges };
}

export function wouldCreateCycle(
  edges: FlowEdge[],
  source: string,
  target: string,
): boolean {
  if (source === target) return true;
  // Adding source->target creates a cycle iff source is already reachable from target
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    const list = adj.get(e.source) ?? [];
    list.push(e.target);
    adj.set(e.source, list);
  }
  const stack = [target];
  const seen = new Set<string>();
  while (stack.length) {
    const cur = stack.pop()!;
    if (cur === source) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const nxt of adj.get(cur) ?? []) stack.push(nxt);
  }
  return false;
}

export function autoLayout(
  flowNodes: FlowNode[],
  flowEdges: FlowEdge[],
): FlowNode[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 80 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of flowNodes) g.setNode(n.id, { width: NODE_W, height: NODE_H });
  for (const e of flowEdges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return flowNodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}
