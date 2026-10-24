// Lesson 6's data, read at build time: `public/data/learn/clock.json` (`tracklab learn clock`) and
// the two published possessions its examples name, whose frames carry `t` (the video's clock, ms)
// and `clock` (the game clock, s, at two decimals). Only the server imports this file; the figure
// gets the examples as props.
import clockJson from "../../public/data/learn/clock.json";
import bb114086 from "../../public/data/possessions/bb_possessions_possession-114086-1-36.json";
import bb184439 from "../../public/data/possessions/bb_possessions_possession-184439-2-38.json";

export interface ClockMatch {
  match_id: string;
  calibration: boolean;
  segments: number;
  frames: number;
  steps: number;
  held: number;
  slope_median: number;
  slope_q1: number;
  slope_q3: number;
}

export interface ClockExampleEntry {
  possession: string;
  match_id: string;
  calibration: boolean;
  frames: number;
  stopped: number[][]; // [first, last] wallClock (ms) of each stretch the flag says is stopped
}

export interface ClockFile {
  schema_version: number;
  fps: number;
  min_frames: number;
  digits: number;
  matches: ClockMatch[];
  examples: ClockExampleEntry[];
}

export const CLOCK = clockJson as ClockFile;

// An example as the figure draws it: time from the possession's first frame (s), the game clock
// (s), and the stopped stretches as [first, last] indices of those frames.
export interface ClockExample {
  key: "calibration" | "control";
  possession: string;
  match_id: string;
  t: number[];
  clock: number[];
  stopped: [number, number][];
}

const FILES: Record<string, { frames: { t: number; clock: number }[] }> = {
  "bb_possessions_possession-114086-1-36.json": bb114086,
  "bb_possessions_possession-184439-2-38.json": bb184439,
};

export function clockExample(entry: ClockExampleEntry): ClockExample {
  const file = FILES[entry.possession];
  if (!file) throw new Error(`clock.json names ${entry.possession}, which this lesson does not read`);
  const t0 = file.frames[0].t;
  const step = 1000 / CLOCK.fps;
  if (file.frames.length !== entry.frames) throw new Error(`${entry.possession}: ${file.frames.length} frames, clock.json says ${entry.frames}`);
  return {
    key: entry.calibration ? "calibration" : "control",
    possession: entry.possession,
    match_id: entry.match_id,
    t: file.frames.map((f) => (f.t - t0) / 1000),
    clock: file.frames.map((f) => f.clock),
    stopped: entry.stopped.map(([a, b]) => [(a - t0) / step, (b - t0) / step] as [number, number]),
  };
}

export const CLOCK_EXAMPLES: ClockExample[] = CLOCK.examples.map(clockExample);
