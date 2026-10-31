"use client";

import { useEffect, useId, useState } from "react";
import { flight, type EntryConstants, type Sample } from "../../../lib/learn/entry";
import { G_MAX, G_MIN, S_MAX, S_MIN } from "../../../lib/learn/entry-figures";
import { expose, shown } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, ticks } from "../gravity/Plot";

// The example shot from the side, in the vertical plane through the rim: its heights against
// the horizontal distance still to go to the rim's centre, the projectile the geometry requires
// (magenta, ending at the rim) and the line the check fits through the last heights (white, at the
// arrival sample). The reader moves g and a scale on the heights; nothing moves until they do.
const PATH_STEPS = 40;

export function EntryFigure({
  samples,
  offset,
  constants,
  rimX,
  hookG,
  heightScale,
}: {
  samples: readonly Sample[];
  offset: number;
  constants: EntryConstants;
  rimX: number;
  hookG: number;
  heightScale: number;
}) {
  const id = useId();
  const [g, setG] = useState(constants.g);
  const [s, setS] = useState(1);
  const run = samples.slice(offset);
  const f = flight(run, constants, rimX, { g, zScale: s });
  const figures = { g, scale: s, reported: shown(f.reported, 2), required: shown(f.required, 2), gap: shown(f.gap, 2) };

  useEffect(() => {
    expose({ entry: figures });
  });

  // Distance still to go to the rim's centre, as a negative number so the rim sits at the right.
  const u = (p: Sample) => -Math.hypot(rimX - p.x, -p.y);
  const u0 = u(run[0]);
  const left = Math.floor(Math.min(...samples.map(u)) * 2) / 2;
  const zTop = Math.ceil(Math.max(...samples.map((p) => s * p.z)) * 2) / 2 + 0.5;
  const arrival = run[f.k];
  const rim = constants.rim_height;
  const ideal = Array.from({ length: PATH_STEPS + 1 }, (_, i) => {
    const t = (f.T * i) / PATH_STEPS;
    return [u0 + f.vH * t, s * run[0].z + f.vz0 * t - 0.5 * g * t * t] as const;
  });
  // A tangent of slope dz/du drawn `back` metres before and `ahead` after a point.
  const tangent = (u1: number, z1: number, slope: number, back: number, ahead: number) => [
    [u1 - back, z1 - slope * back],
    [u1 + ahead, z1 + slope * ahead],
  ];
  const rep = tangent(u(arrival), s * arrival.z, f.vzRep / f.vH, 0.9, 0.5);
  const req = tangent(0, rim, f.vzReq / f.vH, 0.9, 0.3);

  return (
    <figure className="learn-fig surface-dark" data-figure="entry">
      <Legend
        items={[
          { color: INK.data, label: "the ball's height, frame by frame", dot: true },
          { color: INK.standard, label: "the flight the geometry requires, and its angle at the rim" },
          { color: INK.probe, label: "the line through the last heights, at the arrival sample", dashed: true },
          { color: INK.axis, label: "the rim's height", dashed: true },
        ]}
      />
      <Plot
        x={{ min: left, max: 0.5, ticks: ticks(left, 0.5, 1), format: (v) => Math.abs(v).toFixed(0), label: "horizontal distance to the rim's centre (m)" }}
        y={{ min: 0, max: zTop, ticks: ticks(0, zTop, 1), format: (v) => v.toFixed(0), label: "height (m)" }}
        size="tall"
        label="The shot from the side: its heights, the flight the geometry requires and the line the check fits at the arrival sample"
      >
        {({ x, y }) => (
          <>
            <line x1={x(left)} x2={x(0.5)} y1={y(rim)} y2={y(rim)} stroke={INK.axis} strokeWidth={1} strokeDasharray="6 6" vectorEffect="non-scaling-stroke" />
            <polyline points={ideal.map(([a, b]) => `${x(a).toFixed(1)},${y(b).toFixed(1)}`).join(" ")} fill="none" stroke={INK.standard} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            <line x1={x(req[0][0])} y1={y(req[0][1])} x2={x(req[1][0])} y2={y(req[1][1])} stroke={INK.standard} strokeWidth={3} vectorEffect="non-scaling-stroke" />
            <polyline points={samples.map((p) => `${x(u(p)).toFixed(1)},${y(s * p.z).toFixed(1)}`).join(" ")} fill="none" stroke={INK.data} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            {samples.map((p, i) => (
              <Dot key={i} x={x(u(p))} y={y(s * p.z)} r={3} color={INK.data} />
            ))}
            <line x1={x(rep[0][0])} y1={y(rep[0][1])} x2={x(rep[1][0])} y2={y(rep[1][1])} stroke={INK.probe} strokeWidth={2} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" data-probe />
            <Dot x={x(u(arrival))} y={y(s * arrival.z)} r={6} color={INK.probe} />
            <Dot x={x(0)} y={y(rim)} r={5} color={INK.standard} />
          </>
        )}
      </Plot>
      <div className="controls">
        <label htmlFor={`${id}-g`}>g the geometry assumes (m/s²)</label>
        <input id={`${id}-g`} type="range" min={G_MIN} max={G_MAX} step={0.01} value={g} onChange={(e) => setG(Number(e.target.value))} />
        <button type="button" onClick={() => setG(constants.g)}>
          Standard gravity
        </button>
        <button type="button" onClick={() => setG(hookG)}>
          The first lesson&apos;s g
        </button>
      </div>
      <div className="controls">
        <label htmlFor={`${id}-s`}>Scale on every height</label>
        <input id={`${id}-s`} type="range" min={S_MIN} max={S_MAX} step={0.01} value={s} onChange={(e) => setS(Number(e.target.value))} />
        <button type="button" onClick={() => setS(1)}>
          The file&apos;s heights
        </button>
        <button type="button" onClick={() => setS(heightScale)}>
          The first lesson&apos;s height scale
        </button>
      </div>
      <p className="learn-readout" aria-live="polite">
        g <Fig name="learn.entry.g">{figures.g}</Fig>&nbsp;m/s², heights times <Fig name="learn.entry.scale">{figures.scale}</Fig>:
        reported <Fig name="learn.entry.reported">{figures.reported}</Fig>°, required <Fig name="learn.entry.required">{figures.required}</Fig>
        °, a gap of <Fig name="learn.entry.gap">{figures.gap}</Fig>°.
      </p>
      <figcaption>
        Every published sample of the shot, from its start frame to the first frame under the rim on the way down. The check
        measures the horizontal speed from the run that starts two frames after the release, and reads the reported angle at the
        arrival sample, the white dot, where the flight time it computes runs out.
      </figcaption>
    </figure>
  );
}
