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
      <line x1="14" y1="36" x2="14" y2="36" className="pv-run" />
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

const PREVIEWS: Record<string, () => React.JSX.Element> = {
  "/replay": ReplayPreview,
  "/platform": PlatformPreview,
  "/quality": QualityPreview,
  "/warehouse": WarehousePreview,
  "/runs": RunsPreview,
  "/pose": PosePreview,
  "/learn": LearnPreview,
  "/sql": SqlPreview,
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
