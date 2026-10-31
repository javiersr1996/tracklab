import { drawSurface } from "../geometry";
import type { Snapshot } from "./engine";
import type { Possession } from "./types";

const MARGIN_M = 2;
const PLAYER_PX = 9;
const BALL_PX = 4;
const BALL_PX_PER_M = 1.5;

// P1's palette in the site's neon (P13), each a token of globals.css, with its WCAG ratio on the
// canvas (#030712): the markings --canvas-muted (7.9:1), the team with the ball --neon (13.1:1),
// the other --neon-alt (6.2:1), the ball --canvas-hi (20.1:1); the jersey numbers --canvas-ink,
// dark on the discs (13.1:1 on cyan, 6.2:1 on magenta). tests/tokens-contrast.test.ts holds them.
export const COLORS = {
  surface: "#94a3b8",
  attack: "#00e5ff",
  defence: "#ff3ea5",
  ball: "#ffffff",
  text: "#030712",
};

// The home's hero (P12): cyan for the team with the ball, magenta for the other, the ball white
// hot, the markings in a dimmer cyan; jersey numbers dark on the bright discs.
export const NEON_COLORS: typeof COLORS = {
  surface: "rgba(0, 229, 255, 0.6)",
  attack: "#00e5ff",
  defence: "#ff3ea5",
  ball: "#ffffff",
  text: "#030712",
};

// What a frame is drawn with, beyond the frame itself. Every field is optional and `drawFrame`
// with none is P1's renderer unchanged: `/replay`, `/runs` and the lessons pass nothing.
export interface DrawOptions {
  colors?: typeof COLORS;
  // Earlier snapshots of the same possession, oldest first: each entity's path through them
  // is drawn fading behind it (the hero's trails).
  trail?: Snapshot[];
  // Wide, faint strokes under the markings and the discs, so they glow.
  glow?: boolean;
  // The pitch's length down the canvas instead of across it (a portrait phone).
  rotate?: boolean;
  // Discs, numbers and lines this many times their size at 960 px, for a canvas drawn larger.
  markScale?: number;
}

// Positions as the viewer sees them: the venue frame, or rotated 180 degrees so the
// team with the ball attacks towards +x (`attack_sign` is -1 when it attacks -x).
export function viewed(snapshot: Snapshot, possession: Possession, normalized: boolean): Snapshot {
  if (!normalized || possession.attack_sign === 1) return snapshot;
  const k = possession.attack_sign;
  return {
    ...snapshot,
    entities: snapshot.entities.map((e) => ({ ...e, x: e.x * k, y: e.y * k })),
  };
}

// Where the pitch sits on a canvas: pixels per metre and the centre. Rotated, its length runs
// down the canvas, +x up, and the canvas's height is what the length has to fit.
export function layout(
  canvas: { width: number; height: number },
  possession: Pick<Possession, "surface">,
  rotate = false,
) {
  const { length_m, width_m } = possession.surface;
  const along = rotate ? canvas.height : canvas.width;
  const across = rotate ? canvas.width : canvas.height;
  const scale = Math.min(along / (length_m + 2 * MARGIN_M), across / (width_m + 2 * MARGIN_M));
  return { scale, cx: canvas.width / 2, cy: canvas.height / 2, rotate };
}

type Layout = ReturnType<typeof layout>;

// Venue metres to canvas pixels, y up on the canvas and, rotated, +x up as well.
function place(l: Layout, x: number, y: number): [number, number] {
  return l.rotate ? [l.cx - y * l.scale, l.cy - x * l.scale] : [l.cx + x * l.scale, l.cy - y * l.scale];
}

// The same mapping as a canvas transform, for the markings drawn in metres.
function metresTransform(ctx: CanvasRenderingContext2D, l: Layout): void {
  if (l.rotate) ctx.setTransform(0, -l.scale, -l.scale, 0, l.cx, l.cy);
  else ctx.setTransform(l.scale, 0, 0, -l.scale, l.cx, l.cy);
}

// What an overlay needs to draw on top of a frame: venue metres to canvas pixels as
// `drawFrame` places them, and `sign`, the factor the view applies to venue x and y
// (the same `viewed` rotation), so a direction given in the venue frame turns with it.
export interface View {
  project: (x: number, y: number) => [number, number];
  sign: 1 | -1;
}

export function viewOf(
  canvas: { width: number; height: number },
  possession: Pick<Possession, "surface" | "attack_sign">,
  normalized: boolean,
  rotate = false,
): View {
  const l = layout(canvas, possession, rotate);
  const sign = normalized ? possession.attack_sign : 1;
  return { project: (x, y) => place(l, sign * x, sign * y), sign };
}

// A player as P1 draws him: a disc in his team's colour with his number, faded when he is
// not detected. The pose viewer draws a player without a pose with the same disc.
export function drawDisc(
  ctx: CanvasRenderingContext2D,
  px: number,
  py: number,
  color: string,
  jersey: string,
  detected: boolean,
  text = COLORS.text,
  radius = PLAYER_PX,
): void {
  ctx.globalAlpha = detected ? 1 : 0.45;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(px, py, radius, 0, 2 * Math.PI);
  ctx.fill();
  ctx.fillStyle = text;
  ctx.fillText(jersey, px, py);
  ctx.globalAlpha = 1;
}

// The ball, on top. Its radius grows with the provider's z, uncorrected; a null z (not
// measured, or not published) draws it flat.
export function drawBall(
  ctx: CanvasRenderingContext2D,
  px: number,
  py: number,
  z: number | null,
  color = COLORS.ball,
  markScale = 1,
): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(px, py, markScale * (BALL_PX + BALL_PX_PER_M * Math.max(z ?? 0, 0)), 0, 2 * Math.PI);
  ctx.fill();
}

// A soft halo under a mark: the same disc, wider and faint.
function drawGlow(ctx: CanvasRenderingContext2D, px: number, py: number, radius: number, color: string): void {
  ctx.globalAlpha = 0.22;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(px, py, radius, 0, 2 * Math.PI);
  ctx.fill();
  ctx.globalAlpha = 1;
}

// Each entity's path through the trail to where it is now, as segments that brighten and
// widen towards the present, each drawn twice: a wide faint stroke and a thin bright one.
// Returns how many trail samples were drawn behind an entity (0 when the trail is empty).
function drawTrail(
  ctx: CanvasRenderingContext2D,
  l: Layout,
  trail: Snapshot[],
  snapshot: Snapshot,
  colorOf: (i: number) => string,
  widthOf: (i: number) => number,
): number {
  const past = trail.map((s) => new Map(s.entities.map((e) => [e.i, e])));
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  let drawn = 0;
  for (const e of snapshot.entities) {
    const points: [number, number][] = [];
    for (const m of past) {
      const p = m.get(e.i);
      if (p) points.push(place(l, p.x, p.y));
    }
    points.push(place(l, e.x, e.y));
    const n = points.length - 1;
    if (n === 0) continue;
    drawn = Math.max(drawn, n);
    const color = colorOf(e.i);
    const width = widthOf(e.i);
    for (let k = 0; k < n; k++) {
      const f = (k + 1) / n;
      for (const [alpha, w] of [
        [0.1 * f, width * 2.6],
        [0.55 * f, width * 0.9],
      ]) {
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = color;
        ctx.lineWidth = w;
        ctx.beginPath();
        ctx.moveTo(points[k][0], points[k][1]);
        ctx.lineTo(points[k + 1][0], points[k + 1][1]);
        ctx.stroke();
      }
    }
  }
  ctx.globalAlpha = 1;
  return drawn;
}

// Draws one frame; returns how many trail samples it drew behind an entity (0 without a trail).
export function drawFrame(
  ctx: CanvasRenderingContext2D,
  possession: Possession,
  snapshot: Snapshot,
  options: DrawOptions = {},
): number {
  const { colors = COLORS, trail, glow = false, rotate = false, markScale = 1 } = options;
  const { width, height } = ctx.canvas;
  const l = layout(ctx.canvas, possession, rotate);
  const { scale } = l;

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, width, height);

  // Markings in metres, y up.
  metresTransform(ctx, l);
  if (glow) {
    ctx.strokeStyle = colors.surface;
    ctx.globalAlpha = 0.25;
    ctx.lineWidth = (6 * markScale) / scale;
    drawSurface(ctx, possession.surface);
    ctx.globalAlpha = 1;
  }
  ctx.strokeStyle = colors.surface;
  ctx.lineWidth = (1.5 * markScale) / scale;
  drawSurface(ctx, possession.surface);

  // Entities in pixels, so the jersey numbers are not mirrored.
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `bold ${10 * markScale}px system-ui, sans-serif`;
  const byIndex = new Map(possession.entities.map((e) => [e.i, e]));
  const colorOf = (i: number) => {
    const entity = byIndex.get(i);
    if (entity?.kind === "ball") return colors.ball;
    return entity?.team_id === possession.team_in_possession ? colors.attack : colors.defence;
  };
  const playerPx = PLAYER_PX * markScale;
  let trailed = 0;
  if (trail && trail.length > 0) {
    trailed = drawTrail(ctx, l, trail, snapshot, colorOf, (i) =>
      byIndex.get(i)?.kind === "ball" ? BALL_PX * markScale : playerPx,
    );
  }
  let ball: { x: number; y: number; z: number | null } | undefined;
  for (const e of snapshot.entities) {
    const entity = byIndex.get(e.i);
    const [px, py] = place(l, e.x, e.y);
    if (entity?.kind === "ball") {
      ball = { x: px, y: py, z: e.z };
      continue;
    }
    if (glow && e.detected) drawGlow(ctx, px, py, playerPx * 2, colorOf(e.i));
    drawDisc(ctx, px, py, colorOf(e.i), entity?.jersey ?? "", e.detected, colors.text, playerPx);
  }
  // The ball last, on top.
  if (ball) {
    if (glow) drawGlow(ctx, ball.x, ball.y, BALL_PX * markScale * 3, colors.ball);
    drawBall(ctx, ball.x, ball.y, ball.z, colors.ball, markScale);
  }
  return trailed;
}
