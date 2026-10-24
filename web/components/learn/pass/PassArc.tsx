"use client";

import { useEffect, useId, useState } from "react";
import { expose } from "../../../lib/learn/expose";
import type { PassExample } from "../../../lib/learn/pass-data";
import { passFigures } from "../../../lib/learn/pass-figures";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, ticks } from "../gravity/Plot";

// One pass of the example possession, seen from above and from the side: the ball at every frame,
// its chord from the first frame to the last, and the provider's distance between passer and
// receiver at the first frame. The reader picks the pass; nothing moves until they do.
const MARGIN = 0.8; // m around what the top view shows
const S = 100; // the top view's units: centimetres, so a mark is placed to the millimetre

export function PassArc({ passes, fps }: { passes: readonly PassExample[]; fps: number }) {
  const id = useId();
  const [k, setK] = useState(0);
  const ex = passes[k];
  const f = passFigures(ex, fps);
  const figures = { pass: k + 1, ...f };

  useEffect(() => {
    expose({ arc: figures });
  });

  const xs = [...ex.ball.map((b) => b[0]), ...ex.passer.map((p) => p[0]), ...ex.receiver.map((p) => p[0])];
  const ys = [...ex.ball.map((b) => b[1]), ...ex.passer.map((p) => p[1]), ...ex.receiver.map((p) => p[1])];
  const x0 = Math.min(...xs) - MARGIN;
  const y1 = Math.max(...ys) + MARGIN;
  const w = Math.max(...xs) + MARGIN - x0;
  const h = y1 - (Math.min(...ys) - MARGIN);
  // Court x to the right, court y up: the view's y is flipped.
  const px = (x: number) => S * (x - x0);
  const py = (y: number) => S * (y1 - y);
  const [b0, b1] = [ex.ball[0], ex.ball[ex.ball.length - 1]];
  const T = ex.t[ex.t.length - 1];
  const zHi = Math.ceil(Math.max(...ex.ball.map((b) => b[2])) * 2) / 2 + 0.5;

  return (
    <figure className="learn-fig surface-dark" data-figure="pass-arc">
      <Legend
        items={[
          { color: INK.data, label: "the ball, frame by frame", dot: true },
          { color: INK.probe, label: "its chord, first frame to last", dashed: true },
          { color: INK.standard, label: "passer and receiver at the first frame, and the provider's distance", dashed: true },
          { color: INK.axis, label: "the receiver at the last frame", dot: true },
        ]}
      />
      <div className="learn-pass-top">
        <p className="learn-plot-label">From above (court metres, the provider&apos;s axes)</p>
        <svg viewBox={`0 0 ${(S * w).toFixed(0)} ${(S * h).toFixed(0)}`} role="img" aria-label="The pass from above: the ball's positions, its chord, and the passer and receiver where they stand">
          <line x1={px(ex.passer[0][0])} y1={py(ex.passer[0][1])} x2={px(ex.receiver[0][0])} y2={py(ex.receiver[0][1])} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
          <polyline points={ex.ball.map((b) => `${px(b[0]).toFixed(1)},${py(b[1]).toFixed(1)}`).join(" ")} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
          <line x1={px(b0[0])} y1={py(b0[1])} x2={px(b1[0])} y2={py(b1[1])} stroke={INK.probe} strokeWidth={2} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" data-probe />
          {ex.ball.map((b, i) => (
            <Dot key={i} x={px(b[0])} y={py(b[1])} r={3} color={INK.data} />
          ))}
          <Dot x={px(ex.passer[0][0])} y={py(ex.passer[0][1])} r={8} color={INK.standard} />
          <Dot x={px(ex.receiver[0][0])} y={py(ex.receiver[0][1])} r={8} color={INK.standard} />
          <Dot x={px(ex.receiver[1][0])} y={py(ex.receiver[1][1])} r={6} color={INK.axis} />
        </svg>
      </div>
      <Plot
        x={{ min: 0, max: T, ticks: ticks(0, T, 0.1), format: (v) => v.toFixed(1), label: "time from the pass's first frame (s)" }}
        y={{ min: 0, max: zHi, ticks: ticks(0, zHi, 1), format: (v) => v.toFixed(0), label: "the ball's height (m)" }}
        size="short"
        label="The pass from the side: the ball's height at every frame, and its chord"
      >
        {({ x, y }) => (
          <>
            <polyline points={ex.ball.map((b, i) => `${x(ex.t[i]).toFixed(1)},${y(b[2]).toFixed(1)}`).join(" ")} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            <line x1={x(0)} y1={y(b0[2])} x2={x(T)} y2={y(b1[2])} stroke={INK.probe} strokeWidth={2} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
            {ex.ball.map((b, i) => (
              <Dot key={i} x={x(ex.t[i])} y={y(b[2])} r={3} color={INK.data} />
            ))}
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Pass</legend>
          {passes.map((p, i) => (
            <label key={p.entry.pass_id}>
              <input type="radio" name={`${id}-pass`} value={i} checked={i === k} onChange={() => setK(i)} /> {i + 1}
            </label>
          ))}
        </fieldset>
      </div>
      <p className="learn-readout" aria-live="polite">
        Pass <Fig name="learn.arc.pass">{figures.pass}</Fig>: <Fig name="learn.arc.frames">{figures.frames}</Fig> frames,{" "}
        <Fig name="learn.arc.seconds">{figures.seconds}</Fig>&nbsp;s. The provider&apos;s distance{" "}
        <Fig name="learn.arc.distance_m">{figures.distance_m}</Fig>&nbsp;m; the ball&apos;s chord <Fig name="learn.arc.chord_m">{figures.chord_m}</Fig>
        &nbsp;m and its path <Fig name="learn.arc.path_m">{figures.path_m}</Fig>&nbsp;m. Chord over time{" "}
        <Fig name="learn.arc.chord_speed">{figures.chord_speed}</Fig>&nbsp;m/s; the provider&apos;s distance over the same time{" "}
        <Fig name="learn.arc.distance_speed">{figures.distance_speed}</Fig>&nbsp;m/s.
      </p>
      <figcaption>
        The ball and the players as the published possession writes them, to the centimetre. The chord joins the ball&apos;s first
        and last positions; the provider&apos;s distance joins the passer and the receiver as they stand at the first frame.
      </figcaption>
    </figure>
  );
}
