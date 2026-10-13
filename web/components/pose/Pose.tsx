"use client";

import { useEffect, useRef, useState } from "react";
import { PoseEngine } from "../../lib/pose/engine";
import { drawFollow, drawPitch, type Probe } from "../../lib/pose/render";
import type { PoseClip } from "../../lib/pose/types";
import type { Rate } from "../../lib/replay/engine";

// Playwright drives the viewer from here, as `window.__replay` (task 21); a production build
// leaves it out.
const EXPOSE =
  process.env.NODE_ENV === "development" || process.env.NEXT_PUBLIC_EXPOSE_REPLAY === "1";

interface PoseState {
  state: string;
  t: number;
  frameIndex: number;
  frame: number;
  rate: number;
  yaw: number;
  tilt: number;
  // What the pitch drew in this frame: skeletons + discs is every player of the frame.
  skeletons: number;
  discs: number;
  // The followed player and what his own panel shows.
  player: { i: number; shows: "skeleton" | "disc" } | null;
  // One joint of one body as projected for the drawing, in metres of the body frame.
  probe: Probe | null;
  // Animation frames run, paused or not: a pause holds `t` while this keeps counting.
  ticks: number;
}

declare global {
  interface Window {
    __pose?: PoseState;
  }
}

const RATES: Rate[] = [0.5, 1, 2];
const START_TILT = 60;

export function Pose({ clip }: { clip: PoseClip }) {
  const pitch = useRef<HTMLCanvasElement>(null);
  const follow = useRef<HTMLCanvasElement>(null);
  const ticks = useRef(0);
  const [engine] = useState(() => new PoseEngine(clip));
  const [yaw, setYaw] = useState(0);
  const [tilt, setTilt] = useState(START_TILT);
  const [player, setPlayer] = useState<number | null>(null);
  const [, setVersion] = useState(0);
  const rerender = () => setVersion((v) => v + 1);

  useEffect(() => {
    let raf = 0;
    let last: number | undefined;
    let shown = engine.state;
    const loop = (now: number) => {
      ticks.current += 1;
      if (last !== undefined) engine.tick(now - last);
      last = now;
      const frame = engine.frameAt(engine.t);
      const camera = { yaw, tilt };
      const ctx = pitch.current?.getContext("2d");
      const drawn = ctx ? drawPitch(ctx, clip, frame, camera, player) : null;
      const entry = frame.p.find((e) => e[0] === player);
      const followCtx = follow.current?.getContext("2d");
      const shows = entry && followCtx ? drawFollow(followCtx, clip, entry, camera) : null;
      if (EXPOSE && drawn) {
        window.__pose = {
          state: engine.state,
          t: engine.t,
          frameIndex: engine.indexAt(engine.t),
          frame: frame.f,
          rate: engine.rate,
          yaw,
          tilt,
          skeletons: drawn.skeletons,
          discs: drawn.discs,
          player: entry && shows ? { i: entry[0], shows } : null,
          probe: drawn.probe,
          ticks: ticks.current,
        };
      }
      // Every frame while playing, and once more on the tick that ends it.
      if (engine.state === "playing" || engine.state !== shown) setVersion((v) => v + 1);
      shown = engine.state;
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [engine, clip, yaw, tilt, player]);

  const playing = engine.state === "playing";
  const frame = engine.frameAt(engine.t);
  const followed = frame.p.find((e) => e[0] === player);
  const sideOf = (i: number) =>
    clip.teams.find((t) => t.team_id === clip.players[i].team_id)?.side ?? "";
  const nameOf = (i: number) => `${sideOf(i)} ${clip.players[i].number}`;

  return (
    <figure className="pose-viewer" data-state={engine.state}>
      <canvas ref={pitch} width={960} height={640} aria-label="The pitch, each body drawn in its own frame" />
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
        <output aria-label="Frame">frame {frame.f}</output>
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
      </div>
      <div className="controls">
        <span>yaw</span>
        <input
          type="range"
          aria-label="Yaw"
          min={-180}
          max={180}
          step={1}
          value={yaw}
          onChange={(e) => setYaw(Number(e.target.value))}
        />
        <output>{yaw}°</output>
        <span>tilt</span>
        <input
          type="range"
          aria-label="Tilt"
          min={0}
          max={90}
          step={1}
          value={tilt}
          onChange={(e) => setTilt(Number(e.target.value))}
        />
        <output>{tilt}°</output>
      </div>
      <div className="controls">
        <select
          aria-label="Player"
          value={player ?? ""}
          onChange={(e) => setPlayer(e.target.value === "" ? null : Number(e.target.value))}
        >
          <option value="">follow nobody</option>
          {clip.players.map((p, i) => (
            <option key={p.player_id} value={i}>
              follow {nameOf(i)}
            </option>
          ))}
        </select>
      </div>
      {player !== null ? (
        <div className="pose-follow" data-follow={followed?.[4] ? "skeleton" : "disc"}>
          <canvas ref={follow} width={480} height={480} aria-label="The followed body, enlarged in its own frame" />
          <p>
            {nameOf(player)}:{" "}
            {followed?.[4]
              ? "the pose in this frame, centred on its centroid, over a grid through it."
              : "no pose in this frame, so the disc, as on the pitch."}
          </p>
        </div>
      ) : null}
    </figure>
  );
}
