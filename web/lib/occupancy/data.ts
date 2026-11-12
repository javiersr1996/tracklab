import fence from "../learn/fence.json";
import raw from "../../public/data/occupancy.json";

// What /tracking/occupancy draws (task 184b), out of `occupancy.json` (written by `tracklab publish
// occupancy`): one heat map per football position group on one pitch, every team attacking left to
// right. Every figure the page prints is read or summed here from the file; none is typed. The file
// is refused if it names a match the Analytics Cup fence holds out, or if a group's shares do not
// add up to the whole.

export interface OccupancyGroup {
  group: string;
  player_frames: number;
  player_matches: number;
  matches: number;
  off_pitch: number;
  missing: number;
  share: number[];
}

export interface OccupancyFile {
  source: string;
  competition: string;
  season: string;
  sample_rate_hz: number;
  matches: string[];
  frames: number;
  grid: { length_m: number; width_m: number; cols: number; rows: number; cell_length_m: number; cell_width_m: number };
  share_scale: number;
  left_out: { goalkeeper: number; no_group: number };
  groups: OccupancyGroup[];
}

// Thirds along the pitch, own goal first; lanes across it in rows of the grid from row 0, the right
// touchline of a team attacking left to right. Left and right are the team's, facing the goal it attacks.
export const THIRDS = ["own third", "middle third", "attacking third"] as const;
export const LANES = ["right flank", "inside right", "centre", "inside left", "left flank"] as const;

// A cell below this share of its group (in parts of the whole) is left the colour of the pitch.
export const FLOOR = 1e-4;
// The colour steps of the ramp, of equal width in share.
export const STEPS = 8;

export function check(file: OccupancyFile, heldOut: readonly string[] = fence.held_out): OccupancyFile {
  const fenced = file.matches.filter((m) => heldOut.includes(m));
  if (fenced.length) throw new Error(`occupancy.json names held-out matches: ${fenced.join(", ")}`);
  const cells = file.grid.cols * file.grid.rows;
  if (file.grid.cols % 3 || file.grid.rows % LANES.length) throw new Error("the grid does not split into thirds and lanes");
  for (const g of file.groups) {
    if (g.share.length !== cells) throw new Error(`${g.group}: ${g.share.length} cells, not ${cells}`);
    const sum = g.share.reduce((a, b) => a + b, 0);
    if (sum !== file.share_scale) throw new Error(`${g.group}: shares sum to ${sum}, not ${file.share_scale}`);
    if (g.player_frames <= 0) throw new Error(`${g.group}: no player-frame`);
  }
  return file;
}

export const FILE: OccupancyFile = check(raw as OccupancyFile);

export const slug = (group: string) => group.toLowerCase().replaceAll(" ", "-");

// The share (0 to 1) of a group in each third and each lane.
export function regions(file: OccupancyFile, g: OccupancyGroup) {
  const { cols, rows } = file.grid;
  const thirds = THIRDS.map(() => 0);
  const lanes = LANES.map(() => 0);
  g.share.forEach((s, i) => {
    thirds[Math.floor((i % cols) / (cols / 3))] += s;
    lanes[Math.floor(Math.floor(i / cols) / (rows / LANES.length))] += s;
  });
  const scale = (v: number) => v / file.share_scale;
  return { thirds: thirds.map(scale), lanes: lanes.map(scale) };
}

// The largest of `values`, its index first on a tie.
const busiest = (values: number[]) => values.reduce((best, v, i) => (v > values[best] ? i : best), 0);

export const pct = (share: number, digits = 1) => `${(100 * share).toFixed(digits)}%`;

export interface GroupView {
  group: string;
  slug: string;
  player_frames: number;
  player_matches: number;
  matches: number;
  off_pitch: number;
  third: { name: string; share: number };
  lane: { name: string; share: number };
  // The share (0 to 1) in each third and each lane, in the order of THIRDS and LANES.
  thirds: number[];
  lanes: number[];
  // The shares of every cell, 0 to 1, row by row from the right touchline.
  share: number[];
}

export function groupView(file: OccupancyFile, g: OccupancyGroup): GroupView {
  const r = regions(file, g);
  const t = busiest(r.thirds);
  const l = busiest(r.lanes);
  return {
    group: g.group,
    slug: slug(g.group),
    player_frames: g.player_frames,
    player_matches: g.player_matches,
    matches: g.matches,
    off_pitch: g.off_pitch,
    third: { name: THIRDS[t], share: r.thirds[t] },
    lane: { name: LANES[l], share: r.lanes[l] },
    thirds: r.thirds,
    lanes: r.lanes,
    share: g.share.map((s) => s / file.share_scale),
  };
}

// The ramp: one hue, from a dark cyan a step above the pitch through the site's neon to white.
const STOPS: [number, [number, number, number]][] = [
  [0, [10, 58, 74]],
  [0.6, [0, 229, 255]],
  [1, [255, 255, 255]],
];
const hex = (c: number[]) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;

export function ramp(t: number): string {
  const i = STOPS.findIndex(([at]) => at >= t);
  if (i <= 0) return hex(STOPS[0][1]);
  const [a, ca] = STOPS[i - 1];
  const [b, cb] = STOPS[i];
  const k = (t - a) / (b - a);
  return hex(ca.map((v, j) => v + k * (cb[j] - v)));
}

export const COLORS = Array.from({ length: STEPS }, (_, k) => ramp(k / (STEPS - 1)));

// One scale for every map: the step of a share, 0 under the floor, else 1 to STEPS in equal
// slices of the largest share of any cell of any group.
export function stepOf(share: number, top: number): number {
  if (share < FLOOR) return 0;
  return Math.min(STEPS, Math.max(1, Math.ceil((STEPS * share) / top)));
}

// The upper edge of each step, as a share: step k holds the shares up to top * k / STEPS.
export const edges = (top: number) => Array.from({ length: STEPS }, (_, k) => (top * (k + 1)) / STEPS);

// The cells of a map as one SVG path per step, in grid units (col across, row up from the right
// touchline), a run of neighbours in a row drawn as one rectangle.
export function cellPaths(v: GroupView, cols: number, top: number): { step: number; d: string }[] {
  const steps = v.share.map((s) => stepOf(s, top));
  const out = new Map<number, string>();
  for (let i = 0; i < steps.length; ) {
    const k = steps[i];
    let j = i + 1;
    while (j < steps.length && steps[j] === k && j % cols !== 0) j++;
    if (k > 0) out.set(k, (out.get(k) ?? "") + `M${i % cols} ${Math.floor(i / cols)}h${j - i}v1h${i - j}z`);
    i = j;
  }
  return [...out].sort(([a], [b]) => a - b).map(([step, d]) => ({ step, d }));
}

export function occupancyView(file: OccupancyFile = FILE) {
  const groups = file.groups.map((g) => groupView(file, g));
  const top = Math.max(...groups.flatMap((g) => g.share));
  const outfield = groups[groups.length - 1];
  const all = file.groups[file.groups.length - 1];
  return {
    // Of every outfield player-frame read, the share whose position was off its pitch.
    offPitch: all.off_pitch / (all.player_frames + all.off_pitch + all.missing),
    competition: file.competition,
    season: file.season,
    matches: file.matches.length,
    frames: file.frames,
    hz: file.sample_rate_hz,
    hours: file.frames / file.sample_rate_hz / 3600,
    goalkeeperFrames: file.left_out.goalkeeper,
    outfieldFrames: outfield.player_frames,
    grid: file.grid,
    top,
    edges: edges(top),
    groups,
  };
}

export type OccupancyView = ReturnType<typeof occupancyView>;
