// Lesson 4's data, read at build time: `public/data/learn/rebound.json` (`tracklab learn rebound`).
// Only the server imports this file; the race figure gets the example as a prop.
import reboundJson from "../../public/data/learn/rebound.json";
import type { Point, Runner } from "./rebound";

export interface ReboundMatch {
  match_id: string;
  rebounds: number;
  by_player: number;
  field_goal: number;
  located: number;
  after_end: number;
  n: number;
  model: number;
  nearest: number;
  same: number;
  by_reaction: number[];
  confidence: number | null;
  median_wait_s: number | null;
}

export interface ReboundPlayer extends Runner {
  jersey: string;
  team: string; // "shooting" or "defending"
}

export interface ReboundExample {
  match_id: string;
  rebound_id: string;
  shot_id: string;
  end_frame: number;
  frame: number;
  wait_s: number;
  basket_side: number;
  target: Point;
  players: ReboundPlayer[];
  rebounder: number;
  nearest: number;
  model: number;
  times: number[];
  chance_first: number[];
}

export interface ReboundFile {
  schema_version: number;
  fps: number;
  players: number;
  reaction_s: number;
  top_speed: number;
  spread_s: number;
  reactions: number[];
  digits: number;
  matches: ReboundMatch[];
  example: ReboundExample;
}

export const REBOUND: ReboundFile = reboundJson;

// The `data-fig` path of a figure of rebound.json: `rebound.` and a dotted path into the file,
// except that under `matches` the next part is a match id (`rebound.matches.bb:114086.n`).
export const reboundFig = (match_id: string, field: string): string => `rebound.matches.${match_id}.${field}`;

export function reboundFigure(data: ReboundFile, path: string): unknown {
  const parts = path.split(".");
  if (parts[0] !== "rebound") return undefined;
  let at: unknown = data;
  for (let i = 1; i < parts.length; i++) {
    if (Array.isArray(at) && parts[i - 1] === "matches") at = at.find((m: ReboundMatch) => m.match_id === parts[i]);
    else at = at !== null && typeof at === "object" ? (at as Record<string, unknown>)[parts[i]] : undefined;
  }
  return at;
}

// A player as the text names them: their team, then their shirt.
export const playerName = (p: Pick<ReboundPlayer, "team" | "jersey">) => `${p.team} ${p.jersey}`;
