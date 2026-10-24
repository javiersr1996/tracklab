"use client";

import { useEffect, useId, useState } from "react";
import { expose, shown } from "../../../lib/learn/expose";
import { differenceWeights, estimate, gapTo, type Kind, roundingBound, smoothed } from "../../../lib/learn/speed";
import type { SpeedExample } from "../../../lib/learn/speed-data";
import { K_MAX } from "../../../lib/learn/speed-figures";
import { Fig } from "../Fig";
import { INK, Legend, Plot, signed, ticks } from "../gravity/Plot";

// The example player's speed over the possession: the provider's field against the estimate the
// reader builds from the published positions (a difference, then a moving average of k of them),
// with the gap underneath and the most the 1 cm rounding can put in it. Nothing moves until the
// reader does.
const KINDS: readonly { kind: Kind; label: string }[] = [
  { kind: "forward", label: "Forward" },
  { kind: "backward", label: "Backward" },
  { kind: "central", label: "Central" },
];
const GAP_REACH = 0.5; // m/s either side of zero on the gap plot

const line = (ts: readonly number[], vs: readonly (number | null)[], x: (v: number) => number, y: (v: number) => number) =>
  vs
    .map((v, i) => (v === null ? null : `${x(ts[i]).toFixed(1)},${y(v).toFixed(1)}`))
    .filter((p): p is string => p !== null)
    .join(" ");

export function TracePlot({ example, shawWindow }: { example: SpeedExample; shawWindow: number }) {
  const { t_s: t, x, y, speed, h, resolution } = example;
  const id = useId();
  const [kind, setKind] = useState<Kind>("central");
  const [k, setK] = useState(1);

  const weights = smoothed(differenceWeights(kind, h), k);
  const est = estimate(x, y, weights);
  const gap = gapTo(speed, est);
  const bound = Math.SQRT2 * roundingBound(weights, resolution);
  const figures = { kind, k, frames: gap.frames, median: shown(gap.median, 4), max: shown(gap.max, 3), bound: shown(bound, 3) };

  useEffect(() => {
    expose({ trace: figures });
  });

  const t1 = t[t.length - 1];
  const vHi = Math.ceil(Math.max(...speed, ...est.filter((v): v is number => v !== null)));
  const tAxis = { min: 0, max: t1, ticks: ticks(0, t1, 2), format: (v: number) => v.toFixed(0), label: "time from the first frame (s)" };
  const clamp = (g: number) => Math.min(GAP_REACH, Math.max(-GAP_REACH, g));

  return (
    <figure className="learn-fig surface-dark learn-speed-fig" data-figure="trace">
      <Legend
        items={[
          { color: INK.data, label: "the provider's speed" },
          { color: INK.probe, label: "your estimate from the positions" },
          { color: INK.standard, label: "the most the rounding can add", dashed: true },
        ]}
      />
      <Plot
        x={tAxis}
        y={{ min: 0, max: vHi, ticks: ticks(0, vHi, 1), format: (v) => v.toFixed(0), label: "speed (m/s)" }}
        size="tall"
        label="The player's speed over the possession: the provider's field and the estimate built from the published positions"
      >
        {({ x: sx, y: sy }) => (
          <>
            <polyline points={line(t, speed, sx, sy)} fill="none" stroke={INK.data} strokeWidth={3} vectorEffect="non-scaling-stroke" />
            <polyline points={line(t, est, sx, sy)} fill="none" stroke={INK.probe} strokeWidth={1.5} vectorEffect="non-scaling-stroke" data-probe />
          </>
        )}
      </Plot>
      <Plot
        x={tAxis}
        y={{ min: -GAP_REACH, max: GAP_REACH, ticks: [-GAP_REACH, 0, GAP_REACH], format: (v) => signed(v, 1), label: "provider's speed minus your estimate (m/s)" }}
        size="short"
        label="The gap between the provider's speed and the estimate, frame by frame, with the bound the rounding of the positions sets"
      >
        {({ x: sx, y: sy }) => (
          <>
            {[bound, -bound].map((b) => (
              <line key={b} x1={sx(0)} x2={sx(t1)} y1={sy(clamp(b))} y2={sy(clamp(b))} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
            ))}
            <line x1={sx(0)} x2={sx(t1)} y1={sy(0)} y2={sy(0)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <polyline points={line(t, gap.gaps.map((g) => (g === null ? null : clamp(g))), sx, sy)} fill="none" stroke={INK.probe} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Difference</legend>
          {KINDS.map((c) => (
            <label key={c.kind}>
              <input type="radio" name={`${id}-kind`} value={c.kind} checked={c.kind === kind} onChange={() => setKind(c.kind)} /> {c.label}
            </label>
          ))}
        </fieldset>
      </div>
      <div className="controls">
        <label htmlFor={`${id}-k`}>Moving average of k differences</label>
        <input id={`${id}-k`} type="range" min={1} max={K_MAX} step={2} value={k} onChange={(e) => setK(Number(e.target.value))} />
        <button
          type="button"
          onClick={() => {
            setKind("backward");
            setK(shawWindow);
          }}
        >
          Shaw&apos;s recipe
        </button>
        <button
          type="button"
          onClick={() => {
            setKind("central");
            setK(1);
          }}
        >
          Plain central
        </button>
      </div>
      <p className="learn-readout" aria-live="polite">
        <Fig name="learn.trace.kind">{figures.kind}</Fig>, k <Fig name="learn.trace.k">{figures.k}</Fig>: median gap{" "}
        <Fig name="learn.trace.median">{figures.median}</Fig> m/s, largest <Fig name="learn.trace.max">{figures.max}</Fig> m/s over{" "}
        <Fig name="learn.trace.frames">{figures.frames}</Fig> frames; the rounding alone can reach{" "}
        <Fig name="learn.trace.bound">{figures.bound}</Fig>
      </p>
      <figcaption>
        Player <Fig name="speed.example.entity_id">{example.entity_id}</Fig> through possession{" "}
        {example.possession_id.replace(/^bb:possessions:possession-/, "")} of match{" "}
        <Fig name="speed.example.match_id">{example.match_id}</Fig>. The orange line is the file&apos;s own speed; the white one is
        what the published positions give with the difference and window you choose.
      </figcaption>
    </figure>
  );
}
