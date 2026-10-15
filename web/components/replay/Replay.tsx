"use client";

import { useEffect, useRef, useState } from "react";
import { formatClock, type Rate, ReplayEngine, type Snapshot } from "../../lib/replay/engine";
import { drawFrame, type View, viewed, viewOf } from "../../lib/replay/render";
import type { Possession } from "../../lib/replay/types";

// Playwright reads the player's state from here; a production build leaves it out.
const EXPOSE =
  process.env.NODE_ENV === "development" || process.env.NEXT_PUBLIC_EXPOSE_REPLAY === "1";

interface ReplayState {
  state: string;
  t: number;
  frameIndex: number;
  sport: string;
  rate: number;
  normalized: boolean;
  entities: { i: number; x: number; y: number }[];
  overlay: number;
}

declare global {
  interface Window {
    __replay?: ReplayState;
    // Players that share a page (`/runs`), each under its `name`.
    __replays?: Record<string, ReplayState>;
  }
}

// Drawn on top of each frame, after the players; returns how many marks it drew.
export type Overlay = (ctx: CanvasRenderingContext2D, view: View, snapshot: Snapshot) => number;

const RATES: Rate[] = [0.5, 1, 2];

interface Props {
  possession: Possession;
  autoplay?: boolean;
  onEnded?: () => void;
  overlay?: Overlay;
  name?: string;
}

export function Replay({ possession, autoplay = false, onEnded, overlay, name }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [engine] = useState(() => {
    const e = new ReplayEngine(possession);
    if (autoplay) e.play();
    return e;
  });
  const [normalized, setNormalized] = useState(false);
  const [, setVersion] = useState(0);
  const rerender = () => setVersion((v) => v + 1);

  useEffect(() => {
    let raf = 0;
    let last: number | undefined;
    let shown = engine.state;
    const loop = (now: number) => {
      if (last !== undefined) engine.tick(now - last);
      last = now;
      const snapshot = viewed(engine.frameAt(engine.t), possession, normalized);
      const ctx = canvas.current?.getContext("2d");
      if (ctx) drawFrame(ctx, possession, snapshot);
      const marks =
        ctx && overlay ? overlay(ctx, viewOf(ctx.canvas, possession, normalized), snapshot) : 0;
      if (EXPOSE) {
        const exposed: ReplayState = {
          state: engine.state,
          t: engine.t,
          frameIndex: engine.indexAt(engine.t),
          sport: possession.sport,
          rate: engine.rate,
          normalized,
          entities: snapshot.entities.map(({ i, x, y }) => ({ i, x, y })),
          overlay: marks,
        };
        window.__replay = exposed;
        if (name) window.__replays = { ...window.__replays, [name]: exposed };
      }
      // Every frame while playing, and once more on the tick that ends it.
      if (engine.state === "playing" || engine.state !== shown) setVersion((v) => v + 1);
      if (engine.state === "ended" && shown !== "ended") onEnded?.();
      shown = engine.state;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [engine, possession, normalized, onEnded, overlay, name]);

  const playing = engine.state === "playing";
  return (
    <figure className="replay" data-state={engine.state}>
      <canvas ref={canvas} width={960} height={560} aria-label="Replay of the possession" />
      <div className="controls">
        <button
          type="button"
          onClick={() => {
            if (playing) engine.pause();
            else engine.play();
            rerender();
          }}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          aria-label="Scrub"
          min={engine.t0}
          max={engine.tEnd}
          step={1}
          value={Math.round(engine.t)}
          onChange={(e) => {
            engine.seek(Number(e.target.value));
            rerender();
          }}
        />
        <output aria-label="Clock">
          {formatClock(engine.frameAt(engine.t).clock, possession.clock_kind)}
        </output>
        <select
          aria-label="Speed"
          value={engine.rate}
          onChange={(e) => {
            engine.setRate(Number(e.target.value) as Rate);
            rerender();
          }}
        >
          {RATES.map((r) => (
            <option key={r} value={r}>
              {r}x
            </option>
          ))}
        </select>
        <label>
          <input
            type="checkbox"
            checked={normalized}
            onChange={(e) => setNormalized(e.target.checked)}
          />
          normalize attack →
        </label>
      </div>
    </figure>
  );
}
