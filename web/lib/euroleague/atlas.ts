// The shot atlas of /euroleague (P14, task 116): the shape of the published aggregates
// (`web/public/data/euroleague/`, written by `tracklab euroleague publish`), the FIBA half court
// they sit on and the pure helpers the page draws and prints with. Every figure on the page is a
// field of those files or arithmetic on them; the constants here are the court's FIBA measures
// and the colour scale's cut points, which the legend prints.

export type Zone = "rim" | "mid" | "three";

// `cell_fields` of league.json and of a player: q, r, shots, made, points.
export type Cell = [q: number, r: number, n: number, made: number, pts: number];
// A team's cell adds `diff`: its field-goal % minus the league's in the same cell.
export type TeamCell = [q: number, r: number, n: number, made: number, pts: number, diff: number];

export interface Hex {
  side_m: number;
  layout: string;
  origin: string;
  k: number;
}

export interface LeagueSeason {
  season: string;
  cutoff: string;
  games_played: number;
  shots_total: number;
  shots_shown: number;
  cells: Cell[];
  zones: Record<Zone, { n: number; made: number; pts: number }>;
  unclassified: number;
  teams: { code: string; name: string }[];
}

export interface League {
  version: number;
  source: string;
  hex: Hex;
  cell_fields: string[];
  seasons: LeagueSeason[];
}

export interface Player {
  name: string;
  shots_total: number;
  shots_shown: number;
  cells: Cell[];
}

export interface TeamSeason {
  season: string;
  cutoff: string;
  games_played: number;
  name: string;
  team_games: number;
  shots_total: number;
  shots_shown: number;
  cells: TeamCell[];
  players: Player[];
}

export interface Change {
  season: string;
  attempts: number;
  rim: { n: number; share: number };
  mid: { n: number; share: number };
  three: { n: number; share: number };
  unclassified: number;
  fastbreak: { n: number; share: number };
}

export interface Team {
  version: number;
  source: string;
  code: string;
  name: string;
  hex: Hex;
  cell_fields: string[];
  player_cell_fields: string[];
  player_min_shots: number;
  seasons: TeamSeason[];
  changes: Change[];
}

// What the strip of "what has changed" needs of each team, read at build time.
export interface TeamChanges {
  code: string;
  name: string;
  changes: Change[];
}

// The season still being played (the spec: E2025 closed, E2026 in progress).
export const CURRENT_SEASON = "E2026";

// "E2025" is the 2025-26 season.
export function seasonLabel(season: string): string {
  const year = Number(season.slice(1));
  return `${year}-${String((year + 1) % 100).padStart(2, "0")}`;
}

// --- The court: FIBA measures in cm, origin at the centre of the hoop, y towards half court ---

export const COURT = {
  halfWidth: 750, // 15 m wide
  baseline: -157.5, // the hoop's centre is 1.575 m from the baseline
  midline: 1242.5, // 14 m from the baseline
  three: 675, // the arc: 6.75 m from the hoop
  corner: 660, // the corner lines: 6.60 m from the hoop, 0.90 m in from the sideline
  keyHalfWidth: 245, // the restricted area: 4.9 m wide
  keyLength: 580, // and 5.8 m from the baseline to the far edge of the free-throw line
  circle: 180, // free-throw and centre circles: 1.8 m
  noCharge: 125, // no-charge semicircle: 1.25 m
  backboard: -37.5, // its face, 1.2 m from the baseline
  backboardHalf: 90, // 1.8 m wide
  hoop: 22.5, // 45 cm ring
} as const;

// Where the corner lines meet the arc: y = sqrt(6.75² - 6.60²) m above the hoop.
export const CORNER_TOP = Math.sqrt(COURT.three ** 2 - COURT.corner ** 2);

// The SVG draws y upward (the hoop at the bottom, as seen from above), so a point (x, y) of the
// data is (x, -y) on screen: no mirror.
export const VIEW = { x: -880, y: -1460, width: 1760, height: 1730 } as const;

const r1 = (v: number) => Math.round(v * 10) / 10;

// The court's lines, as SVG path data in screen units (cm, y flipped).
export function courtPaths(): { outline: string; lines: string; dashed: string; hoop: { cy: number; r: number } } {
  const c = COURT;
  const base = -c.baseline; // screen y of the baseline
  const mid = -c.midline;
  const ft = -(c.baseline + c.keyLength); // screen y of the free-throw line
  const top = -CORNER_TOP;
  const outline = `M${-c.halfWidth},${base}H${c.halfWidth}V${mid}H${-c.halfWidth}Z`;
  const lines = [
    // the three-point line: corner, arc through (0, 6.75 m), corner
    `M${-c.corner},${base}V${r1(top)}A${c.three},${c.three} 0 0 1 ${c.corner},${r1(top)}V${base}`,
    // the restricted area
    `M${-c.keyHalfWidth},${base}V${ft}H${c.keyHalfWidth}V${base}`,
    // the free-throw circle, its half outside the key
    `M${-c.circle},${ft}A${c.circle},${c.circle} 0 0 1 ${c.circle},${ft}`,
    // the no-charge semicircle and its two short lines to the backboard
    `M${-c.noCharge},${-c.backboard}V0A${c.noCharge},${c.noCharge} 0 0 1 ${c.noCharge},0V${-c.backboard}`,
    // the backboard
    `M${-c.backboardHalf},${-c.backboard}H${c.backboardHalf}`,
    // the centre circle, the half on this side of the midline
    `M${-c.circle},${mid}A${c.circle},${c.circle} 0 0 0 ${c.circle},${mid}`,
  ].join("");
  // the free-throw circle's half inside the key, dashed
  const dashed = `M${-c.circle},${ft}A${c.circle},${c.circle} 0 0 0 ${c.circle},${ft}`;
  return { outline, lines, dashed, hoop: { cy: 0, r: c.hoop } };
}

// --- The hexagons: pointy top, axial (q, r), origin at the hoop (aggregates.py::hex_cell) ---

const SQRT3 = Math.sqrt(3);

// The centre of cell (q, r) in cm, data axes (y towards half court).
export function hexCenter(q: number, r: number, sideCm: number): [number, number] {
  return [sideCm * SQRT3 * (q + r / 2), sideCm * 1.5 * r];
}

// The cell a point (cm, data axes) falls in: aggregates.py::hex_cell line for line, cube rounding
// with floor(v + 0.5). The pointer is resolved to a whole cell this way, so a hexagon drawn small
// for its few shots is still as easy to touch as a full one.
export function cellAt(x: number, y: number, sideCm: number): [number, number] {
  const qf = ((SQRT3 / 3) * x - y / 3) / sideCm;
  const rf = ((2 / 3) * y) / sideCm;
  const sf = -qf - rf;
  let [q, r] = [Math.floor(qf + 0.5), Math.floor(rf + 0.5)];
  const s = Math.floor(sf + 0.5);
  const [dq, dr, ds] = [Math.abs(q - qf), Math.abs(r - rf), Math.abs(s - sf)];
  if (dq > dr && dq > ds) q = -r - s;
  else if (dr > ds) r = -q - s;
  return [q + 0, r + 0]; // never -0
}

// A pointy-top hexagon of circumradius `radius` around screen point (cx, cy), as path data.
export function hexPath(cx: number, cy: number, radius: number): string {
  const pts = [-90, -30, 30, 90, 150, 210].map((deg) => {
    const a = (deg * Math.PI) / 180;
    return `${r1(cx + radius * Math.cos(a))},${r1(cy + radius * Math.sin(a))}`;
  });
  return `M${pts.join("L")}Z`;
}

// Size by volume: the area grows with the shots, full size from `full` shots up, and never under
// MIN_SCALE so a hexagon of k shots stays visible. A gap is left between full hexagons.
export const MIN_SCALE = 0.3;
export const MAX_SCALE = 0.92;

export function hexScale(n: number, full: number): number {
  return MAX_SCALE * Math.max(MIN_SCALE, Math.min(1, Math.sqrt(n / full)));
}

// The volume at which a hexagon is full size: the 90th percentile of the selection's cells, so a
// few cells at the rim do not shrink the rest to dots.
export function fullAt(ns: readonly number[]): number {
  if (ns.length === 0) return 1;
  const sorted = [...ns].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.9))];
}

// --- The colour: against the league ---

export type Tone = "lo" | "down" | "mid" | "up" | "hi";
export const TONES: readonly Tone[] = ["hi", "up", "mid", "down", "lo"];

// "fg": a team's or a player's field-goal % minus the league's in the same cell (a fraction).
// "pps": the league's own cells, points per shot minus the league's average points per shot.
export type Mode = "fg" | "pps";

// The cut points the legend prints: within `near` of the league is neutral; `well` or more away
// is the full colour.
export const CUTS: Record<Mode, { near: number; well: number }> = {
  fg: { near: 0.03, well: 0.1 },
  pps: { near: 0.05, well: 0.2 },
};

export function toneOf(diff: number, mode: Mode): Tone {
  const { near, well } = CUTS[mode];
  // The JSON's diff has three decimals: compare on that grid, so 0.03 is "up", not "mid".
  const d = Math.round(diff * 1000) / 1000;
  if (d >= well) return "hi";
  if (d >= near) return "up";
  if (d > -near) return "mid";
  if (d > -well) return "down";
  return "lo";
}

// How much of the colour a cell keeps. A cell with FULL_FADE_N shots or more keeps all of it; one
// with only the fewest the files publish (`k`) keeps MIN_FADE (the 65% keeps the second tone at 3:1
// on the canvas); in between it is a straight ramp on the shots.
export const MIN_FADE = 0.65;
export const FULL_FADE_N = 10;

export function fade(n: number, k: number): number {
  if (n >= FULL_FADE_N) return 1;
  if (n <= k) return MIN_FADE;
  return MIN_FADE + ((1 - MIN_FADE) * (n - k)) / (FULL_FADE_N - k);
}

// --- What a selection draws ---

export interface Drawn {
  q: number;
  r: number;
  n: number;
  made: number;
  pts: number;
  // fg: this cell's % minus the league's in it; pps: points per shot minus the league average.
  diff: number;
  // fg only: the league's % in the same cell, without the team's or the player's own shots.
  league?: number;
  // The standard error of the cell's own value: of its field-goal % (fg) or of its points a shot (pps).
  se: number;
}

const r3 = (v: number) => Math.round(v * 1000) / 1000 || 0;

// The standard error of a cell's field-goal % (a fraction), from a proportion nudged by one made
// and one missed shot (the "plus-two" rule), so a cell that made all or none of its shots does not
// claim an error of 0.
export function shotSe(made: number, n: number): number {
  const p = (made + 1) / (n + 2);
  return Math.sqrt((p * (1 - p)) / (n + 2));
}

// The standard error of a cell's points a shot: every make in a cell is worth the same, pts/made,
// so the points a shot are that value times a make-or-miss with the field-goal % above.
export function pointsSe(made: number, pts: number, n: number): number {
  return (made === 0 ? 2 : pts / made) * shotSe(made, n);
}

// The league's average points per shot over the cells it shows.
export function leagueAverage(cells: readonly Cell[]): number {
  const n = cells.reduce((s, c) => s + c[2], 0);
  const pts = cells.reduce((s, c) => s + c[4], 0);
  return n === 0 ? 0 : pts / n;
}

export function leagueDrawn(cells: readonly Cell[]): Drawn[] {
  const avg = leagueAverage(cells);
  return cells.map(([q, r, n, made, pts]) => ({
    q,
    r,
    n,
    made,
    pts,
    diff: r3(pts / n - avg),
    se: pointsSe(made, pts, n),
  }));
}

const key = (q: number, r: number) => `${q},${r}`;

// A team's or a player's cell against the league's in the same hexagon *without their own shots*:
// the league's cells include them, so against the whole league a team that takes many shots there
// is compared with itself. The league's % there is what is left once their made and shots are taken
// out. If nothing is left (it does not happen in the files), the whole league's % stands.
function againstRest(l: Cell | undefined, made: number, n: number): number | undefined {
  if (!l) return undefined;
  return l[2] > n ? (l[3] - made) / (l[2] - n) : l[3] / l[2];
}

// A team's cells carry a diff against the whole league (league.json's cells include the team): the
// one drawn here is the cell's % minus the rest of the league's, to the same three decimals.
export function teamDrawn(cells: readonly TeamCell[], league: readonly Cell[]): Drawn[] {
  const byKey = new Map(league.map((c) => [key(c[0], c[1]), c]));
  return cells.map(([q, r, n, made, pts, diff]) => {
    const rest = againstRest(byKey.get(key(q, r)), made, n);
    return {
      q,
      r,
      n,
      made,
      pts,
      diff: rest === undefined ? diff : r3(made / n - rest),
      league: rest,
      se: shotSe(made, n),
    };
  });
}

// A player's cells carry no diff: it is computed as a team's is here, the cell's % minus the rest of
// the league's in the same cell, to three decimals. A player's cell of k shots or more lies in a
// league cell of k or more, so the league cell is always there.
export function playerDrawn(cells: readonly Cell[], league: readonly Cell[]): Drawn[] {
  const byKey = new Map(league.map((c) => [key(c[0], c[1]), c]));
  return cells.flatMap(([q, r, n, made, pts]) => {
    const rest = againstRest(byKey.get(key(q, r)), made, n);
    if (rest === undefined) return [];
    return [{ q, r, n, made, pts, diff: r3(made / n - rest), league: rest, se: shotSe(made, n) }];
  });
}

// Reading order for the keyboard and the entry's stagger: top to bottom on screen (far from the
// hoop first), then left to right.
export function readingOrder(cells: readonly Drawn[]): Drawn[] {
  return [...cells].sort((a, b) => b.r - a.r || a.q - b.q);
}

// --- How the figures are printed ---

export const MINUS = "−";

export const pct = (made: number, n: number) => `${((made / n) * 100).toFixed(1)}%`;

// A difference of percentages, in percentage points with its sign.
export function signedPp(diff: number): string {
  const v = Math.round(diff * 1000) / 10;
  if (v === 0) return "0.0 pp";
  return `${v > 0 ? "+" : MINUS}${Math.abs(v).toFixed(1)} pp`;
}

export function signedPts(diff: number): string {
  const v = Math.round(diff * 100) / 100;
  if (v === 0) return "0.00";
  return `${v > 0 ? "+" : MINUS}${Math.abs(v).toFixed(2)}`;
}

export const perShot = (pts: number, n: number) => (pts / n).toFixed(2);

// How far a cell's centre is from the hoop, in metres.
export function metresFromHoop(q: number, r: number, sideCm: number): string {
  const [x, y] = hexCenter(q, r, sideCm);
  return (Math.hypot(x, y) / 100).toFixed(1);
}

// A share as the strip prints it inside a bar: a whole percentage.
export const wholePct = (share: number) => `${Math.round(share * 100)}%`;
