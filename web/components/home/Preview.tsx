import type { CSSProperties } from "react";

// One small moving picture per section card of the home (task 107): inline SVG, shapes only
// (an SVG text would be under the 16 px floor), animated by CSS in globals.css under
// `prefers-reduced-motion: no-preference`, so a reader who asked for stillness gets the last
// frame. Nothing here is data: no fetch, no figure, a sketch of what the section does.
const VIEW = "0 0 120 72";

// `--i` staggers the animation of the k-th mark; the CSS multiplies it by a delay.
const nth = (k: number) => ({ "--i": k }) as CSSProperties;

function ReplayPreview() {
  return (
    <svg viewBox={VIEW} className="pv pv-replay">
      <rect x="4" y="6" width="112" height="60" className="pv-line" />
      <line x1="60" y1="6" x2="60" y2="66" className="pv-line" />
      <circle cx="60" cy="36" r="9" className="pv-line" />
      <circle r="3.5" className="pv-ink pv-mark pv-mark-a" />
      <circle r="3.5" className="pv-alt pv-mark pv-mark-b" />
      <circle r="3.5" className="pv-alt pv-mark pv-mark-c" />
      <circle r="2" className="pv-ball pv-mark pv-mark-ball" />
    </svg>
  );
}

function PlatformPreview() {
  const xs = [10, 30, 50, 70, 90, 110];
  return (
    <svg viewBox={VIEW} className="pv pv-platform">
      <line x1="10" y1="36" x2="110" y2="36" className="pv-line" />
      {xs.map((x, k) => (
        <circle key={x} cx={x} cy="36" r="4" className="pv-node" style={nth(k)} />
      ))}
      <circle cy="36" r="2.5" className="pv-ball pv-pulse" />
    </svg>
  );
}

function QualityPreview() {
  return (
    <svg viewBox={VIEW} className="pv pv-quality">
      <rect x="4" y="30" width="112" height="12" className="pv-band" />
      <polyline
        points="4,38 14,34 24,39 34,33 44,37 54,31 64,36 74,40 84,34 94,37 104,32 116,36"
        className="pv-ink pv-signal"
      />
      <line x1="4" y1="8" x2="4" y2="64" className="pv-sweep" />
    </svg>
  );
}

function WarehousePreview() {
  const cells = Array.from({ length: 12 }, (_, k) => k);
  return (
    <svg viewBox={VIEW} className="pv pv-warehouse">
      {cells.map((k) => (
        <rect
          key={k}
          x={6 + (k % 4) * 28}
          y={10 + Math.floor(k / 4) * 18}
          width="24"
          height="12"
          className="pv-cell"
          style={nth(k)}
        />
      ))}
    </svg>
  );
}

function RunsPreview() {
  return (
    <svg viewBox={VIEW} className="pv pv-runs">
      <line x1="14" y1="36" x2="108" y2="36" className="pv-run" />
      <circle cx="60" cy="20" r="3.5" className="pv-alt" />
      <circle cx="78" cy="48" r="3.5" className="pv-alt" />
      <circle cx="96" cy="30" r="3.5" className="pv-alt" />
      <circle cx="14" cy="36" r="3.5" className="pv-ink pv-runner" />
    </svg>
  );
}

function PosePreview() {
  return (
    <svg viewBox={VIEW} className="pv pv-pose">
      <circle cx="60" cy="14" r="6" className="pv-ink" />
      <line x1="60" y1="20" x2="60" y2="42" className="pv-bone" />
      <line x1="60" y1="24" x2="60" y2="40" className="pv-bone pv-arm pv-arm-l" />
      <line x1="60" y1="24" x2="60" y2="40" className="pv-bone pv-arm pv-arm-r" />
      <line x1="60" y1="42" x2="60" y2="62" className="pv-bone pv-leg pv-leg-l" />
      <line x1="60" y1="42" x2="60" y2="62" className="pv-bone pv-leg pv-leg-r" />
    </svg>
  );
}

function LearnPreview() {
  return (
    <svg viewBox={VIEW} className="pv pv-learn">
      <line x1="8" y1="62" x2="112" y2="62" className="pv-line" />
      <path d="M 12 60 Q 60 -20 108 60" className="pv-ink pv-arc" />
      <circle r="3" className="pv-ball pv-fall" />
    </svg>
  );
}

function SqlPreview() {
  const lines = [
    { w: 58, key: true },
    { w: 40, key: false },
    { w: 74, key: false },
    { w: 32, key: true },
    { w: 50, key: false },
  ];
  return (
    <svg viewBox={VIEW} className="pv pv-sql">
      {lines.map((l, k) => (
        <rect
          key={k}
          x="8"
          y={10 + k * 11}
          width={l.w}
          height="5"
          rx="1"
          className={l.key ? "pv-code pv-code-key" : "pv-code"}
          style={nth(k)}
        />
      ))}
      <rect x="60" y="54" width="5" height="7" className="pv-cursor" />
    </svg>
  );
}

// A half court seen from above, hoop at the foot, and a few hexagons lighting up in turn: a sketch
// of the atlas, not its data (the cells and their tones here are drawn, not read).
function EuroleaguePreview() {
  const hexes = [
    { x: 60, y: 58, r: 6, tone: "pv-hex-hi" },
    { x: 49, y: 52, r: 4.5, tone: "pv-hex-mid" },
    { x: 71, y: 52, r: 4.5, tone: "pv-hex-lo" },
    { x: 32, y: 34, r: 5, tone: "pv-hex-hi" },
    { x: 88, y: 34, r: 5, tone: "pv-hex-mid" },
    { x: 60, y: 22, r: 5.5, tone: "pv-hex-hi" },
    { x: 44, y: 26, r: 3.5, tone: "pv-hex-lo" },
    { x: 76, y: 26, r: 3.5, tone: "pv-hex-hi" },
  ];
  const corner = (x: number, y: number, r: number) =>
    [-90, -30, 30, 90, 150, 210]
      .map((d) => `${(x + r * Math.cos((d * Math.PI) / 180)).toFixed(1)},${(y + r * Math.sin((d * Math.PI) / 180)).toFixed(1)}`)
      .join(" ");
  return (
    <svg viewBox={VIEW} className="pv pv-euroleague">
      <rect x="10" y="4" width="100" height="64" className="pv-line" />
      <path d="M 18 68 V 58 A 42 42 0 0 1 102 58 V 68" className="pv-line" />
      <rect x="47" y="44" width="26" height="24" className="pv-line" />
      {hexes.map((h, k) => (
        <polygon key={k} points={corner(h.x, h.y, h.r)} className={`pv-hex ${h.tone}`} style={nth(k)} />
      ))}
    </svg>
  );
}

// A pitch from above and the squares one group fills, brighter where it spends more time, lighting
// from the busiest outwards: the idea of the heat map, not its data (the squares here are drawn).
function OccupancyPreview() {
  const cells = [
    { c: 2, r: 1, tone: "pv-heat-hi", ring: 0 },
    { c: 2, r: 2, tone: "pv-heat-hi", ring: 0 },
    { c: 1, r: 1, tone: "pv-heat-mid", ring: 1 },
    { c: 1, r: 2, tone: "pv-heat-mid", ring: 1 },
    { c: 3, r: 1, tone: "pv-heat-mid", ring: 1 },
    { c: 3, r: 2, tone: "pv-heat-mid", ring: 1 },
    { c: 2, r: 0, tone: "pv-heat-mid", ring: 1 },
    { c: 2, r: 3, tone: "pv-heat-mid", ring: 1 },
    { c: 0, r: 1, tone: "pv-heat-lo", ring: 2 },
    { c: 0, r: 2, tone: "pv-heat-lo", ring: 2 },
    { c: 1, r: 0, tone: "pv-heat-lo", ring: 2 },
    { c: 3, r: 0, tone: "pv-heat-lo", ring: 2 },
    { c: 1, r: 3, tone: "pv-heat-lo", ring: 2 },
    { c: 3, r: 3, tone: "pv-heat-lo", ring: 2 },
    { c: 4, r: 1, tone: "pv-heat-lo", ring: 2 },
    { c: 4, r: 2, tone: "pv-heat-lo", ring: 2 },
    { c: 5, r: 1, tone: "pv-heat-lo", ring: 3 },
  ];
  return (
    <svg viewBox={VIEW} className="pv pv-occupancy">
      {cells.map((cell, k) => (
        <rect
          key={k}
          x={4 + cell.c * 14}
          y={6 + cell.r * 15}
          width="14"
          height="15"
          className={`pv-heat ${cell.tone}`}
          style={nth(cell.ring)}
        />
      ))}
      <rect x="4" y="6" width="112" height="60" className="pv-line" />
      <line x1="60" y1="6" x2="60" y2="66" className="pv-line" />
      <circle cx="60" cy="36" r="9" className="pv-line" />
    </svg>
  );
}

// Four position groups, a row each: the middle half as a box that opens out, the median a tick, a
// few players as dots. The rows are drawn, not read.
function PositionsPreview() {
  const rows = [
    { y: 15, lo: 30, hi: 62, med: 44, dots: [24, 50, 70] },
    { y: 30, lo: 50, hi: 86, med: 70, dots: [42, 78, 96] },
    { y: 45, lo: 40, hi: 76, med: 56, dots: [34, 64, 84] },
    { y: 60, lo: 20, hi: 52, med: 34, dots: [14, 44, 60] },
  ];
  return (
    <svg viewBox={VIEW} className="pv pv-positions">
      {rows.map((r, k) => (
        <g key={r.y} style={nth(k)}>
          <line x1="8" y1={r.y} x2="112" y2={r.y} className="pv-line" />
          <rect x={r.lo} y={r.y - 4} width={r.hi - r.lo} height="8" className="pv-box" />
          {r.dots.map((x) => (
            <circle key={x} cx={x} cy={r.y} r="1.6" className="pv-dot" />
          ))}
          <line x1={r.med} y1={r.y - 6} x2={r.med} y2={r.y + 6} className="pv-median" />
        </g>
      ))}
    </svg>
  );
}

// Two players side by side, a bar each way for each statistic, growing out from the middle: the
// comparison's shape, not its figures.
function ScoutingPreview() {
  const rows = [
    { a: 34, b: 22 },
    { a: 18, b: 40 },
    { a: 44, b: 30 },
    { a: 26, b: 36 },
    { a: 38, b: 14 },
  ];
  return (
    <svg viewBox={VIEW} className="pv pv-scouting">
      {rows.map((r, k) => (
        <g key={k} style={nth(k)}>
          <rect x={60 - r.a} y={9 + k * 12} width={r.a} height="6" className="pv-bar pv-bar-a" />
          <rect x="60" y={9 + k * 12} width={r.b} height="6" className="pv-bar pv-bar-b" />
        </g>
      ))}
      <line x1="60" y1="4" x2="60" y2="68" className="pv-line" />
    </svg>
  );
}

const PREVIEWS: Record<string, () => React.JSX.Element> = {
  "/tracking/replay": ReplayPreview,
  "/engineering": PlatformPreview,
  "/engineering/quality": QualityPreview,
  "/warehouse": WarehousePreview,
  "/tracking/runs": RunsPreview,
  "/tracking/pose": PosePreview,
  "/learn": LearnPreview,
  "/sql": SqlPreview,
  "/euroleague": EuroleaguePreview,
  "/tracking/occupancy": OccupancyPreview,
  "/warehouse/positions": PositionsPreview,
  "/warehouse/scouting": ScoutingPreview,
};

export function Preview({ href }: { href: string }) {
  const Picture = PREVIEWS[href];
  if (!Picture) return null;
  return (
    <div className="card-preview" aria-hidden="true">
      <Picture />
    </div>
  );
}
