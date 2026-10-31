"use client";

import { useEffect, useId, useState } from "react";
import { display } from "../../../lib/learn/display";
import { expose, shown } from "../../../lib/learn/expose";
import { circular, SIDE_DEG, summarise } from "../../../lib/learn/facing";
import type { ClipFacing } from "../../../lib/learn/facing-data";
import { Fig } from "../Fig";
import { INK, Legend } from "../gravity/Plot";

// The hook player of a clip, one frame at a time: from above, the two shoulders and the nose
// with the facing they give and the heading of the frame before to the frame after; beside it,
// the rose of every qualifying frame's relative angle, straight ahead at the top, with the mean
// resultant vector. The reader picks the clip and the frame; it opens on the first frame.
const SIZE = 300;
const C = SIZE / 2;
const RING = 120; // px, the radius of the dial
const PX_PER_CM = 3; // the skeleton's scale in the view from above
const BIN_DEG = 30;
const BINS = 360 / BIN_DEG;
const GAP_DEG = 2;
const DEG = 180 / Math.PI;

// A point at `deg` (anticlockwise from the x axis, as on the pitch) and radius r: the view's y is
// flipped, so the pitch's y points up.
const at = (deg: number, r: number, cx = C, cy = C): [number, number] => [cx + r * Math.cos(deg / DEG), cy - r * Math.sin(deg / DEG)];
const pt = ([x, y]: readonly [number, number]) => `${x.toFixed(1)},${y.toFixed(1)}`;

// An arrow from (x0, y0) along `deg` for `len` px, its head a filled triangle.
function Arrow({ from, deg, len, color, dashed }: { from: readonly [number, number]; deg: number; len: number; color: string; dashed?: boolean }) {
  const tip = at(deg, len, from[0], from[1]);
  const back = at(deg, Math.max(len - 12, 0), from[0], from[1]);
  const a = at(deg + 90, 5, back[0], back[1]);
  const b = at(deg - 90, 5, back[0], back[1]);
  return (
    <g>
      <line x1={from[0].toFixed(1)} y1={from[1].toFixed(1)} x2={back[0].toFixed(1)} y2={back[1].toFixed(1)} stroke={color} strokeWidth={2} strokeDasharray={dashed ? "6 4" : undefined} vectorEffect="non-scaling-stroke" />
      <polygon points={`${pt(tip)} ${pt(a)} ${pt(b)}`} fill={color} />
    </g>
  );
}

// A wedge of the rose from `a` to `b` degrees (screen angles as `at` reads them), to radius r.
function wedge(a: number, b: number, r: number): string {
  const [x0, y0] = at(a, r);
  const [x1, y1] = at(b, r);
  return `M${C} ${C} L${x0.toFixed(1)} ${y0.toFixed(1)} A${r} ${r} 0 0 0 ${x1.toFixed(1)} ${y1.toFixed(1)} Z`;
}

export function Compass({ clips }: { clips: readonly ClipFacing[] }) {
  const id = useId();
  const [which, setWhich] = useState(0);
  const [pick, setPick] = useState(0);
  const clip = clips[which];
  const { frames } = clip.hook;
  const k = Math.min(pick, frames.length - 1);
  const fr = frames[k];
  const s = summarise(frames);
  const figures = {
    match_id: clip.match_id,
    k,
    frame_id: fr.f,
    speed: shown(fr.speed, 2),
    facing: shown(fr.facing, 3),
    heading: shown(fr.heading, 3),
    relative: shown(fr.relative, 3),
    frames: s.frames,
    circ_mean: shown(s.circ_mean, 3),
    resultant: shown(s.resultant, 3),
    median_abs: shown(s.median_abs, 3),
  };

  useEffect(() => {
    expose({ compass: figures });
  });

  // From above: the skeleton's joints around the player's own x, y, the facing from the shoulders'
  // midpoint, the heading from the player's position. The relative angle is the arc between them.
  const mid: [number, number] = [(fr.left[0] + fr.right[0]) / 2, (fr.left[1] + fr.right[1]) / 2];
  const px = ([dx, dy]: readonly [number, number]): [number, number] => [C + dx * PX_PER_CM, C - dy * PX_PER_CM];
  const arcR = RING - 24;
  const arc0 = at(fr.heading, arcR);
  const arc1 = at(fr.facing, arcR);
  const sweep = fr.relative > 0 ? 0 : 1; // anticlockwise on the pitch is anticlockwise on screen

  // The rose: bins of BIN_DEG centred on multiples of it, straight ahead at the top, positive
  // relative angles anticlockwise; the mean resultant vector in white, this frame's angle in magenta.
  const counts = Array.from({ length: BINS }, () => 0);
  for (const x of frames) counts[(((Math.floor((x.relative + BIN_DEG / 2) / BIN_DEG) % BINS) + BINS) % BINS)]++;
  const top = Math.max(...counts);
  const { mean, resultant } = circular(frames.map((x) => x.relative));
  const up = 90;

  return (
    <figure className="learn-fig surface-dark" data-figure="compass">
      <Legend
        items={[
          { color: INK.data, label: "the shoulders, right to left, the nose, and the facing they give", dot: true },
          { color: INK.probe, label: "the heading, from the frame before to the frame after", dashed: true },
          { color: INK.standard, label: "the relative angle, and this frame on the rose" },
          { color: INK.probe, label: "the mean resultant vector of every frame" },
        ]}
      />
      <div className="learn-facing-views">
        <div className="learn-facing-view">
          <p className="learn-plot-label">From above, in the pitch&apos;s axes: the joints in centimetres around the player&apos;s own position</p>
          <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="The player from above in the chosen frame: the shoulder line, the nose, the facing normal and the heading arrow, with the angle between them">
            <circle cx={C} cy={C} r={RING} fill="none" stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <path d={`M${pt(arc0)} A${arcR} ${arcR} 0 0 ${sweep} ${pt(arc1)}`} fill="none" stroke={INK.standard} strokeWidth={3} vectorEffect="non-scaling-stroke" />
            <Arrow from={[C, C]} deg={fr.heading} len={RING} color={INK.probe} dashed />
            <line x1={px(fr.right)[0].toFixed(1)} y1={px(fr.right)[1].toFixed(1)} x2={px(fr.left)[0].toFixed(1)} y2={px(fr.left)[1].toFixed(1)} stroke={INK.data} strokeWidth={4} vectorEffect="non-scaling-stroke" />
            <Arrow from={px(mid)} deg={fr.facing} len={RING - Math.hypot(mid[0], mid[1]) * PX_PER_CM} color={INK.data} />
            <circle cx={px(fr.nose)[0].toFixed(1)} cy={px(fr.nose)[1].toFixed(1)} r={6} fill={INK.data} />
            <circle cx={px(fr.left)[0].toFixed(1)} cy={px(fr.left)[1].toFixed(1)} r={5} fill={INK.data} />
            <circle cx={px(fr.right)[0].toFixed(1)} cy={px(fr.right)[1].toFixed(1)} r={5} fill={INK.data} />
          </svg>
        </div>
        <div className="learn-facing-view">
          <p className="learn-plot-label">The rose of the relative angle over every frame: straight ahead at the top, positive angles anticlockwise</p>
          <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="The rose of relative angles: one wedge per bin of thirty degrees, the mean resultant vector and the chosen frame's angle">
            <circle cx={C} cy={C} r={RING} fill="none" stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <line x1={C} y1={C - RING} x2={C} y2={C + RING} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <line x1={C - RING} y1={C} x2={C + RING} y2={C} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            {counts.map((n, i) =>
              n > 0 ? <path key={i} d={wedge(up + i * BIN_DEG - BIN_DEG / 2 + GAP_DEG, up + i * BIN_DEG + BIN_DEG / 2 - GAP_DEG, (RING * n) / top)} fill={INK.data} /> : null,
            )}
            <Arrow from={[C, C]} deg={up + mean} len={RING * resultant} color={INK.probe} />
            <circle cx={at(up + fr.relative, RING)[0].toFixed(1)} cy={at(up + fr.relative, RING)[1].toFixed(1)} r={6} fill={INK.standard} />
          </svg>
        </div>
      </div>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Match</legend>
          {clips.map((c, i) => (
            <label key={c.match_id}>
              <input type="radio" name={`${id}-match`} value={c.match_id} checked={i === which} onChange={() => setWhich(i)} /> {display(String(c.match_id), "match_id")}
            </label>
          ))}
        </fieldset>
        <label htmlFor={`${id}-frame`}>Frame</label>
        <input id={`${id}-frame`} type="range" min={0} max={frames.length - 1} step={1} value={k} onChange={(e) => setPick(Number(e.target.value))} />
      </div>
      <p className="learn-readout" aria-live="polite">
        Frame <Fig name="learn.compass.frame_id">{figures.frame_id}</Fig>, at <Fig name="learn.compass.speed">{figures.speed}</Fig>&nbsp;m/s: facing{" "}
        <Fig name="learn.compass.facing">{figures.facing}</Fig>°, heading <Fig name="learn.compass.heading">{figures.heading}</Fig>°, relative{" "}
        <Fig name="learn.compass.relative">{figures.relative}</Fig>°. Over the <Fig name="learn.compass.frames">{figures.frames}</Fig> frames: circular mean{" "}
        <Fig name="learn.compass.circ_mean">{figures.circ_mean}</Fig>°, mean resultant length <Fig name="learn.compass.resultant">{figures.resultant}</Fig>, median
        of the angle&apos;s size <Fig name="learn.compass.median_abs">{figures.median_abs}</Fig>°.
      </p>
      <figcaption>
        Number <Fig name={`${clip.file}:players.${clip.hook.index}.number`}>{clip.hook.number}</Fig> of team{" "}
        <Fig name={`${clip.file}:players.${clip.hook.index}.team_id`}>{clip.hook.team_id}</Fig> in the clip of match{" "}
        <Fig name={`${clip.file}:match_id`}>{clip.match_id}</Fig>, the player whose window the fifth lesson read. A relative angle past{" "}
        <Fig name="learn.side_deg">{SIDE_DEG}</Fig>° either way is side on or further round; the rose&apos;s wedges are counts of frames, the longest
        reaching the ring.
      </figcaption>
    </figure>
  );
}
