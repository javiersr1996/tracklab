"use client";

import { useEffect, useId, useState } from "react";
import { autocorrelation, band, firstPeak } from "../../../lib/learn/cadence";
import type { HookWindow } from "../../../lib/learn/cadence-data";
import { expose, shown } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, signed, ticks } from "../gravity/Plot";

// The hook window's s(t) and the same signal moved later by the lag the reader picks, above its
// autocorrelation r(k) / r(0) with white noise's band. It opens on the first peak, the lag the
// cadence is read from; nothing moves until the reader does.
const R_LIM = 1.25;

export function LagPlot({ hook }: { hook: HookWindow }) {
  const { s_m: s, fps } = hook;
  const id = useId();
  const n = s.length;
  const r = autocorrelation(s);
  const rel = r.map((v) => v / r[0]);
  const peak = firstPeak(r);
  const [k, setK] = useState(peak?.k ?? 0);

  const figures = { k, seconds: shown(k / fps, 2), ratio: shown(rel[k], 3), band: shown(band(n, k), 3), products: n - k };
  useEffect(() => {
    expose({ lag: figures });
  });

  const t = s.map((_, i) => i / fps);
  const tMax = t[n - 1];
  const sLim = Math.ceil(Math.max(...s.map(Math.abs)) * 10) / 10;
  const clampR = (v: number) => Math.min(R_LIM, Math.max(-R_LIM, v));
  const line = (xs: number[], ys: number[], x: (v: number) => number, y: (v: number) => number) =>
    xs.map((xi, i) => `${x(xi).toFixed(1)},${y(ys[i]).toFixed(1)}`).join(" ");
  const lags = r.map((_, j) => j);
  const shifted = s.slice(0, n - k);

  return (
    <figure className="learn-fig surface-dark" data-figure="lag">
      <Legend
        items={[
          { color: INK.data, label: "s(t) and its autocorrelation", dot: true },
          { color: INK.probe, label: "the copy moved by the lag you pick" },
          { color: INK.standard, label: "white noise's band", dashed: true },
        ]}
      />
      <Plot
        x={{ min: 0, max: tMax, ticks: ticks(0, tMax, 0.5), format: (v) => v.toFixed(1), label: "time in the window (s)" }}
        y={{ min: -sLim, max: sLim, ticks: [-sLim, 0, sLim], format: (v) => signed(v, 1), label: "s(t), left ankle ahead of the right along the run (m)" }}
        size="tall"
        label="The ankles' separation along the run over the window, and the same signal moved later by the chosen lag"
      >
        {({ x, y }) => (
          <>
            <line x1={x(0)} x2={x(tMax)} y1={y(0)} y2={y(0)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <polyline points={line(t, s, x, y)} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            {t.map((ti, i) => (
              <Dot key={ti} x={x(ti)} y={y(s[i])} r={3} color={INK.data} />
            ))}
            <polyline points={line(t.slice(k), shifted, x, y)} fill="none" stroke={INK.probe} strokeWidth={2} vectorEffect="non-scaling-stroke" data-probe />
          </>
        )}
      </Plot>
      <Plot
        x={{ min: 0, max: n - 1, ticks: ticks(0, n - 1, 10), format: String, label: "lag k (frames)" }}
        y={{ min: -R_LIM, max: R_LIM, ticks: [-1, 0, 1], format: (v) => signed(v, 0), label: "r(k) / r(0)" }}
        size="tall"
        label="The autocorrelation of the signal against the lag, with the white-noise band and the chosen lag marked"
      >
        {({ x, y }) => (
          <>
            <line x1={x(0)} x2={x(n - 1)} y1={y(0)} y2={y(0)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            {[1, -1].map((sign) => (
              <polyline
                key={sign}
                points={line(lags.slice(1), lags.slice(1).map((j) => clampR(sign * band(n, j))), x, y)}
                fill="none"
                stroke={INK.standard}
                strokeWidth={2}
                strokeDasharray="8 6"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <polyline points={line(lags, rel.map(clampR), x, y)} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            {lags.map((j) => (
              <Dot key={j} x={x(j)} y={y(clampR(rel[j]))} r={3} color={INK.data} />
            ))}
            <line x1={x(k)} x2={x(k)} y1={y(-R_LIM)} y2={y(R_LIM)} stroke={INK.probe} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <Dot x={x(k)} y={y(clampR(rel[k]))} r={7} color={INK.probe} />
          </>
        )}
      </Plot>
      <div className="controls">
        <label htmlFor={`${id}-k`}>Lag k</label>
        <input id={`${id}-k`} type="range" min={0} max={n - 2} step={1} value={k} onChange={(e) => setK(Number(e.target.value))} />
        <button type="button" disabled={!peak} onClick={() => peak && setK(peak.k)}>
          First peak
        </button>
      </div>
      <p className="learn-readout" aria-live="polite">
        Lag <Fig name="learn.lag.k">{figures.k}</Fig> frames, <Fig name="learn.lag.seconds">{figures.seconds}</Fig> s, over{" "}
        <Fig name="learn.lag.products">{figures.products}</Fig> products: r(k) / r(0) = <Fig name="learn.lag.ratio">{figures.ratio}</Fig>, band ±
        <Fig name="learn.lag.band">{figures.band}</Fig>
      </p>
      <figcaption>
        The hook window of match <Fig name={`${hook.file}:match_id`}>{hook.match_id}</Fig>, as /tracking/pose publishes it. Where
        the white copy lies on the cyan signal, the products are positive and r is high.
      </figcaption>
    </figure>
  );
}
