import { describe, expect, it } from "vitest";
import {
  ancestors,
  descendants,
  findCycle,
  layout,
  type GraphEdge,
  type GraphNode,
} from "../lib/lineage-graph";

// A fabricated five-node, three-group DAG, not `lineage.json` itself, so
// these tests catch a broken `ancestors`/`descendants`/`layout` even if the
// real graph happens to hide the bug: two roots in g1 feed a shared hub in
// g2 that has a sibling with its own, separate root; both g2 nodes feed the
// single g3 sink.
//
//   a1 -\           /-> c1
//        b1 --------
//   a2 -/
//   b2 -------------/
// Deliberately out of key order within each column (a2 before a1, b2
// before b1): a `layout()` that forgot to sort would still pass a test
// fixture already listed in key order, so this fixture is not.
const NODES: GraphNode[] = [
  { key: "a2", group: "g1" },
  { key: "a1", group: "g1" },
  { key: "b2", group: "g2" },
  { key: "b1", group: "g2" },
  { key: "c1", group: "g3" },
];
const EDGES: GraphEdge[] = [
  { from: "a1", to: "b1" },
  { from: "a2", to: "b1" },
  { from: "b1", to: "c1" },
  { from: "b2", to: "c1" },
];
const GROUPS = ["g1", "g2", "g3"];

// Mutation checked by hand: swapping `edge.to`/`edge.from` inside `ancestors`
// (so it walks `childrenIndex` instead of `parentsIndex`) turns this into
// `descendants` and fails both assertions below (`ancestors(edges, "c1")`
// comes back empty, since nothing points forward from "c1"). Restored byte
// for byte afterwards; this is also the mutation task 36 asks to prove
// breaks the e2e closure test on the real graph.
describe("ancestors", () => {
  it("walks every parent transitively, never the node itself", () => {
    expect(ancestors(EDGES, "c1")).toEqual(new Set(["b1", "b2", "a1", "a2"]));
    expect(ancestors(EDGES, "b1")).toEqual(new Set(["a1", "a2"]));
  });

  it("is empty for a root with no parents", () => {
    expect(ancestors(EDGES, "a1")).toEqual(new Set());
  });
});

describe("descendants", () => {
  it("walks every child transitively, never the node itself", () => {
    expect(descendants(EDGES, "a1")).toEqual(new Set(["b1", "c1"]));
    expect(descendants(EDGES, "b2")).toEqual(new Set(["c1"]));
  });

  it("is empty for a sink with no children", () => {
    expect(descendants(EDGES, "c1")).toEqual(new Set());
  });
});

// Mutation checked by hand: dropping the `.sort(...)` call in `layout` (so
// nodes keep insertion order instead of key order) fails
// `sorts nodes by key within a column` on this fixture, since NODES lists
// "a2"/"b2" before "a1"/"b1" in each column. Restored byte for byte.
describe("layout", () => {
  it("puts one column per group, in the groups' own order", () => {
    const positions = layout(GROUPS, NODES, EDGES);
    const colOf = new Map(positions.map((p) => [p.key, p.col]));
    expect(colOf.get("a1")).toBe(0);
    expect(colOf.get("a2")).toBe(0);
    expect(colOf.get("b1")).toBe(1);
    expect(colOf.get("b2")).toBe(1);
    expect(colOf.get("c1")).toBe(2);
  });

  it("sorts nodes by key within a column", () => {
    const positions = layout(GROUPS, NODES, EDGES);
    const rowOf = new Map(positions.map((p) => [p.key, p.row]));
    expect(rowOf.get("a1")).toBe(0);
    expect(rowOf.get("a2")).toBe(1);
    expect(rowOf.get("b1")).toBe(0);
    expect(rowOf.get("b2")).toBe(1);
  });

  it("never puts two nodes in the same (col, row) cell", () => {
    const positions = layout(GROUPS, NODES, EDGES);
    const cells = positions.map((p) => `${p.col},${p.row}`);
    expect(new Set(cells).size).toBe(cells.length);
  });
});

// Mutation checked by hand: returning `null` unconditionally from
// `findCycle` (skipping the DFS body) fails `detects a fabricated cycle`
// directly, and also makes `layout` stop throwing on the cyclic fixture in
// `layout refuses a cyclic graph`, since it never sees anything to throw on.
// Both restored afterwards.
describe("cycle detection", () => {
  const cyclicNodes: GraphNode[] = [
    { key: "x", group: "g1" },
    { key: "y", group: "g1" },
    { key: "z", group: "g1" },
  ];
  const cyclicEdges: GraphEdge[] = [
    { from: "x", to: "y" },
    { from: "y", to: "z" },
    { from: "z", to: "x" },
  ];

  it("returns null on a genuine DAG", () => {
    expect(findCycle(NODES, EDGES)).toBeNull();
  });

  it("detects a fabricated cycle", () => {
    const cycle = findCycle(cyclicNodes, cyclicEdges);
    expect(cycle).not.toBeNull();
    // Whichever node the DFS starts from, the cycle it reports visits all
    // three before closing the loop back on itself.
    expect(new Set(cycle)).toEqual(new Set(["x", "y", "z"]));
    expect(cycle?.[0]).toBe(cycle?.[cycle.length - 1]);
  });

  it("layout refuses a cyclic graph instead of laying one out", () => {
    expect(() => layout(["g1"], cyclicNodes, cyclicEdges)).toThrow(/cycle/i);
  });
});
