import { drawSurface } from "../geometry";
import type { Snapshot } from "./engine";
import type { Possession } from "./types";

const MARGIN_M = 2;
const PLAYER_PX = 9;
const BALL_PX = 4;
const BALL_PX_PER_M = 1.5;

export const COLORS = {
  surface: "#9aa4ad",
  attack: "#e8702a",
  defence: "#2a6fe8",
  ball: "#f5c518",
  text: "#ffffff",
};

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

// Where the pitch sits on a canvas: pixels per metre and the centre.
function layout(canvas: { width: number; height: number }, possession: Possession) {
  const { length_m, width_m } = possession.surface;
  const scale = Math.min(
    canvas.width / (length_m + 2 * MARGIN_M),
    canvas.height / (width_m + 2 * MARGIN_M),
  );
  return { scale, cx: canvas.width / 2, cy: canvas.height / 2 };
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
  possession: Possession,
  normalized: boolean,
): View {
  const { scale, cx, cy } = layout(canvas, possession);
  const sign = normalized ? possession.attack_sign : 1;
  return { project: (x, y) => [cx + sign * x * scale, cy - sign * y * scale], sign };
}

export function drawFrame(
  ctx: CanvasRenderingContext2D,
  possession: Possession,
  snapshot: Snapshot,
): void {
  const { width, height } = ctx.canvas;
  const { scale, cx, cy } = layout(ctx.canvas, possession);

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, width, height);

  // Markings in metres, y up.
  ctx.setTransform(scale, 0, 0, -scale, cx, cy);
  ctx.strokeStyle = COLORS.surface;
  ctx.lineWidth = 1.5 / scale;
  drawSurface(ctx, possession.surface);

  // Entities in pixels, so the jersey numbers are not mirrored.
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "bold 10px system-ui, sans-serif";
  const byIndex = new Map(possession.entities.map((e) => [e.i, e]));
  let ball: { x: number; y: number; z: number | null } | undefined;
  for (const e of snapshot.entities) {
    const entity = byIndex.get(e.i);
    const px = cx + e.x * scale;
    const py = cy - e.y * scale;
    if (entity?.kind === "ball") {
      ball = { x: px, y: py, z: e.z };
      continue;
    }
    ctx.globalAlpha = e.detected ? 1 : 0.45;
    ctx.fillStyle =
      entity?.team_id === possession.team_in_possession ? COLORS.attack : COLORS.defence;
    ctx.beginPath();
    ctx.arc(px, py, PLAYER_PX, 0, 2 * Math.PI);
    ctx.fill();
    ctx.fillStyle = COLORS.text;
    ctx.fillText(entity?.jersey ?? "", px, py);
  }
  ctx.globalAlpha = 1;
  // The ball last, on top. Its radius grows with the provider's z, uncorrected;
  // a null z (not measured) draws it flat.
  if (ball) {
    ctx.fillStyle = COLORS.ball;
    ctx.beginPath();
    ctx.arc(ball.x, ball.y, BALL_PX + BALL_PX_PER_M * Math.max(ball.z ?? 0, 0), 0, 2 * Math.PI);
    ctx.fill();
  }
}
