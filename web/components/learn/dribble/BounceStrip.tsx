"use client";

import { useEffect, useId, useState } from "react";
import { autocorrelation } from "../../../lib/learn/cadence";
import type { TouchExample } from "../../../lib/learn/dribble-data";
import type { DribbleLessonFigures } from "../../../lib/learn/dribble-figures";
import { expose } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, signed, ticks } from "../gravity/Plot";

// One touch of the example possession: the ball's height at every frame, the provider's dribbles
// as marks in time, and the lowest height within the window around each; then the height's own
// rhythm, its autocorrelation. The reader picks a dribble; nothing moves until they do.
export function BounceStrip({ ex, figures }: { ex: TouchExample; figures: Pick<DribbleLessonFigures, "dribbles" | "ac_lag" | "ac_k"> }) {
  const id = useId();
  const [k, setK] = useState(0);
  const d = figures.dribbles[k];
  const readout = { dribble: d.n, t_s: d.t_s, offset: d.offset, low_z: d.low_z, gap_s: d.gap_s };

  useEffect(() => {
    expose({ strip: readout });
  });

  const t = (frame: number) => (frame - ex.start) / ex.fps;
  const t0 = t(ex.first);
  const t1 = t(ex.first + ex.z.length - 1);
  const points = ex.z.flatMap((h, i) => (h === null ? [] : [[t(ex.first + i), h] as const]));
  const zHi = Math.ceil(Math.max(...points.map((p) => p[1])) * 2) / 2;
  const f = ex.dribbles[k];

  // The autocorrelation of the height from the first dribble to the last, over lags up to half.
  const last = ex.dribbles.length - 1;
  const signal = ex.z.slice(ex.dribbles[0] - ex.first, ex.dribbles[last] - ex.first + 1) as number[];
  const r = autocorrelation(signal);
  const lags = Math.floor(r.length / 2);
  const rr = r.slice(0, lags + 1).map((v) => v / r[0]);

  return (
    <figure className="learn-fig surface-dark" data-figure="bounce-strip">
      <Legend
        items={[
          { color: INK.data, label: "the ball's height, frame by frame" },
          { color: INK.probe, label: "a dribble in the provider's events", dashed: true },
          { color: INK.standard, label: "the lowest height within the window", dot: true },
          { color: INK.axis, label: "the window of the dribble picked", dashed: true },
        ]}
      />
      <Plot
        x={{ min: t0, max: t1, ticks: ticks(t0, t1, 1), format: (v) => signed(v, 0), label: "time from the touch's first frame (s)" }}
        y={{ min: 0, max: zHi, ticks: ticks(0, zHi, 0.5), format: (v) => v.toFixed(1), label: "the ball's height (m)" }}
        size="tall"
        label="The ball's height over the touch, the provider's dribbles and the lowest height near each"
      >
        {({ x, y }) => (
          <>
            {[f - ex.reach, f + ex.reach].map((w) => (
              <line key={w} x1={x(t(w))} x2={x(t(w))} y1={y(0)} y2={y(zHi)} stroke={INK.axis} strokeWidth={2} strokeDasharray="3 5" vectorEffect="non-scaling-stroke" />
            ))}
            {ex.dribbles.map((g) => (
              <line key={g} x1={x(t(g))} x2={x(t(g))} y1={y(0)} y2={y(zHi)} stroke={INK.probe} strokeWidth={g === f ? 3 : 1.5} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
            ))}
            <polyline points={points.map(([a, b]) => `${x(a).toFixed(1)},${y(b).toFixed(1)}`).join(" ")} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            {figures.dribbles.map((row) => (
              <Dot key={row.n} x={x(t(row.low_frame))} y={y(row.low_z)} r={row.n === d.n ? 7 : 5} color={INK.standard} />
            ))}
          </>
        )}
      </Plot>
      <Plot
        x={{ min: 0, max: lags, ticks: ticks(0, lags, 10), format: (v) => v.toFixed(0), label: "lag (frames)" }}
        y={{ min: -1, max: 1, ticks: [-1, -0.5, 0, 0.5, 1], format: (v) => signed(v, 1), label: "autocorrelation of the height, over its value at lag zero" }}
        size="short"
        label="The autocorrelation of the ball's height from the first dribble to the last, and its first peak"
      >
        {({ x, y }) => (
          <>
            <line x1={x(0)} x2={x(lags)} y1={y(0)} y2={y(0)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <polyline points={rr.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            <line x1={x(figures.ac_lag)} x2={x(figures.ac_lag)} y1={y(-1)} y2={y(1)} stroke={INK.probe} strokeWidth={2} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" data-probe />
            <Dot x={x(figures.ac_k)} y={y(rr[figures.ac_k])} r={6} color={INK.standard} />
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Dribble</legend>
          {figures.dribbles.map((row, i) => (
            <label key={row.n}>
              <input type="radio" name={`${id}-dribble`} value={i} checked={i === k} onChange={() => setK(i)} /> {row.n}
            </label>
          ))}
        </fieldset>
      </div>
      <p className="learn-readout" aria-live="polite">
        Dribble <Fig name="learn.strip.dribble">{readout.dribble}</Fig> at <Fig name="learn.strip.t_s">{readout.t_s}</Fig>&nbsp;s
        {k === 0 ? (
          <>, the touch&apos;s first.</>
        ) : (
          <>
            , after a gap of <Fig name="learn.strip.gap_s">{readout.gap_s}</Fig>&nbsp;s.
          </>
        )}{" "}
        The lowest height in its window is{" "}
        <Fig name="learn.strip.low_z">{readout.low_z}</Fig>&nbsp;m, <Fig name="learn.strip.offset">{readout.offset}</Fig> frames from the
        event.
      </p>
      <figcaption>
        The heights are the published possession&apos;s, to the centimetre. The window runs as many frames before the dribble as
        after it; the dot is the lowest height inside it, the earliest if two are equal. Below, the white line is where the first
        peak of the autocorrelation sits, between frames.
      </figcaption>
    </figure>
  );
}
