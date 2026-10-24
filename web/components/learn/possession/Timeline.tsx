"use client";

import { useEffect, useId, useState } from "react";
import { display } from "../../../lib/learn/display";
import { expose } from "../../../lib/learn/expose";
import { expSurvival, quantile, survival } from "../../../lib/learn/possession";
import { durations, spells, type Timeline as TimelineData } from "../../../lib/learn/possession-data";
import { timelineFigures } from "../../../lib/learn/possession-figures";
import { Fig } from "../Fig";
import { INK, Legend, Plot, ticks } from "../gravity/Plot";

// A whole match as the ball changes hands: one lane per period, a bar per run (football) or
// possession (basketball) in its team's colour; then how long they last, as the share that
// outlasts each time, against an exponential with the same median. The reader picks the sport.
const SPORTS = ["football", "basketball"] as const;
type Sport = (typeof SPORTS)[number];
const UNIT: Record<Sport, string> = { football: "run", basketball: "possession" };
const TEAM = [INK.data, INK.standard];

export function Timeline({ timelines }: { timelines: Record<Sport, TimelineData> }) {
  const id = useId();
  const [sport, setSport] = useState<Sport>("football");
  const t = timelines[sport];
  const s = spells(t);
  const d = durations(s);
  const f = timelineFigures(t);
  const readout = { sport, n: f.n, median: f.median, p90: f.p90, beyond2_pct: f.beyond2_pct, exp_beyond2_pct: f.exp_beyond2_pct };

  useEffect(() => {
    expose({ timeline: readout });
  });

  // Lanes: minutes from each period's first unit.
  const periods = [...new Set(s.map((x) => x.period))].sort((a, b) => a - b);
  const origin = new Map(periods.map((p) => [p, Math.min(...s.filter((x) => x.period === p).map((x) => x.start))]));
  const span = Math.max(...s.map((x) => (x.end - origin.get(x.period)!) / 60));
  const xMax = Math.ceil(span / 10) * 10;
  const lane = (p: number) => periods.indexOf(p);
  // The survival curve up to twice the 90th percentile.
  const median = quantile(d, 0.5);
  const tMax = Math.ceil((2 * quantile(d, 0.9)) / 20) * 20;
  const grid = Array.from({ length: 201 }, (_, i) => (i * tMax) / 200);

  return (
    <figure className="learn-fig surface-dark" data-figure="timeline">
      <Legend
        items={[
          { color: TEAM[0], label: `a ${UNIT[sport]} of the team that has the ball first` },
          { color: TEAM[1], label: `a ${UNIT[sport]} of the other team` },
          { color: INK.probe, label: "an exponential with the same median", dashed: true },
        ]}
      />
      <Plot
        x={{ min: 0, max: xMax, ticks: ticks(0, xMax, xMax > 40 ? 10 : 5), format: (v) => v.toFixed(0), label: "minutes of video from the period's first unit" }}
        y={{ min: -0.5, max: periods.length - 0.5, ticks: [], format: (v) => v.toFixed(0), label: `match ${display(t.match_id, "match_id")}, one lane per period, the first at the top` }}
        size="short"
        label={`The ${sport} match as the ball changes hands: a bar per ${UNIT[sport]}, one lane per period`}
      >
        {({ x, y }) => (
          <>
            {s.map((u, i) => {
              const top = y(periods.length - 1 - lane(u.period) + 0.35);
              const bottom = y(periods.length - 1 - lane(u.period) - 0.35);
              const x0 = x((u.start - origin.get(u.period)!) / 60);
              const x1 = x((u.end - origin.get(u.period)!) / 60);
              return <rect key={i} x={x0.toFixed(1)} y={top.toFixed(1)} width={Math.max(x1 - x0, 0.5).toFixed(1)} height={(bottom - top).toFixed(1)} fill={TEAM[u.team]} />;
            })}
          </>
        )}
      </Plot>
      <Plot
        x={{ min: 0, max: tMax, ticks: ticks(0, tMax, tMax > 150 ? 50 : 20), format: (v) => v.toFixed(0), label: `seconds a ${UNIT[sport]} lasts` }}
        y={{ min: 0, max: 1, ticks: [0, 0.25, 0.5, 0.75, 1], format: (v) => v.toFixed(2), label: `share of ${UNIT[sport]}s that last longer` }}
        size="short"
        label={`How long the ${UNIT[sport]}s last: the share that outlasts each time, and an exponential with the same median`}
      >
        {({ x, y }) => (
          <>
            <polyline points={grid.map((v) => `${x(v).toFixed(1)},${y(expSurvival(median, v)).toFixed(1)}`).join(" ")} fill="none" stroke={INK.probe} strokeWidth={2} strokeDasharray="6 4" vectorEffect="non-scaling-stroke" />
            <polyline points={grid.map((v) => `${x(v).toFixed(1)},${y(survival(d, v)).toFixed(1)}`).join(" ")} fill="none" stroke={INK.data} strokeWidth={2} vectorEffect="non-scaling-stroke" />
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Sport</legend>
          {SPORTS.map((k) => (
            <label key={k}>
              <input type="radio" name={`${id}-sport`} value={k} checked={k === sport} onChange={() => setSport(k)} /> {k}
            </label>
          ))}
        </fieldset>
      </div>
      <p className="learn-readout" aria-live="polite">
        <Fig name="learn.timeline.n">{readout.n}</Fig> {UNIT[sport]}s, median <Fig name="learn.timeline.median">{readout.median}</Fig>&nbsp;s,
        ninetieth percentile <Fig name="learn.timeline.p90">{readout.p90}</Fig>&nbsp;s. Longer than twice the median:{" "}
        <Fig name="learn.timeline.beyond2_pct">{readout.beyond2_pct}</Fig>&nbsp;%, against{" "}
        <Fig name="learn.timeline.exp_beyond2_pct">{readout.exp_beyond2_pct}</Fig>&nbsp;% for the exponential.
      </p>
      <figcaption>
        Times are the video&apos;s, from a unit&apos;s first frame to its last, so a stoppage inside it counts. The orange curve
        steps down as each unit ends; the dashed one is what a constant chance per second of the ball changing hands would give,
        fitted only by its median.
      </figcaption>
    </figure>
  );
}
