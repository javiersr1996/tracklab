// Lesson 7's data, read at build time: `public/data/learn/pass.json` (`tracklab learn pass`) and the
// published possession its example names, whose frames carry the ball's x, y and z (m, at two
// decimals) and every player's x and y. Only the server imports this file; the figure gets the
// example's passes as props.
import passJson from "../../public/data/learn/pass.json";
import bb114099 from "../../public/data/possessions/bb_possessions_possession-114099-1-41.json";
import type { Point3 } from "./pass";

export interface PassMatch {
  match_id: string;
  complete: number;
  forward: number;
  n: number;
  chord_speed_median: number;
  chord_speed_p90: number;
  path_over_chord: number;
  distance_speed_median: number;
  chord_over_distance: number;
  separation_n: number;
  separation_gap_max: number;
}

export interface PassEntry {
  pass_id: string;
  t0: number;
  t1: number;
  frames: number;
  distance_m: number;
  passer: number;
  receiver: number;
  chord_m: number;
  path_m: number;
  chord_speed: number;
}

export interface PassFile {
  schema_version: number;
  fps: number;
  m_per_ft: number;
  matches: PassMatch[];
  example: { possession: string; match_id: string; passes: PassEntry[] };
}

export const PASS = passJson as PassFile;

type Row = (number | null)[];
interface PossessionFile {
  entities: { i: number; kind: string }[];
  frames: { t: number; o: Row[] }[];
}

const FILES: Record<string, PossessionFile> = { "bb_possessions_possession-114099-1-41.json": bb114099 as PossessionFile };

// A pass as the figure draws it: the ball at every frame from start to end (m), time from the
// start (s), and the passer and the receiver where they stand at the start and at the end.
export interface PassExample {
  entry: PassEntry;
  t: number[];
  ball: Point3[];
  passer: [number, number][];
  receiver: [number, number][];
}

export function passExamples(file: PassFile): PassExample[] {
  const pos = FILES[file.example.possession];
  if (!pos) throw new Error(`pass.json names ${file.example.possession}, which this lesson does not read`);
  const ball = pos.entities.find((e) => e.kind === "ball")!.i;
  const byT = new Map(pos.frames.map((f) => [f.t, f.o]));
  const at = (t: number, i: number): Row => {
    const row = byT.get(t)?.find((o) => o[0] === i);
    if (!row) throw new Error(`${file.example.possession}: no entity ${i} at ${t} ms`);
    return row;
  };
  const step = 1000 / file.fps;
  return file.example.passes.map((entry) => {
    const ts = Array.from({ length: entry.frames + 1 }, (_, k) => entry.t0 + k * step);
    const xy = (i: number, t: number): [number, number] => [at(t, i)[1]!, at(t, i)[2]!];
    return {
      entry,
      t: ts.map((t) => (t - entry.t0) / 1000),
      ball: ts.map((t) => {
        const r = at(t, ball);
        return [r[1]!, r[2]!, r[3]!] as const;
      }),
      passer: [xy(entry.passer, entry.t0), xy(entry.passer, entry.t1)],
      receiver: [xy(entry.receiver, entry.t0), xy(entry.receiver, entry.t1)],
    };
  });
}

export const PASS_EXAMPLES = passExamples(PASS);
