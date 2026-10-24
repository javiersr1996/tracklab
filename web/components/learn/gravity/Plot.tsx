import type { ReactNode } from "react";

// The colours lesson 1 draws with on `--canvas`; each is 3:1 or more against it, and
// tests/learn-figures.test.ts checks every stroke and fill the figures render. The orange is the
// data's and only ever sits on the canvas.
export const CANVAS = "#1d2327";
export const INK = {
  data: "#e0883a", // the samples and what is fitted to them
  standard: "#4ea1f2", // 9.80665 m/s², the blue of /quality
  probe: "#ffffff", // what the reader moves
  axis: "#7b858d", // --canvas-edge
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
// text size at any width. The SVG keeps its aspect ratio, so a tick at p % of the viewBox sits at
// p % of the box it is drawn in. `height` is in the viewBox's units, `PLOT_W` wide.
export function Plot({
  x,
  y,
  height,
  label,
  children,
}: {
  x: Axis;
  y: Axis;
  height: number;
  label: string;
  children: (s: Scale) => ReactNode;
}) {
  const sx = (v: number) => PAD + ((v - x.min) / (x.max - x.min)) * (PLOT_W - 2 * PAD);
  const sy = (v: number) => height - PAD - ((v - y.min) / (y.max - y.min)) * (height - 2 * PAD);
  return (
    <div className="learn-plot">
      {y.label ? <p className="learn-plot-label">{y.label}</p> : null}
      <div className="learn-plot-grid">
        <div className="learn-plot-yticks" aria-hidden="true">
          {y.ticks.map((v) => (
            <span key={v} style={{ top: `${(sy(v) / height) * 100}%` }}>
              {y.format(v)}
            </span>
          ))}
        </div>
        <svg viewBox={`0 0 ${PLOT_W} ${height}`} role="img" aria-label={label}>
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
