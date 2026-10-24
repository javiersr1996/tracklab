"use client";

import { useEffect, useId, useState } from "react";
import { surfacePrimitives, type Primitive } from "../../../lib/geometry";
import { printed } from "../../../lib/learn/coordinates";
import { shown, expose } from "../../../lib/learn/expose";
import type { FrameView } from "../../../lib/learn/coordinates-data";
import { Fig } from "../Fig";
import { INK } from "../gravity/Plot";

// The first frame of each home-page possession, step by step from the provider's numbers to
// Track Lab's frame. Positions are drawn in metres throughout: a change of unit relabels the axes
// and leaves every player where he is, while the sign k turns the picture. Nothing moves until
// the reader picks a step.
export const MARKS = {
  attack: INK.data,
  defence: INK.standard,
  ball: "#f5c518", // the replay's ball (lib/replay/render.ts)
  ring: INK.probe,
  surface: "#9aa4ad", // the replay's markings, --canvas-muted
} as const;

export type Step = "delivered" | "metres" | "turn-own" | "turn-other" | "mirror-other";

export const STEPS: readonly { step: Step; label: string }[] = [
  { step: "delivered", label: "as delivered" },
  { step: "metres", label: "× s, in metres" },
  { step: "turn-own", label: "× k, turned for the team with the ball" },
  { step: "turn-other", label: "× k, turned for the other team" },
  { step: "mirror-other", label: "x only, mirrored for the other team" },
];

// What a step does to a point in metres: the factor on x and on y, and the unit it is read in.
export function stepOf(view: Pick<FrameView, "sign" | "unit" | "unit_to_m">, step: Step) {
  const k = step === "turn-own" ? view.sign : step === "turn-other" || step === "mirror-other" ? -view.sign : 1;
  const fy = step === "mirror-other" ? 1 : k;
  const delivered = step === "delivered";
  return {
    k,
    fx: k,
    fy,
    unit: delivered ? view.unit : "m",
    per_m: delivered ? 1 / view.unit_to_m : 1,
    // Which way the team with the ball attacks on the screen: its sign, times what the step did to x.
    attack: (view.sign * k) as 1 | -1,
  };
}

// The point as the step reads it, at the published precision (two decimals).
export const readAt = (v: Pick<FrameView, "sign" | "unit" | "unit_to_m">, step: Step, x: number, y: number) => {
  const s = stepOf(v, step);
  return [shown(s.fx * x * s.per_m, 2), shown(s.fy * y * s.per_m, 2)] as const;
};

const TICK_STEP: Record<string, number> = { ft: 20, m: 5 };
const TICK_STEP_FOOTBALL = 25;

function ticksFor(half: number, every: number): number[] {
  const out: number[] = [];
  for (let v = -Math.floor(half / every) * every; v <= half + 1e-9; v += every) out.push(v);
  return out;
}

function arcPath(p: Extract<Primitive, { kind: "arc" }>): string {
  const at = (a: number) => `${(p.cx + p.r * Math.cos(a)).toFixed(3)} ${(-(p.cy + p.r * Math.sin(a))).toFixed(3)}`;
  const large = p.end - p.start > Math.PI ? 1 : 0;
  // Counter-clockwise with y up is counter-clockwise on the screen too once y is flipped: sweep 0.
  return `M${at(p.start)}A${p.r} ${p.r} 0 ${large} 0 ${at(p.end)}`;
}

export function Marking({ p }: { p: Primitive }) {
  const common = { fill: "none", stroke: MARKS.surface, strokeWidth: 1.5, vectorEffect: "non-scaling-stroke" } as const;
  switch (p.kind) {
    case "line":
      return <line x1={p.x1} y1={-p.y1} x2={p.x2} y2={-p.y2} {...common} />;
    case "rect":
      return <rect x={p.x} y={-(p.y + p.h)} width={p.w} height={p.h} {...common} />;
    case "circle":
      return <circle cx={p.cx} cy={-p.cy} r={p.r} {...common} />;
    case "arc":
      return <path d={arcPath(p)} {...common} />;
  }
}

export function FrameFigure({ views, feetBound }: { views: readonly FrameView[]; feetBound: number }) {
  const id = useId();
  const [sport, setSport] = useState(0);
  const [step, setStep] = useState<Step>("delivered");
  const view = views[sport];
  const s = stepOf(view, step);

  const player = view.entities.find((e) => e.i === view.highlight)!;
  const ball = view.entities.find((e) => e.role === "ball");
  const figures = {
    sport: view.sport,
    step,
    k: s.k,
    unit: s.unit,
    attack: s.attack,
    player: readAt(view, step, player.x, player.y),
    ball: ball ? readAt(view, step, ball.x, ball.y) : null,
  };

  useEffect(() => {
    expose({ frame: figures });
  });

  const margin = Math.max(2, 0.04 * view.length_m);
  const halfX = view.length_m / 2 + margin;
  const halfY = view.width_m / 2 + margin;
  const r = 0.016 * 2 * halfX;
  const every = view.sport === "football" ? TICK_STEP_FOOTBALL : TICK_STEP[s.unit];
  // Tick values in the step's unit, placed where that many units sit in metres.
  const xt = ticksFor((view.length_m / 2) * s.per_m, every);
  const yt = ticksFor((view.width_m / 2) * s.per_m, every);
  const pct = (m: number, half: number) => `${((m + half) / (2 * half)) * 100}%`;
  const minus = (v: number) => String(v).replace("-", "−");
  const draw = view.entities.map((e) => ({ ...e, x: s.fx * e.x, y: s.fy * e.y }));

  return (
    <figure className="learn-fig surface-dark learn-coordinates-frame" data-figure="frame" data-step={step} data-sport={view.sport}>
      <ul className="learn-legend">
        <li>
          <span className="learn-swatch learn-swatch-dot" style={{ color: MARKS.attack }} aria-hidden="true" />
          the team with the ball
        </li>
        <li>
          <span className="learn-swatch learn-swatch-dot" style={{ color: MARKS.defence }} aria-hidden="true" />
          the other team
        </li>
        <li>
          <span className="learn-swatch learn-swatch-dot" style={{ color: MARKS.ball }} aria-hidden="true" />
          the ball
        </li>
        <li>
          <span className="learn-swatch learn-swatch-dot learn-coordinates-ring" style={{ color: MARKS.ring }} aria-hidden="true" />
          player {view.jersey} of the team with the ball
        </li>
      </ul>
      <div className="learn-coordinates-plot">
        <p className="learn-plot-label">y ({s.unit})</p>
        <div className="learn-coordinates-grid">
          <div className="learn-coordinates-yticks" aria-hidden="true">
            {yt.map((v) => (
              <span key={v} style={{ top: pct(-v / s.per_m, halfY) }}>
                {minus(v)}
              </span>
            ))}
          </div>
          <svg
            viewBox={`${-halfX} ${-halfY} ${2 * halfX} ${2 * halfY}`}
            style={{ aspectRatio: `${2 * halfX} / ${2 * halfY}` }}
            role="img"
            aria-label={`The first frame of the ${view.sport} possession on its surface, ${STEPS.find((x) => x.step === step)?.label}`}
          >
            {surfacePrimitives({ spec: view.spec, length_m: view.length_m, width_m: view.width_m }).map((p, k) => (
              <Marking key={k} p={p} />
            ))}
            {draw
              .filter((e) => e.role !== "ball")
              .map((e) => (
                <circle key={e.i} cx={e.x} cy={-e.y} r={r} fill={MARKS[e.role]} />
              ))}
            <circle cx={s.fx * player.x} cy={-s.fy * player.y} r={1.9 * r} fill="none" stroke={MARKS.ring} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            {draw
              .filter((e) => e.role === "ball")
              .map((e) => (
                <circle key={e.i} cx={e.x} cy={-e.y} r={0.8 * r} fill={MARKS.ball} />
              ))}
          </svg>
          <div className="learn-coordinates-xticks" aria-hidden="true">
            {xt.map((v) => (
              <span key={v} style={{ left: pct(v / s.per_m, halfX) }}>
                {minus(v)}
              </span>
            ))}
          </div>
        </div>
        <p className="learn-plot-label learn-plot-xlabel">x ({s.unit})</p>
      </div>
      <div className="controls learn-coordinates-controls">
        <fieldset className="learn-choice">
          <legend>Surface</legend>
          {views.map((v, k) => (
            <label key={v.stem}>
              <input type="radio" name={`${id}-sport`} checked={sport === k} onChange={() => setSport(k)} />
              {v.sport === "basketball" ? "court" : "pitch"}
            </label>
          ))}
        </fieldset>
        <fieldset className="learn-choice learn-coordinates-steps">
          <legend>Step</legend>
          {STEPS.map((x) => (
            <label key={x.step}>
              <input type="radio" name={`${id}-step`} checked={step === x.step} onChange={() => setStep(x.step)} />
              {x.label}
            </label>
          ))}
        </fieldset>
      </div>
      <table className="learn-coordinates-readout">
        <thead>
          <tr>
            <th scope="col">{s.unit === "ft" ? "in feet" : "in metres"}</th>
            <th scope="col">x</th>
            <th scope="col">y</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">player {view.jersey}</th>
            <td>
              <Fig name="learn.frame.player.0">{printed(figures.player[0])}</Fig>
            </td>
            <td>
              <Fig name="learn.frame.player.1">{printed(figures.player[1])}</Fig>
            </td>
          </tr>
          {figures.ball ? (
            <tr>
              <th scope="row">ball</th>
              <td>
                <Fig name="learn.frame.ball.0">{printed(figures.ball[0])}</Fig>
              </td>
              <td>
                <Fig name="learn.frame.ball.1">{printed(figures.ball[1])}</Fig>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
      <p className="learn-readout" aria-live="polite">
        k = <Fig name="learn.frame.k">{printed(figures.k)}</Fig>; the team with the ball attacks towards{" "}
        {s.attack === 1 ? "+x, to the right" : "−x, to the left"}.
      </p>
      <figcaption>
        The first frame of the possession the home page plays for each sport: match{" "}
        <Fig name={`possession.${view.stem}.match.match_id`}>{view.match_id}</Fig>, at{" "}
        <Fig name={`possession.${view.stem}.frames.0.t`}>{printed(view.t_ms)}</Fig>&nbsp;ms of video.
        {view.unit === "ft" ? (
          <>
            {" "}The feet are the published metres divided back by s, so they hold to within{" "}
            <Fig name="learn.feet_bound">{feetBound}</Fig>&nbsp;ft of the provider&apos;s.
          </>
        ) : (
          " The provider delivers metres already, so s is one and the first two steps agree."
        )}
      </figcaption>
    </figure>
  );
}
