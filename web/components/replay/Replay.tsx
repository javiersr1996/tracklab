"use client";

import { useEffect, useRef, useState } from "react";
import { formatClock, type Rate, ReplayEngine, type Snapshot } from "../../lib/replay/engine";
import { drawFrame, NEON_COLORS, type View, viewed, viewOf } from "../../lib/replay/render";
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
  // Trail samples drawn behind an entity this frame: 0 on every page but the home.
  trail: number;
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

// The trail is the entity's position at these fractions of `trailMs` ago, oldest first.
const TRAIL_STEPS = Array.from({ length: 12 }, (_, k) => 1 - k / 12);
// A hero canvas is drawn at the device's pixel ratio up to this, so a phone stays fluid.
const HERO_MAX_DPR = 1.5;

interface Props {
  possession: Possession;
  autoplay?: boolean;
  onEnded?: () => void;
  overlay?: Overlay;
  name?: string;
  // The home's hero (P12): the canvas fills its box and turns the pitch upright on a portrait
  // screen, in the neon colours with a glow under every mark; the controls shrink to the pause
  // button and a readout. Without it, P1's player, unchanged.
  hero?: boolean;
  // Milliseconds of each entity's path drawn fading behind it; 0 (reduced motion) draws none.
  trailMs?: number;
}

export function Replay({
  possession,
  autoplay = false,
  onEnded,
  overlay,
  name,
  hero = false,
  trailMs = 0,
}: Props) {
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
    // A hero canvas takes its box's size (the box is sized by CSS); the loop redraws it anyway.
    let observer: ResizeObserver | undefined;
    if (hero && canvas.current) {
      const el = canvas.current;
      const fit = () => {
        const dpr = Math.min(window.devicePixelRatio || 1, HERO_MAX_DPR);
        el.width = Math.max(1, Math.round(el.clientWidth * dpr));
        el.height = Math.max(1, Math.round(el.clientHeight * dpr));
      };
      fit();
      observer = new ResizeObserver(fit);
      observer.observe(el);
    }
    const loop = (now: number) => {
      if (last !== undefined) engine.tick(now - last);
      last = now;
      const snapshot = viewed(engine.frameAt(engine.t), possession, normalized);
      const ctx = canvas.current?.getContext("2d");
      let trailed = 0;
      let rotate = false;
      if (ctx) {
        const trail =
          trailMs > 0
            ? TRAIL_STEPS.map((f) => viewed(engine.frameAt(engine.t - trailMs * f), possession, normalized))
            : undefined;
        rotate = hero && ctx.canvas.height > ctx.canvas.width;
        const markScale = hero ? Math.max(1, Math.max(ctx.canvas.width, ctx.canvas.height) / 960) : 1;
        trailed = drawFrame(
          ctx,
          possession,
          snapshot,
          hero ? { colors: NEON_COLORS, trail, glow: true, rotate, markScale } : { trail },
        );
      }
      const marks =
        ctx && overlay ? overlay(ctx, viewOf(ctx.canvas, possession, normalized, rotate), snapshot) : 0;
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
          trail: trailed,
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
    return () => {
      cancelAnimationFrame(raf);
      observer?.disconnect();
    };
  }, [engine, possession, normalized, onEnded, overlay, name, hero, trailMs]);

  const playing = engine.state === "playing";
  const playPause = (
    <button
      type="button"
      className="primary"
      onClick={() => {
        if (playing) engine.pause();
        else engine.play();
        rerender();
      }}
    >
      {playing ? "Pause" : "Play"}
    </button>
  );
  const clock = (
    <output aria-label="Clock">{formatClock(engine.frameAt(engine.t).clock, possession.clock_kind)}</output>
  );
  if (hero) {
    return (
      <figure className="replay replay-hero" data-state={engine.state}>
        <canvas ref={canvas} aria-label="Replay of the possession" />
        <div className="controls">
          {playPause}
          <p className="replay-hero-readout">
            <span className="replay-hero-sport">{possession.sport}</span>
            <span className="replay-hero-teams">
              {possession.match.home} v {possession.match.away}
            </span>
            {clock}
          </p>
        </div>
      </figure>
    );
  }
  return (
    <figure className="replay" data-state={engine.state}>
      <canvas ref={canvas} width={960} height={560} aria-label="Replay of the possession" />
      <div className="controls">
        {playPause}
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
        {clock}
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
