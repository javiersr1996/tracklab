"use client";

import { useMemo, useState } from "react";
import { ancestors, descendants, layout } from "../../lib/lineage-graph";
import type { LineageData, LineageNode } from "../../lib/platform";

// One column per group in `lineage.json`'s own flow order, nodes sorted by
// key within a column (task 36): a hand-written SVG, no charting library,
// wrapped in its own horizontally-scrolling box so a phone-width page never
// gets a horizontal scrollbar of its own (bronze's 43 nodes and their long
// keys make the graph far wider than any phone). Hovering or clicking a
// node calls the same `ancestors`/`descendants` the vitest suite exercises
// on a fabricated graph, marking every node in the closure `data-lit`
// ("ancestor" or "descendant") and the node itself `data-selected`, so
// Playwright can assert the exact closure by attribute instead of a pixel.
const ROW_HEIGHT = 24;
const NODE_HEIGHT = 16;
const COL_GAP = 56;
const CHAR_WIDTH = 6.2;
const MIN_COL_WIDTH = 120;
const PAD_X = 16;
const PAD_TOP = 28;
// The SVG is drawn in the units above and shown 1.5 times larger, so the 8-unit node
// labels and badges render at 12 px.
const SCALE = 1.5;

const SCHEMA_COLOR: Record<LineageNode["schema"], string> = {
  frozen: "#4ea1f2",
  code: "#e0883a",
  dbt: "#7ec699",
  none: "#98a2ab",
};

interface Positioned {
  key: string;
  group: string;
  col: number;
  row: number;
  x: number;
  y: number;
  halfWidth: number;
}

function buildPositions(lineage: LineageData): { positions: Positioned[]; width: number; height: number } {
  const grid = layout(lineage.groups, lineage.nodes, lineage.edges);

  const colWidths = lineage.groups.map((group) => {
    const keys = lineage.nodes.filter((n) => n.group === group).map((n) => n.key);
    const maxLen = keys.reduce((m, k) => Math.max(m, k.length), 0);
    return Math.max(MIN_COL_WIDTH, maxLen * CHAR_WIDTH + PAD_X * 2);
  });
  const colStart = colWidths.reduce<number[]>((acc, w, i) => {
    acc.push(i === 0 ? 0 : acc[i - 1] + colWidths[i - 1] + COL_GAP);
    return acc;
  }, []);
  const maxRows = lineage.groups.reduce((m, group) => {
    const count = lineage.nodes.filter((n) => n.group === group).length;
    return Math.max(m, count);
  }, 0);

  const positions: Positioned[] = grid.map((g) => ({
    key: g.key,
    group: g.group,
    col: g.col,
    row: g.row,
    x: colStart[g.col] + colWidths[g.col] / 2,
    y: PAD_TOP + g.row * ROW_HEIGHT + ROW_HEIGHT / 2,
    halfWidth: colWidths[g.col] / 2 - PAD_X / 2,
  }));

  const width = colStart[colStart.length - 1] + colWidths[colWidths.length - 1] + PAD_X;
  const height = PAD_TOP + maxRows * ROW_HEIGHT + PAD_X;
  return { positions, width, height };
}

function edgePath(a: Positioned, b: Positioned): string {
  const forward = b.col > a.col;
  const x1 = a.x + a.halfWidth;
  const y1 = a.y;
  const x2 = forward ? b.x - b.halfWidth : b.x + b.halfWidth;
  const y2 = b.y;
  const dx = Math.max(Math.abs(x2 - x1) * 0.5, 30);
  const sign = forward ? 1 : -1;
  const c1x = x1 + sign * dx;
  const c2x = x2 - sign * dx;
  return `M ${x1},${y1} C ${c1x},${y1} ${c2x},${y2} ${x2},${y2}`;
}

function litDirection(key: string, up: Set<string>, down: Set<string>): "ancestor" | "descendant" | undefined {
  if (up.has(key)) return "ancestor";
  if (down.has(key)) return "descendant";
  return undefined;
}

export function Lineage({ lineage }: { lineage: LineageData }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const activeKey = hovered ?? pinned;

  const { positions, width, height } = useMemo(() => buildPositions(lineage), [lineage]);
  const positionByKey = useMemo(() => new Map(positions.map((p) => [p.key, p])), [positions]);
  const nodeByKey = useMemo(() => new Map(lineage.nodes.map((n) => [n.key, n])), [lineage]);

  const up = useMemo(
    () => (activeKey ? ancestors(lineage.edges, activeKey) : new Set<string>()),
    [lineage, activeKey],
  );
  const down = useMemo(
    () => (activeKey ? descendants(lineage.edges, activeKey) : new Set<string>()),
    [lineage, activeKey],
  );

  const selectNode = (key: string) => setPinned((prev) => (prev === key ? null : key));

  return (
    <figure className="lineage">
      <div className="lineage-scroll">
        <svg
          width={width * SCALE}
          height={height * SCALE}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Dagster asset graph, ${lineage.nodes.length} nodes, ${lineage.edges.length} edges`}
        >
          <g className="lineage-edges">
            {lineage.edges.map((edge) => {
              const a = positionByKey.get(edge.from);
              const b = positionByKey.get(edge.to);
              if (!a || !b) return null;
              const litFrom = litDirection(edge.from, up, down);
              const litTo = litDirection(edge.to, up, down);
              const bothInClosure =
                (edge.from === activeKey || litFrom === "ancestor") &&
                (edge.to === activeKey || litTo === "ancestor")
                  ? "ancestor"
                  : (edge.from === activeKey || litFrom === "descendant") &&
                      (edge.to === activeKey || litTo === "descendant")
                    ? "descendant"
                    : undefined;
              return (
                <path
                  key={`${edge.from}->${edge.to}`}
                  data-edge={`${edge.from}->${edge.to}`}
                  data-lit={bothInClosure}
                  d={edgePath(a, b)}
                  fill="none"
                />
              );
            })}
          </g>
          <g className="lineage-nodes">
            {positions.map((p) => {
              const node = nodeByKey.get(p.key);
              const selected = p.key === activeKey;
              const lit = !selected ? litDirection(p.key, up, down) : undefined;
              return (
                <g
                  key={p.key}
                  data-node={p.key}
                  data-selected={selected ? "true" : undefined}
                  data-lit={lit}
                  className="lineage-node"
                  tabIndex={0}
                  role="button"
                  aria-label={p.key}
                  transform={`translate(${p.x}, ${p.y})`}
                  onMouseEnter={() => setHovered(p.key)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(p.key)}
                  onBlur={() => setHovered(null)}
                  onClick={() => selectNode(p.key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      selectNode(p.key);
                    }
                  }}
                >
                  <rect
                    x={-p.halfWidth}
                    y={-NODE_HEIGHT / 2}
                    width={p.halfWidth * 2}
                    height={NODE_HEIGHT}
                    rx={3}
                    fill={SCHEMA_COLOR[node?.schema ?? "none"]}
                    stroke={node?.kind === "external" ? "#f2f2f2" : "none"}
                    strokeDasharray={node?.kind === "external" ? "3 2" : undefined}
                  />
                  <text x={0} y={0} textAnchor="middle" dominantBaseline="central">
                    {p.key}
                  </text>
                  {node && (node.dbt_tests ?? 0) > 0 && (
                    <text
                      className="lineage-test-badge"
                      x={p.halfWidth - 2}
                      y={-NODE_HEIGHT / 2 - 1.5}
                      textAnchor="end"
                    >
                      {node.dbt_tests}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <figcaption className="lineage-legend">
        <span>
          <i className="lineage-swatch" style={{ background: SCHEMA_COLOR.frozen }} /> frozen schema
        </span>
        <span>
          <i className="lineage-swatch" style={{ background: SCHEMA_COLOR.code }} /> schema in code
        </span>
        <span>
          <i className="lineage-swatch" style={{ background: SCHEMA_COLOR.dbt }} /> dbt-owned schema
        </span>
        <span>
          <i className="lineage-swatch lineage-swatch-badge">#</i> dbt tests (dbt models,
          count above the node)
        </span>
      </figcaption>
    </figure>
  );
}
