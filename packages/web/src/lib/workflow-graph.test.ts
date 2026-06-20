import { describe, it, expect } from "vitest";
import { nodesToFlow, wouldCreateCycle, autoLayout } from "./workflow-graph";

const node = (id: string, deps: string[], pos?: { x: number; y: number }) => ({
  id, label: id, taskName: "tasks." + id,
  args: null, kwargs: null, queue: null,
  dependsOn: JSON.stringify(deps), condition: "all_succeeded",
  timeoutSeconds: null, positionX: null, positionY: null,
  position: pos ?? null,
});

describe("nodesToFlow", () => {
  it("builds one edge per dependency (source=dep, target=node)", () => {
    const { flowNodes, flowEdges } = nodesToFlow([node("a", []), node("b", ["a"])]);
    expect(flowNodes).toHaveLength(2);
    expect(flowEdges).toEqual([{ id: "a->b", source: "a", target: "b" }]);
  });

  it("uses stored position when present", () => {
    const { flowNodes } = nodesToFlow([node("a", [], { x: 10, y: 20 })]);
    expect(flowNodes[0].position).toEqual({ x: 10, y: 20 });
  });

  it("maps run status by nodeId", () => {
    const runs = [{ id: "r1", nodeId: "a", label: "a", taskName: "tasks.a",
      celeryTaskId: null, status: "succeeded", error: null,
      startedAt: null, finishedAt: null }];
    const { flowNodes } = nodesToFlow([node("a", [])], runs as any);
    expect(flowNodes[0].data.status).toBe("succeeded");
  });
});

describe("wouldCreateCycle", () => {
  const edges = [{ id: "a->b", source: "a", target: "b" }];
  it("detects a back-edge cycle", () => {
    expect(wouldCreateCycle(edges, "b", "a")).toBe(true);
  });
  it("detects self-loop", () => {
    expect(wouldCreateCycle(edges, "a", "a")).toBe(true);
  });
  it("allows a valid new edge", () => {
    expect(wouldCreateCycle(edges, "b", "c")).toBe(false);
  });
});

describe("autoLayout", () => {
  it("assigns a position to every node", () => {
    const { flowNodes, flowEdges } = nodesToFlow([node("a", []), node("b", ["a"])]);
    const laid = autoLayout(flowNodes, flowEdges);
    expect(laid).toHaveLength(2);
    for (const n of laid) {
      expect(typeof n.position.x).toBe("number");
      expect(typeof n.position.y).toBe("number");
    }
  });
});
