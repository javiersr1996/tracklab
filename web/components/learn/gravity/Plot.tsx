import type { ReactNode } from "react";

// The colours every lesson draws with on `--canvas`, each a token of globals.css; the ratios are
// WCAG's on #030712, and tests/learn-figures.test.ts checks every stroke and fill the figures
// render (3:1 or more) and that each colour is still its token.
export const CANVAS = "#030712";
export const INK = {
  data: "#00e5ff", // --neon, 13.1:1: the samples and what is fitted to them, the cyan of /engineering/quality
  standard: "#ff3ea5", // --neon-alt, 6.2:1: 9.80665 m/s², the magenta of /engineering/quality
  probe: "#ffffff", // --canvas-hi, 20.1:1: what the reader moves
  axis: "#64748b", // --canvas-edge, 4.2:1
} as const;

export interface Axis {
  min: number;
  max: number;
  ticks: readonly number[];
  format: (v: number) => string;
  label: string;
}

export interface Scale {
  x: (v: number) => number;
  y: (v: number) => number;
}

export const PLOT_W = 640;
const PAD = 16;

// Ticks every `step` from the first multiple of it at or above `min` to `max`.
export function ticks(min: number, max: number, step: number): number[] {
  const out: number[] = [];
  for (let k = Math.ceil(min / step - 1e-9); k * step <= max + 1e-9; k++) out.push(Number((k * step).toFixed(6)));
  return out;
}

// A minus sign, not a hyphen, on the axes.
export const signed = (v: number, digits: number) => v.toFixed(digits).replace("-", "−");

// A plot on the canvas: the marks in SVG, the ticks and the axis labels in HTML, so they keep the
// text size at any width. The SVG fills a box whose height globals.css sets by `size` (taller than
// the width alone would give on a phone), so the viewBox stretches: a tick at p % of the viewBox
// sits at p % of the box, strokes keep their width (non-scaling) and dots are `Dot`s, not circles.
const VIEW_H = 300;

export function Plot({
  x,
  y,
  size,
  label,
  children,
}: {
  x: Axis;
  y: Axis;
  size: "tall" | "short";
  label: string;
  children: (s: Scale) => ReactNode;
}) {
  const height = VIEW_H;
  const sx = (v: number) => PAD + ((v - x.min) / (x.max - x.min)) * (PLOT_W - 2 * PAD);
  const sy = (v: number) => height - PAD - ((v - y.min) / (y.max - y.min)) * (height - 2 * PAD);
  return (
    <div className={`learn-plot learn-plot-${size}`}>
      {y.label ? <p className="learn-plot-label">{y.label}</p> : null}
      <div className="learn-plot-grid">
        <div className="learn-plot-yticks" aria-hidden="true">
          {y.ticks.map((v) => (
            <span key={v} style={{ top: `${(sy(v) / height) * 100}%` }}>
              {y.format(v)}
            </span>
          ))}
        </div>
        <svg viewBox={`0 0 ${PLOT_W} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
          {children({ x: sx, y: sy })}
        </svg>
        <div className="learn-plot-xticks" aria-hidden="true">
          {x.ticks.map((v) => (
            <span key={v} style={{ left: `${(sx(v) / PLOT_W) * 100}%` }}>
              {x.format(v)}
            </span>
          ))}
        </div>
      </div>
      <p className="learn-plot-label learn-plot-xlabel">{x.label}</p>
    </div>
  );
}

// A round mark of radius r px that stays round in a stretched viewBox: a stroke of zero length
// with round caps, its width in screen pixels.
export function Dot({ x, y, r, color }: { x: number; y: number; r: number; color: string }) {
  return <path d={`M${x.toFixed(1)} ${y.toFixed(1)}h0`} stroke={color} strokeWidth={2 * r} strokeLinecap="round" vectorEffect="non-scaling-stroke" />;
}

// A legend on the canvas: a swatch in the mark's colour, then its name.
export function Legend({ items }: { items: readonly { color: string; label: string; dot?: boolean; dashed?: boolean }[] }) {
  return (
    <ul className="learn-legend">
      {items.map((it) => (
        <li key={it.label}>
          <span
            className={["learn-swatch", it.dot && "learn-swatch-dot", it.dashed && "learn-swatch-dashed"].filter(Boolean).join(" ")}
            style={{ color: it.color }}
            aria-hidden="true"
          />
          {it.label}
        </li>
      ))}
    </ul>
  );
}
