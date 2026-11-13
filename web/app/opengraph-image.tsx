import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { POSSESSIONS } from "../lib/data";
import { basketballPrimitives } from "../lib/geometry/basketball";
import type { Primitive } from "../lib/geometry/primitives";
import { OG_SIZE, OG_TYPE, ogFonts } from "../lib/learn/og";
import type { Possession } from "../lib/replay/types";
import { AUTHOR } from "../lib/sections";

// The card for every page that has no image of its own (P19, task 150; drawn in P20, task 172):
// the lessons, /sql and /euroleague keep theirs. Beside the words, the home hero's first
// basketball possession at its last frame, on the half court it attacks, each player and the ball
// with the path of its last two seconds fading behind it. Nothing is placed by hand: the court is
// lib/geometry's FIBA markings, the marks are the possession file's. The palette is the hero's
// (lib/replay/render.ts NEON_COLORS): cyan the team with the ball, magenta the other, the ball
// white, the markings cyan at 60%.
export const size = OG_SIZE;
export const contentType = OG_TYPE;
export const alt = `Track Lab: watch a possession, then ask it a question. A basketball possession's last two seconds on a half court. A personal learning project by ${AUTHOR.name}.`;

const TRAIL_S = 2;
const SAMPLES = 10;
const COLORS = { line: "rgba(0, 229, 255, 0.6)", attack: "#00e5ff", defence: "#ff3ea5", ball: "#ffffff" };

// One marking as SVG, in metres (y down, so an angle grows clockwise, SVG's sweep 1).
function marking(p: Primitive, key: number) {
  const stroke = { stroke: COLORS.line, strokeWidth: 0.07, fill: "none" };
  if (p.kind === "line") return <line key={key} x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} {...stroke} />;
  if (p.kind === "rect") return <rect key={key} x={p.x} y={p.y} width={p.w} height={p.h} {...stroke} />;
  if (p.kind === "circle") return <circle key={key} cx={p.cx} cy={p.cy} r={p.r} {...stroke} />;
  const at = (a: number) => `${p.cx + p.r * Math.cos(a)} ${p.cy + p.r * Math.sin(a)}`;
  const large = p.end - p.start > Math.PI ? 1 : 0;
  return <path key={key} d={`M ${at(p.start)} A ${p.r} ${p.r} 0 ${large} 1 ${at(p.end)}`} {...stroke} />;
}

async function lastSeconds() {
  const entry = POSSESSIONS.find((p) => p.sport === "basketball")!;
  const possession = JSON.parse(await readFile(join(process.cwd(), "public", "data", entry.file), "utf-8")) as Possession;
  const { frames, entities, surface } = possession;
  // As the hero shows it: the team with the ball attacks towards +x.
  const k = possession.attack_sign;
  const span = Math.round(TRAIL_S * possession.sample_rate_hz);
  const picks = Array.from({ length: SAMPLES + 1 }, (_, s) => frames[Math.max(0, frames.length - 1 - span + Math.round((s * span) / SAMPLES))]);
  const marks = entities.map((e) => {
    const path = picks.flatMap((f) => {
      const o = f.o.find((x) => x[0] === e.i);
      return o ? [[o[1] * k, o[2] * k] as const] : [];
    });
    const color = e.kind === "ball" ? COLORS.ball : e.team_id === possession.team_in_possession ? COLORS.attack : COLORS.defence;
    return { kind: e.kind, color, path };
  });
  return { surface, marks };
}

export default async function Image() {
  const { surface, marks } = await lastSeconds();
  const half = surface.length_m / 2;
  const w = surface.width_m / 2;
  // The attacked half, a metre of margin round it.
  const view = { x: -0.6, y: -w - 0.6, width: half + 1.2, height: surface.width_m + 1.2 };
  const courtHeight = OG_SIZE.height - 2 * 36;
  const courtWidth = Math.round((courtHeight * view.width) / view.height);
  const players = [...marks.filter((m) => m.kind === "player"), ...marks.filter((m) => m.kind === "ball")];

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", position: "relative", background: "#030712", fontFamily: "JetBrains Mono" }}>
        <svg
          width={courtWidth}
          height={courtHeight}
          viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
          style={{ position: "absolute", right: 40, top: 36 }}
        >
          {basketballPrimitives(surface.length_m, surface.width_m).map(marking)}
          {players.map((m, i) => (
            <g key={i}>
              {m.path.slice(1).map(([x, y], s) => (
                <line
                  key={s}
                  x1={m.path[s][0]}
                  y1={m.path[s][1]}
                  x2={x}
                  y2={y}
                  stroke={m.color}
                  strokeWidth={m.kind === "ball" ? 0.12 : 0.3}
                  strokeLinecap="round"
                  strokeOpacity={0.06 + (0.5 * (s + 1)) / m.path.length}
                />
              ))}
              {m.path.slice(-1).map(([x, y]) => [
                <circle key="glow" cx={x} cy={y} r={m.kind === "ball" ? 0.55 : 0.75} fill={m.color} fillOpacity={0.18} />,
                <circle key="mark" cx={x} cy={y} r={m.kind === "ball" ? 0.2 : 0.36} fill={m.color} stroke="#030712" strokeWidth={m.kind === "ball" ? 0.05 : 0} />,
              ])}
            </g>
          ))}
        </svg>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", width: 640, height: "100%", padding: "56px 0 56px 64px", color: "#e2e8f0" }}>
          <div style={{ display: "flex", fontSize: 26, letterSpacing: 3, textTransform: "uppercase", color: "#00e5ff" }}>Open tracking data</div>
          {/* The home's headline since P23, its second half lit as there, in four lines as on a phone. */}
          <div style={{ display: "flex", flexDirection: "column", fontSize: 64, lineHeight: 1.12, letterSpacing: -1, color: "#ffffff" }}>
            <div style={{ display: "flex" }}>Watch a</div>
            <div style={{ display: "flex" }}>possession,</div>
            <div style={{ display: "flex", color: "#00e5ff" }}>then ask it</div>
            <div style={{ display: "flex", color: "#00e5ff" }}>a question</div>
          </div>
          <div style={{ display: "flex", fontSize: 26, lineHeight: 1.35, color: "#94a3b8" }}>
            A personal learning project by {AUTHOR.name}
          </div>
          <div style={{ display: "flex", fontSize: 44, letterSpacing: -1, color: "#ffffff" }}>
            track<span style={{ color: "#00e5ff" }}>lab</span>
          </div>
        </div>
      </div>
    ),
    { ...OG_SIZE, fonts: await ogFonts() },
  );
}
