// What the data add to lesson 1 (task 87): `public/data/learn/gravity.json`, written by
// `tracklab learn hypotheses` from the flights P3's gravity check keeps, read at build time.
import gravityJson from "../../public/data/learn/gravity.json";

export interface StartBin {
  n: number;
  g_median: number | null;
}

export interface MatchHypotheses {
  match_id: string;
  is_calibration: boolean;
  flights: number;
  g_median_by_half_window: Record<string, number | null>;
  frames_from_start_median: number | null;
  before_start: number;
  by_frames_from_start: StartBin[];
}

export interface HypothesesFile {
  schema_version: number;
  g_real: number;
  half_windows: number[];
  p3_half_window: number;
  start_bins: (number | null)[][];
  matches: MatchHypotheses[];
}

export const HYPOTHESES = gravityJson as HypothesesFile;

// The `data-fig` path of a figure of gravity.json: `hypotheses.` and a dotted path into the file,
// except that under `matches` the next part is a match id
// (`hypotheses.matches.bb:114086.g_median_by_half_window.4`).
export const hypothesesFig = (match_id: string, path: string): string => `hypotheses.matches.${match_id}.${path}`;

export function hypothesesFigure(data: HypothesesFile, path: string): unknown {
  const parts = path.split(".");
  if (parts[0] !== "hypotheses") return undefined;
  let at: unknown = data;
  for (let i = 1; i < parts.length; i++) {
    if (Array.isArray(at) && parts[i - 1] === "matches") at = at.find((m: MatchHypotheses) => m.match_id === parts[i]);
    else at = at !== null && typeof at === "object" ? (at as Record<string, unknown>)[parts[i]] : undefined;
  }
  return at;
}
