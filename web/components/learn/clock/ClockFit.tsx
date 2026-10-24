"use client";

import { useEffect, useId, useState } from "react";
import { lineAt } from "../../../lib/learn/clock";
import type { ClockExample } from "../../../lib/learn/clock-data";
import { fitFrom, flagRuns, MIN_FIT, moves } from "../../../lib/learn/clock-figures";
import { expose, shown } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { INK, Legend, Plot, signed, ticks } from "../gravity/Plot";

// The game clock against the video's clock over one published possession, the least-squares line
// through the frames the reader keeps, and what is left over. Nothing moves until the reader does.
const LABEL: Record<ClockExample["key"], string> = {
  calibration: "A possession of a calibration match",
  control: "A possession of a control match",
};

const niceReach = (ms: number) => [10, 20, 50, 100, 200, 500, 1000, 2000].find((r) => r >= ms) ?? Math.ceil(ms / 1000) * 1000;

export function ClockFit({ examples, halfUnitMs }: { examples: readonly ClockExample[]; halfUnitMs: number }) {
  const id = useId();
  const [key, setKey] = useState<ClockExample["key"]>("calibration");
  const [from, setFrom] = useState(0);
  const ex = examples.find((e) => e.key === key) ?? examples[0];
  const last = ex.t.length - MIN_FIT;
  const at = Math.min(from, last);
  const { fit, t, res, rms_ms, max_ms } = fitFrom(ex, at);
  const figures = { key, from: at, frames: t.length, from_s: shown(ex.t[at], 2), slope: shown(fit.slope, 5), rms_ms: shown(rms_ms, 1), max_ms: shown(max_ms, 1) };

  useEffect(() => {
    expose({ fit: figures });
  });

  const t1 = ex.t[ex.t.length - 1];
  const [lo, hi] = [Math.floor(Math.min(...ex.clock)), Math.ceil(Math.max(...ex.clock))];
  const tAxis = { min: 0, max: t1, ticks: ticks(0, t1, 2), format: (v: number) => v.toFixed(0), label: "video's clock from the first frame (s)" };
  const reach = niceReach(max_ms);
  const clamp = (v: number) => Math.min(reach, Math.max(-reach, v));
  const line = (xs: readonly number[], ys: readonly number[], x: (v: number) => number, y: (v: number) => number) =>
    xs.map((v, i) => `${x(v).toFixed(1)},${y(ys[i]).toFixed(1)}`).join(" ");

  return (
    <figure className="learn-fig surface-dark" data-figure="clock-fit">
      <Legend
        items={[
          { color: INK.data, label: "the game clock, frame by frame" },
          { color: INK.probe, label: "the line through the frames kept" },
          { color: INK.standard, label: "the flag says the clock is stopped", dashed: true },
        ]}
      />
      <Plot
        x={tAxis}
        y={{ min: lo, max: hi, ticks: ticks(lo, hi, hi - lo > 8 ? 4 : 2), format: (v) => v.toFixed(0), label: "game clock (s)" }}
        size="tall"
        label="The game clock against the video's clock over the possession, with the least-squares line through the frames kept"
      >
        {({ x, y }) => (
          <>
            {ex.stopped.map(([a, b]) => (
              <line key={a} x1={x(ex.t[a])} x2={x(ex.t[Math.min(b, ex.t.length - 1)])} y1={y(hi) + 6} y2={y(hi) + 6} stroke={INK.standard} strokeWidth={4} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
            ))}
            <polyline points={line(ex.t, ex.clock, x, y)} fill="none" stroke={INK.data} strokeWidth={3} vectorEffect="non-scaling-stroke" />
            <line x1={x(t[0])} x2={x(t1)} y1={y(lineAt(fit, t[0]))} y2={y(lineAt(fit, t1))} stroke={INK.probe} strokeWidth={1.5} vectorEffect="non-scaling-stroke" data-probe />
          </>
        )}
      </Plot>
      <Plot
        x={tAxis}
        y={{ min: -reach, max: reach, ticks: [-reach, 0, reach], format: (v) => signed(v, 0), label: "game clock minus the line (ms)" }}
        size="short"
        label="What the line leaves over at each frame kept, with half the step at which the file writes the clock"
      >
        {({ x, y }) => (
          <>
            {[halfUnitMs, -halfUnitMs].map((b) => (
              <line key={b} x1={x(0)} x2={x(t1)} y1={y(clamp(b))} y2={y(clamp(b))} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
            ))}
            <line x1={x(0)} x2={x(t1)} y1={y(0)} y2={y(0)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <polyline points={line(t, res.map(clamp), x, y)} fill="none" stroke={INK.probe} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Possession</legend>
          {examples.map((e) => (
            <label key={e.key}>
              <input
                type="radio"
                name={`${id}-key`}
                value={e.key}
                checked={e.key === key}
                onChange={() => {
                  setKey(e.key);
                  setFrom(0);
                }}
              />{" "}
              {LABEL[e.key]}
            </label>
          ))}
        </fieldset>
      </div>
      <div className="controls">
        <label htmlFor={`${id}-from`}>Fit from frame</label>
        <input id={`${id}-from`} type="range" min={0} max={last} step={1} value={at} onChange={(e) => setFrom(Number(e.target.value))} />
        <button type="button" onClick={() => setFrom(0)}>
          All frames
        </button>
        <button type="button" onClick={() => setFrom(flagRuns(ex))}>
          From the flag
        </button>
        <button type="button" onClick={() => setFrom(moves(ex))}>
          From the first move
        </button>
      </div>
      <p className="learn-readout" aria-live="polite">
        From <Fig name="learn.fit.from_s">{figures.from_s}</Fig>&nbsp;s, <Fig name="learn.fit.frames">{figures.frames}</Fig> frames: slope{" "}
        <Fig name="learn.fit.slope">{figures.slope}</Fig>, what is left over <Fig name="learn.fit.rms_ms">{figures.rms_ms}</Fig>&nbsp;ms RMS
        and at most <Fig name="learn.fit.max_ms">{figures.max_ms}</Fig>&nbsp;ms.
      </p>
      <figcaption>
        The game clock as the published possession writes it, at a hundredth of a second, against the video&apos;s clock. The
        dashed bar above the clock marks the frames the provider&apos;s flag calls stopped; the dashed lines below are half the
        step at which the file writes the clock.
      </figcaption>
    </figure>
  );
}
