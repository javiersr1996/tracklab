// Lesson 9's data, read at build time: `public/data/learn/dribble.json` (`tracklab learn dribble`)
// and the published possession its example names, whose frames carry the ball's height (m, at two
// decimals). Only the server imports this file; the figure gets the touch's heights as props.
import dribbleJson from "../../public/data/learn/dribble.json";
import bb114086 from "../../public/data/possessions/bb_possessions_possession-114086-1-36.json";

export interface DribbleMatch {
  match_id: string;
  dribbles: number;
  intervals: number;
  interval_median_s: number;
  interval_p10_s: number;
  interval_p90_s: number;
  touches_3: number;
  windows: number;
  offset_median: number;
  offset_abs_median: number;
  near_pct: number;
  edge_pct: number;
  low_z_median: number;
  pairs: number;
  shared_low: number;
}

export interface DribbleEvent {
  t: number;
  offset: number;
  low_z: number;
}

export interface DribbleFile {
  schema_version: number;
  fps: number;
  reach: number;
  near: number;
  touch_min: number;
  m_per_ft: number;
  matches: DribbleMatch[];
  example: { possession: string; match_id: string; touch_id: string; t0: number; t1: number; dribbles: DribbleEvent[] };
}

export const DRIBBLE = dribbleJson as DribbleFile;

type Row = (number | null)[];
interface PossessionFile {
  entities: { i: number; kind: string }[];
  frames: { t: number; o: Row[] }[];
}

const FILES: Record<string, PossessionFile> = { "bb_possessions_possession-114086-1-36.json": bb114086 as PossessionFile };

// The touch as the figure draws it: the ball's height at every frame from `first` (the touch's
// first frame less the window's reach) to its last plus the reach, and the dribbles' frames.
export interface TouchExample {
  fps: number;
  reach: number;
  first: number; // frame of z[0]
  z: (number | null)[];
  start: number; // the touch's first and last frames
  end: number;
  dribbles: number[];
  file: DribbleEvent[];
}

export function touchExample(file: DribbleFile): TouchExample {
  const ex = file.example;
  const pos = FILES[ex.possession];
  if (!pos) throw new Error(`dribble.json names ${ex.possession}, which this lesson does not read`);
  const step = 1000 / file.fps;
  const ball = pos.entities.find((e) => e.kind === "ball")!.i;
  const byFrame = new Map(pos.frames.map((f) => [f.t / step, f.o.find((o) => o[0] === ball)?.[3] ?? null]));
  const start = ex.t0 / step;
  const end = ex.t1 / step;
  const first = start - file.reach;
  const z = Array.from({ length: end + file.reach - first + 1 }, (_, i) => byFrame.get(first + i) ?? null);
  return { fps: file.fps, reach: file.reach, first, z, start, end, dribbles: ex.dribbles.map((d) => d.t / step), file: ex.dribbles };
}

export const TOUCH = touchExample(DRIBBLE);
