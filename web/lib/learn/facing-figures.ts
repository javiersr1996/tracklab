// Every figure the text of lesson 11 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are the two clips' hook players, frame by frame, and every qualifying player's summary
// (`facing-data.ts`); the constants are the lesson's own.
import { mean } from "./cadence";
import { shown } from "./expose";
import { BACK_DEG, circular, MIN_FRAMES, MIN_SPEED_M_S, SIDE_DEG, summarise } from "./facing";
import type { ClipFacing, HookPlayer, PlayerFacing } from "./facing-data";

// Two angles either side of the back, for the text's example of a mean that needs the circle.
export const DEMO_DEG: readonly [number, number] = [170, -170];

// What one player's frames say, the first frame apart (the figure opens on it).
export function hookFigures(h: HookPlayer, fps: number) {
  const s = summarise(h.frames);
  const [first] = h.frames;
  const widest = h.frames.reduce((best, x) => (Math.abs(x.relative) > Math.abs(best.relative) ? x : best), first);
  const speeds = h.frames.map((x) => x.speed);
  return {
    frames: s.frames,
    seconds: shown(s.frames / fps, 2),
    first_frame_id: first.f,
    first_speed: shown(first.speed, 2),
    first_facing: shown(first.facing, 3),
    first_heading: shown(first.heading, 3),
    first_relative: shown(first.relative, 3),
    speed_lo: shown(Math.min(...speeds), 2),
    speed_hi: shown(Math.max(...speeds), 2),
    median_abs: shown(s.median_abs, 3),
    circ_mean: shown(s.circ_mean, 3),
    resultant: shown(s.resultant, 3),
    circ_var: shown(s.circ_var, 3),
    off_pct: shown(s.off_pct, 1),
    back_pct: shown(s.back_pct, 1),
    widest_frame_id: widest.f,
    widest_relative: shown(widest.relative, 3),
  };
}

export interface PlayerRow {
  index: number;
  team_id: number;
  number: number;
  frames: number;
  median_abs: number;
  circ_mean: number;
  circ_var: number;
  off_pct: number;
}

// Every qualifying player's row, rounded as the table prints it, in the file's order.
export const playerRows = (players: readonly PlayerFacing[]): PlayerRow[] =>
  players.map((p) => ({
    index: p.index,
    team_id: p.team_id,
    number: p.number,
    frames: p.frames,
    median_abs: shown(p.median_abs, 3),
    circ_mean: shown(p.circ_mean, 3),
    circ_var: shown(p.circ_var, 3),
    off_pct: shown(p.off_pct, 1),
  }));

// Per clip: how many players qualify and the span of their rows.
export function clipFigures(rows: readonly PlayerRow[]) {
  const widest = rows.reduce((best, r) => (r.median_abs > best.median_abs ? r : best), rows[0]);
  return {
    players: rows.length,
    forward: rows.filter((r) => r.median_abs < SIDE_DEG).length,
    median_lo: Math.min(...rows.map((r) => r.median_abs)),
    median_hi: Math.max(...rows.map((r) => r.median_abs)),
    var_lo: Math.min(...rows.map((r) => r.circ_var)),
    var_hi: Math.max(...rows.map((r) => r.circ_var)),
    off_lo: Math.min(...rows.map((r) => r.off_pct)),
    off_hi: Math.max(...rows.map((r) => r.off_pct)),
    widest_team: widest.team_id,
    widest_number: widest.number,
    widest_median: widest.median_abs,
  };
}

export function facingFigures(clips: readonly ClipFacing[]) {
  const [first] = clips;
  const demo = circular(DEMO_DEG);
  return {
    min_speed: MIN_SPEED_M_S,
    min_frames: MIN_FRAMES,
    side_deg: SIDE_DEG,
    back_deg: BACK_DEG,
    step_ms: shown(1000 / first.fps, 0),
    span_ms: shown(2000 / first.fps, 0),
    clip_frames: first.clip_frames,
    clip_seconds: shown(first.clip_frames / first.fps, 0),
    demo_a: DEMO_DEG[0],
    demo_b: DEMO_DEG[1],
    demo_arith: shown(mean(DEMO_DEG), 0),
    demo_circ: shown(demo.mean, 0),
    demo_resultant: shown(demo.resultant, 3),
    hook: Object.fromEntries(clips.map((c) => [c.match_id, hookFigures(c.hook, c.fps)])),
    players: Object.fromEntries(clips.map((c) => [c.match_id, playerRows(c.players)])),
    clip: Object.fromEntries(clips.map((c) => [c.match_id, clipFigures(playerRows(c.players))])),
  };
}

export type FacingFigures = ReturnType<typeof facingFigures>;
