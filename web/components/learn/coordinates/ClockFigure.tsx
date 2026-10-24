"use client";

import { useEffect, useId, useState } from "react";
import { alphaAt, printed } from "../../../lib/learn/coordinates";
import type { ClockTrack } from "../../../lib/learn/coordinates-data";
import { expose, shown } from "../../../lib/learn/expose";
import { ReplayEngine } from "../../../lib/replay/engine";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, ticks } from "../gravity/Plot";

// The ball's x over the first second of each home-page possession, the court at its rate and the
// pitch at its own, on one time axis. The reader picks an instant; the replay's own engine
// (`ReplayEngine.frameAt`) gives the position there from the two samples around it.
export const START_MS = 60;

export function readClock(track: ClockTrack, engine: ReplayEngine, t: number) {
  const at = track.t0 + t;
  const k = engine.indexAt(at);
  const a = track.frames[k];
  const b = track.frames[Math.min(k + 1, track.frames.length - 1)];
  const ball = engine.frameAt(at).entities.find((e) => e.i === track.ball);
  if (!ball) throw new Error(`${track.match_id}: no ball at ${at}`);
  return { ta: a.t - track.t0, tb: b.t - track.t0, alpha: shown(alphaAt(a.t, b.t, at), 2), x: shown(ball.x, 2) };
}

const ballX = (track: ClockTrack) => track.frames.map((f) => [f.t - track.t0, f.o.find((o) => o[0] === track.ball)?.[1] ?? NaN] as const);

export function ClockFigure({ tracks, shared, windowMs }: { tracks: readonly ClockTrack[]; shared: number; windowMs: number }) {
  const id = useId();
  const [engines] = useState(() => tracks.map((t) => new ReplayEngine(t)));
  const [t, setT] = useState(START_MS);
  const reads = tracks.map((track, k) => readClock(track, engines[k], t));
  const figures = { t, ...Object.fromEntries(tracks.map((track, k) => [track.sport, reads[k]])) };

  useEffect(() => {
    expose({ clock: figures });
  });

  const xAxis = { min: 0, max: windowMs, ticks: ticks(0, windowMs, shared), format: (v: number) => String(v), label: "time from the first frame (ms)" };

  return (
    <figure className="learn-fig surface-dark" data-figure="clock">
      <Legend
        items={[
          { color: INK.data, label: "the samples", dot: true },
          { color: INK.data, label: "between them, as the replay reads it" },
          { color: INK.probe, label: "the instant you pick", dot: true },
        ]}
      />
      {tracks.map((track, k) => {
        const xs = ballX(track);
        const lo = Math.floor(Math.min(...xs.map((p) => p[1])) * 2) / 2;
        const hi = Math.ceil(Math.max(...xs.map((p) => p[1])) * 2) / 2;
        const r = reads[k];
        return (
          <div key={track.sport} className="learn-coordinates-track" data-track={track.sport}>
            <p className="learn-coordinates-track-head">
              {track.sport === "basketball" ? "Court" : "Pitch"}, a sample every{" "}
              <Fig name={track.sport === "basketball" ? "learn.step_bb_ms" : "learn.step_fb_ms"}>{1000 / track.rate}</Fig>&nbsp;ms
            </p>
            <Plot
              x={xAxis}
              y={{ min: lo, max: hi, ticks: [lo, hi], format: (v) => v.toFixed(1).replace("-", "−"), label: "ball x (m)" }}
              size="short"
              label={`The ball's x in the ${track.sport} possession over its first second, and the reading at the instant picked`}
            >
              {({ x, y }) => (
                <>
                  <polyline
                    points={xs.map(([ti, xi]) => `${x(ti).toFixed(1)},${y(xi).toFixed(1)}`).join(" ")}
                    fill="none"
                    stroke={INK.data}
                    strokeWidth={2}
                    vectorEffect="non-scaling-stroke"
                  />
                  {xs.map(([ti, xi]) => (
                    <Dot key={ti} x={x(ti)} y={y(xi)} r={4} color={INK.data} />
                  ))}
                  <line x1={x(t)} x2={x(t)} y1={y(lo)} y2={y(hi)} stroke={INK.probe} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                  <Dot x={x(t)} y={y(r.x)} r={6} color={INK.probe} />
                </>
              )}
            </Plot>
            <p className="learn-readout" aria-live="polite">
              Between the samples at <Fig name={`learn.clock.${track.sport}.ta`}>{r.ta}</Fig> and{" "}
              <Fig name={`learn.clock.${track.sport}.tb`}>{r.tb}</Fig>&nbsp;ms: α = <Fig name={`learn.clock.${track.sport}.alpha`}>{r.alpha}</Fig>,
              ball x = <Fig name={`learn.clock.${track.sport}.x`}>{printed(r.x)}</Fig>&nbsp;m
            </p>
          </div>
        );
      })}
      <div className="controls">
        <label htmlFor={`${id}-t`}>Instant</label>
        <input id={`${id}-t`} type="range" min={0} max={windowMs} step={1} value={t} onChange={(e) => setT(Number(e.target.value))} />
        <output htmlFor={`${id}-t`}>
          <Fig name="learn.clock.t">{t}</Fig>&nbsp;ms
        </output>
      </div>
      <figcaption>
        The ticks on the time axis fall every <Fig name="learn.shared_ms">{shared}</Fig>&nbsp;ms, the instants at which both clocks
        have a sample. Anywhere else at least one of the two positions is a weighted average of its neighbours.
      </figcaption>
    </figure>
  );
}
