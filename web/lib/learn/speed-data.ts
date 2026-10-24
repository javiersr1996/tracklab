// Lesson 2's data, read at build time: `public/data/learn/speed.json` (`tracklab learn speed`)
// and the published possession it takes its example from, whose positions P2 rounded to 1 cm.
// Only the server imports this file; the figures get the example's arrays as props.
import possession from "../../public/data/possessions/bb_possessions_possession-114099-1-41.json";
import speedJson from "../../public/data/learn/speed.json";

export interface SpeedMatch {
  match_id: string;
  rows: number;
  triples: number;
  r: number;
  median_gap: number;
  p99_gap: number;
  median_gap_forward: number;
  median_gap_backward: number;
  max_speed: number;
  max_speed_triples: number;
  over_max: number;
  over_max_triples: number;
  window_rows: number;
  by_window: Record<string, number>;
  shaw_rows: number;
  median_gap_shaw: number;
}

export interface SpeedFile {
  schema_version: number;
  fps: number;
  m_per_ft: number;
  max_speed: number;
  shaw_window: number;
  windows: number[];
  resolution_m: number;
  matches: SpeedMatch[];
  example: {
    possession: string;
    possession_id: string;
    match_id: string;
    entity_id: string;
    t0_ms: number;
    frames: number;
    speed: number[];
    full_precision: { frames: number; median_gap: number; max_gap: number };
  };
}

export const SPEED: SpeedFile = speedJson;

// What a figure needs of the example: one player's track over the possession.
export interface SpeedExample {
  match_id: string;
  possession_id: string;
  entity_id: string;
  jersey: string;
  h: number; // seconds between two frames
  resolution: number; // metres, how finely the positions are published
  t_s: number[]; // from the first frame
  x: number[];
  y: number[];
  speed: number[]; // the provider's, m/s
}

interface Possession {
  possession_id: string;
  match: { match_id: string };
  entities: { i: number; entity_id: string; jersey: string | null }[];
  frames: { t: number; o: (number | null)[][] }[];
}

export function speedExample(file: SpeedFile, pos: Possession): SpeedExample {
  const ex = file.example;
  const entity = pos.entities.find((e) => e.entity_id === ex.entity_id);
  if (!entity) throw new Error(`${ex.entity_id} is not in ${ex.possession}`);
  const step = 1000 / file.fps;
  if (pos.frames.length !== ex.frames || pos.frames[0].t !== ex.t0_ms) {
    throw new Error(`speed.json's example does not span ${ex.possession}`);
  }
  const at = pos.frames.map((fr, i) => {
    if (fr.t !== ex.t0_ms + i * step) throw new Error(`${ex.possession}: frame ${i} is not ${step} ms after the last`);
    const o = fr.o.find((row) => row[0] === entity.i);
    if (!o || o[1] === null || o[2] === null) throw new Error(`${ex.entity_id} is missing at frame ${i}`);
    return { t: (fr.t - ex.t0_ms) / 1000, x: o[1], y: o[2] };
  });
  return {
    match_id: pos.match.match_id,
    possession_id: pos.possession_id,
    entity_id: ex.entity_id,
    jersey: entity.jersey ?? "",
    h: 1 / file.fps,
    resolution: file.resolution_m,
    t_s: at.map((a) => a.t),
    x: at.map((a) => a.x),
    y: at.map((a) => a.y),
    speed: ex.speed,
  };
}

export const SPEED_EXAMPLE = speedExample(SPEED, possession as Possession);

// The `data-fig` path of a figure of speed.json: `speed.` and a dotted path into the file, except
// that under `matches` the next part is a match id (`speed.matches.bb:114086.r`).
export const speedFig = (match_id: string, field: string): string => `speed.matches.${match_id}.${field}`;

export function speedFigure(data: SpeedFile, path: string): unknown {
  const parts = path.split(".");
  if (parts[0] !== "speed") return undefined;
  let at: unknown = data;
  for (let i = 1; i < parts.length; i++) {
    if (Array.isArray(at) && parts[i - 1] === "matches") at = at.find((m: SpeedMatch) => m.match_id === parts[i]);
    else at = at !== null && typeof at === "object" ? (at as Record<string, unknown>)[parts[i]] : undefined;
  }
  return at;
}
