"use client";

import { useRouter } from "next/navigation";
import { type PointerEvent, useEffect, useRef, useState } from "react";
import {
  formatClock,
  type Rate,
  ReplayEngine,
  type Snapshot,
  speedOf,
} from "../../lib/replay/engine";
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
  // Venue metres; in the hero, also where the mark sits on the canvas, in CSS px.
  entities: { i: number; x: number; y: number; px?: number; py?: number }[];
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
// How close to a player's mark, in CSS px, the pointer has to be to pick him.
const HIT_PX = 28;

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
  // Where a click on a player goes (task 108): hovering or tapping one shows his number and
  // speed, a second tap or a click opens this. Pointer only; the page's link is the keyboard path.
  href?: string;
}

export function Replay({
  possession,
  autoplay = false,
  onEnded,
  overlay,
  name,
  hero = false,
  trailMs = 0,
  href,
}: Props) {
  const router = useRouter();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [engine] = useState(() => {
    const e = new ReplayEngine(possession);
    if (autoplay) e.play();
    return e;
  });
  const [normalized, setNormalized] = useState(false);
  const [, setVersion] = useState(0);
  const rerender = () => setVersion((v) => v + 1);
  // The player under the pointer (hero), by entity index: state for the readout's markup, and a
  // ref the loop reads, so a pick never restarts the loop (which would clear the canvas).
  const [picked, setPicked] = useState<number | null>(null);
  const pickedRef = useRef<number | null>(null);
  const pick = (i: number | null) => {
    pickedRef.current = i;
    setPicked(i);
  };
  const readout = useRef<HTMLAnchorElement>(null);
  const speedOut = useRef<HTMLOutputElement>(null);

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
        const w = Math.max(1, Math.round(el.clientWidth * dpr));
        const h = Math.max(1, Math.round(el.clientHeight * dpr));
        // Setting a size clears the bitmap: only when it changed.
        if (w !== el.width) el.width = w;
        if (h !== el.height) el.height = h;
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
      // Canvas px to CSS px, and the view, for the readout and the exposed positions (hero).
      let toCss: ((x: number, y: number) => [number, number]) | undefined;
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
        if (hero) {
          const view = viewOf(ctx.canvas, possession, normalized, rotate);
          const sx = ctx.canvas.clientWidth / ctx.canvas.width;
          const sy = ctx.canvas.clientHeight / ctx.canvas.height;
          toCss = (x, y) => {
            const [px, py] = view.project(x, y);
            return [px * sx, py * sy];
          };
          const pickedNow = pickedRef.current;
          const e = pickedNow === null ? undefined : snapshot.entities.find((s) => s.i === pickedNow);
          if (e && readout.current) {
            const [px, py] = toCss(e.x, e.y);
            readout.current.style.left = `${px}px`;
            readout.current.style.top = `${py}px`;
            const v = speedOf(engine, e.i, engine.t);
            if (speedOut.current) speedOut.current.textContent = v === null ? "– m/s" : `${v.toFixed(1)} m/s`;
          }
        }
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
          entities: snapshot.entities.map(({ i, x, y }) => {
            if (!toCss) return { i, x, y };
            const [px, py] = toCss(x, y);
            return { i, x, y, px, py };
          }),
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

  // The player whose mark is nearest the pointer, within HIT_PX, at this instant.
  const nearestPlayer = (e: PointerEvent<HTMLCanvasElement>): number | null => {
    const el = e.currentTarget;
    const rect = el.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const view = viewOf(el, possession, normalized, el.height > el.width);
    const sx = rect.width / el.width;
    const sy = rect.height / el.height;
    const players = new Set(possession.entities.filter((p) => p.kind === "player").map((p) => p.i));
    let best: number | null = null;
    let bestD = HIT_PX;
    for (const s of viewed(engine.frameAt(engine.t), possession, normalized).entities) {
      if (!players.has(s.i)) continue;
      const [px, py] = view.project(s.x, s.y);
      const d = Math.hypot(px * sx - x, py * sy - y);
      if (d < bestD) {
        bestD = d;
        best = s.i;
      }
    }
    return best;
  };

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
    const pickedEntity = picked === null ? undefined : possession.entities.find((p) => p.i === picked);
    return (
      <figure className="replay replay-hero" data-state={engine.state} data-picked={pickedEntity ? "" : undefined}>
        <canvas
          ref={canvas}
          aria-label="Replay of the possession"
          onPointerMove={(e) => {
            if (e.pointerType !== "mouse") return;
            const i = nearestPlayer(e);
            if (i !== pickedRef.current) pick(i);
          }}
          onPointerLeave={(e) => {
            if (e.pointerType === "mouse") pick(null);
          }}
          onPointerDown={(e) => {
            const i = nearestPlayer(e);
            if (i !== null && i === pickedRef.current && href) router.push(href);
            else pick(i);
          }}
        />
        {pickedEntity ? (
          <a ref={readout} href={href} className="replay-hero-player">
            #{pickedEntity.jersey ?? "?"} <output ref={speedOut} aria-label="Speed" />
          </a>
        ) : null}
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
