// The figures "What the data add" (lesson 1, task 87) computes from gravity.json, as the page
// prints them: `data-fig="learn.hyp.<key>"`, and the same object in `window.__learn.hyp`. Every one
// is a count or an extreme over the matches' rows; no median is recomputed here.
import type { HypothesesFile } from "./hypotheses-data";

export function hypothesesFigures(file: HypothesesFile) {
  const m = file.matches;
  const cells = m.flatMap((r) => file.half_windows.map((h) => ({ match_id: r.match_id, h, g: r.g_median_by_half_window[String(h)] })));
  const valued = cells.filter((c): c is { match_id: string; h: number; g: number } => c.g !== null);
  const highest = valued.reduce((best, c) => (c.g > best.g ? c : best));
  const lowest = valued.reduce((best, c) => (c.g < best.g ? c : best));
  const starts = m.map((r) => r.frames_from_start_median).filter((v): v is number => v !== null);
  const before = m.filter((r) => r.before_start > 0);
  // Matches with flights in the bin nearest the hand and in at least one other: is the nearest
  // bin's median above every other bin's?
  const compared = m.filter((r) => r.by_frames_from_start[0].g_median !== null && r.by_frames_from_start.slice(1).some((b) => b.g_median !== null));
  const nearHighest = compared.filter((r) => {
    const [near, ...rest] = r.by_frames_from_start;
    return rest.every((b) => b.g_median === null || near.g_median! > b.g_median);
  });
  const nearN = compared.map((r) => r.by_frames_from_start[0].n);
  return {
    matches: m.length,
    cells: cells.length,
    below: valued.filter((c) => c.g < file.g_real).length,
    highest_g: highest.g,
    highest_match: highest.match_id,
    highest_h: highest.h,
    lowest_g: lowest.g,
    start_lo: Math.min(...starts),
    start_hi: Math.max(...starts),
    before_matches: before.length,
    before_max: Math.max(0, ...m.map((r) => r.before_start)),
    near_compared: compared.length,
    near_highest: nearHighest.length,
    near_n_lo: Math.min(...nearN),
    near_n_hi: Math.max(...nearN),
  };
}

export type HypothesesFigures = ReturnType<typeof hypothesesFigures>;
