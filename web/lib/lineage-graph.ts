// Pure graph functions behind `components/platform/Lineage.tsx` (task 36):
// no React, no DOM, just `lineage.json`'s own shape (`groups[]`, nodes with
// `key`/`group`, edges with `from`/`to`), so they can be fed a fabricated
// graph in vitest and imported by the component unchanged. An edge's `from`
// is the upstream (parent) node and `to` the downstream (child) one, the
// same direction Dagster's `parent_keys` gave task 33's exporter.

export interface GraphNode {
  key: string;
  group: string;
}

export interface GraphEdge {
  from: string;
  to: string;
}

function parentsIndex(edges: GraphEdge[]): Map<string, string[]> {
  const index = new Map<string, string[]>();
  for (const edge of edges) {
    const list = index.get(edge.to) ?? [];
    list.push(edge.from);
    index.set(edge.to, list);
  }
  return index;
}

function childrenIndex(edges: GraphEdge[]): Map<string, string[]> {
  const index = new Map<string, string[]>();
  for (const edge of edges) {
    const list = index.get(edge.from) ?? [];
    list.push(edge.to);
    index.set(edge.from, list);
  }
  return index;
}

// Every node with a directed path of edges into `key` (its parents,
// grandparents, ...), never `key` itself. Walks `edge.from` backward from
// `edge.to === key`; swapping the two directions turns this into
// `descendants` instead, which is exactly the mutation task 36 requires
// breaking on purpose.
export function ancestors(edges: GraphEdge[], key: string): Set<string> {
  const parentsOf = parentsIndex(edges);
  const seen = new Set<string>();
  const stack = [...(parentsOf.get(key) ?? [])];
  while (stack.length > 0) {
    const node = stack.pop() as string;
    if (seen.has(node)) continue;
    seen.add(node);
    stack.push(...(parentsOf.get(node) ?? []));
  }
  return seen;
}

// The mirror of `ancestors`: every node reachable forward from `key` along
// `edge.from -> edge.to`, never `key` itself.
export function descendants(edges: GraphEdge[], key: string): Set<string> {
  const childrenOf = childrenIndex(edges);
  const seen = new Set<string>();
  const stack = [...(childrenOf.get(key) ?? [])];
  while (stack.length > 0) {
    const node = stack.pop() as string;
    if (seen.has(node)) continue;
    seen.add(node);
    stack.push(...(childrenOf.get(node) ?? []));
  }
  return seen;
}

// DFS with a recursion-stack color, the textbook way to find a cycle in a
// directed graph: a node reached while still "visiting" closes a loop.
// Returns the cycle itself (first repeated key last) or null on a genuine
// DAG. `layout()` calls this before laying anything out, because the
// left-to-right, column-per-group picture only makes sense for an acyclic
// graph in the first place.
export function findCycle(nodes: GraphNode[], edges: GraphEdge[]): string[] | null {
  const childrenOf = childrenIndex(edges);
  const state = new Map<string, "visiting" | "done">();
  const path: string[] = [];

  function visit(key: string): string[] | null {
    state.set(key, "visiting");
    path.push(key);
    for (const next of childrenOf.get(key) ?? []) {
      const nextState = state.get(next);
      if (nextState === "visiting") {
        const start = path.indexOf(next);
        return [...path.slice(start), next];
      }
      if (nextState !== "done") {
        const found = visit(next);
        if (found) return found;
      }
    }
    path.pop();
    state.set(key, "done");
    return null;
  }

  for (const node of nodes) {
    if (!state.has(node.key)) {
      const found = visit(node.key);
      if (found) return found;
    }
  }
  return null;
}

export interface LayoutNode extends GraphNode {
  col: number;
  row: number;
}

// One column per group, in `groups`' own flow order; within a column, nodes
// sorted by key, one per row, so no two nodes ever land in the same
// (col, row) cell. Throws on a cyclic graph instead of laying one out.
export function layout(groups: string[], nodes: GraphNode[], edges: GraphEdge[]): LayoutNode[] {
  const cycle = findCycle(nodes, edges);
  if (cycle) {
    throw new Error(`lineage graph has a cycle: ${cycle.join(" -> ")}`);
  }
  const result: LayoutNode[] = [];
  groups.forEach((group, col) => {
    const inGroup = [...nodes]
      .filter((n) => n.group === group)
      .sort((a, b) => a.key.localeCompare(b.key));
    inGroup.forEach((node, row) => {
      result.push({ ...node, col, row });
    });
  });
  return result;
}
