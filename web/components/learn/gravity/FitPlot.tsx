"use client";

import { useEffect, useId, useState } from "react";
import { apparentG, fitAtG, fitQuadratic, residualsAt, rmsAt, type Quadratic } from "../../../lib/learn/gravity";
import type { GravityHook } from "../../../lib/learn/gravity-data";
import { expose, shown } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, signed, ticks } from "./Plot";

// The hook flight's 21 samples, the least-squares parabola, the same flight redrawn at 9.80665
// from `z_real_m`, and a parabola at any g the reader tries (c and b fitted to it), with the
// residuals that g leaves underneath. Nothing moves until the reader does.
const G_MIN = 6;
const G_MAX = 11;
const G_STEP = 0.01;
const CURVE_POINTS = 81;

const at = (q: Quadratic, t: number) => q.c + q.b * t + q.a * t * t;

function curve(q: Quadratic, t0: number, t1: number, sx: (v: number) => number, sy: (v: number) => number) {
  return Array.from({ length: CURVE_POINTS }, (_, k) => {
    const t = t0 + ((t1 - t0) * k) / (CURVE_POINTS - 1);
    return `${sx(t).toFixed(1)},${sy(at(q, t)).toFixed(1)}`;
  }).join(" ");
}

// The smallest of 10, 20, 50, 100 or 200 mm that holds every residual.
const reach = (mm: number) => [10, 20, 50, 100, 200].find((r) => r >= mm) ?? Math.ceil(mm / 100) * 100;

export function FitPlot({ hook }: { hook: GravityHook }) {
  const { t_s: t, z_data_m: z, z_real_m: zReal, g_real: G } = hook;
  const id = useId();
  const fitted = apparentG(t, z);
  const [g, setG] = useState(fitted);

  const residualsMm = residualsAt(t, z, g).map((r) => r * 1000);
  const rmsMm = rmsAt(t, z, g) * 1000;
  const figures = { g: shown(g, 5), rms_mm: shown(rmsMm, 1) };
  const residualsShown = residualsMm.map((r) => shown(r, 1));

  useEffect(() => {
    expose({ fit: { ...figures, residuals_mm: residualsShown } });
  });

  const t0 = t[0];
  const t1 = t[t.length - 1];
  const zs = [...z, ...zReal];
  const zLo = Math.floor(Math.min(...zs) * 10) / 10;
  const zHi = Math.ceil(Math.max(...zs) * 10) / 10;
  const tAxis = { min: t0, max: t1, ticks: ticks(t0, t1, 0.2), format: (v: number) => signed(v, 1), label: "time from the highest sample (s)" };
  const r = reach(Math.max(...residualsMm.map(Math.abs)));

  return (
    <figure className="learn-fig surface-dark" data-figure="fit">
      <Legend
        items={[
          { color: INK.data, label: "the samples", dot: true },
          { color: INK.data, label: "least squares" },
          { color: INK.standard, label: "the same start at standard gravity", dashed: true },
          { color: INK.probe, label: "the g you try" },
        ]}
      />
      <Plot
        x={tAxis}
        y={{ min: zLo, max: zHi, ticks: ticks(zLo, zHi, 0.2), format: (v) => v.toFixed(1), label: "height z (m)" }}
        size="tall"
        label="Height of the ball against time: the samples, the least-squares parabola, the same start at standard gravity and the parabola at the g you try"
      >
        {({ x, y }) => (
          <>
            <polyline points={curve(fitQuadratic(t, zReal), t0, t1, x, y)} fill="none" stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
            <polyline points={curve(fitQuadratic(t, z), t0, t1, x, y)} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            <polyline points={curve(fitAtG(t, z, g), t0, t1, x, y)} fill="none" stroke={INK.probe} strokeWidth={1.5} vectorEffect="non-scaling-stroke" data-probe />
            {t.map((ti, i) => (
              <Dot key={ti} x={x(ti)} y={y(z[i])} r={5} color={INK.data} />
            ))}
          </>
        )}
      </Plot>
      <Plot
        x={tAxis}
        y={{ min: -r, max: r, ticks: [-r, 0, r], format: (v) => signed(v, 0), label: "residual at the g you try (mm)" }}
        size="short"
        label="Residuals of the samples against the parabola at the g you try"
      >
        {({ x, y }) => (
          <>
            <line x1={x(t0)} x2={x(t1)} y1={y(0)} y2={y(0)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            {t.map((ti, i) => (
              <line key={ti} x1={x(ti)} x2={x(ti)} y1={y(0)} y2={y(residualsMm[i])} stroke={INK.probe} strokeWidth={3} vectorEffect="non-scaling-stroke" />
            ))}
          </>
        )}
      </Plot>
      <div className="controls">
        <label htmlFor={`${id}-g`}>Try a g</label>
        <input
          id={`${id}-g`}
          type="range"
          min={G_MIN}
          max={G_MAX}
          step={G_STEP}
          value={g}
          onChange={(e) => setG(Number(e.target.value))}
        />
        <button type="button" onClick={() => setG(fitted)}>
          Least squares
        </button>
        <button type="button" onClick={() => setG(G)}>
          Standard gravity
        </button>
      </div>
      <p className="learn-readout" aria-live="polite">
        g <Fig name="learn.fit.g">{figures.g}</Fig> m/s², residual RMS <Fig name="learn.fit.rms_mm">{figures.rms_mm}</Fig> mm
      </p>
      <figcaption>
        Shot {hook.shot_id.replace(/^shot-/, "")} of match <Fig name="hook.match_id">{hook.match_id}</Fig>, as
        /engineering/quality replays it. Drag the g, or jump to the least-squares one or to{" "}
        <Fig name="hook.g_real">{G}</Fig>; the white bars are what that parabola leaves unexplained.
      </figcaption>
    </figure>
  );
}
