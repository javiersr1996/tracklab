// Every figure the text of lesson 8 computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`. The inputs
// are entry.json's flight and constants, quality.json's entry-angle rows and lesson 1's hook.
import { flight, perfectRun, type EntryConstants, type Options, type Sample } from "./entry";
import type { EntryFile, EntryMatch } from "./entry-data";
import { shown } from "./expose";

// The rim's height by FIBA's rules, 3,050 mm (sources.ts: `fiba-ring`), against the check's 10 ft.
export const FIBA_RIM_M = 3.05;
// The figure's sliders.
export const G_MIN = 7;
export const G_MAX = 11;
export const S_MIN = 0.8;
export const S_MAX = 1.4;

// Lesson 1: for the hook to fall at G, the file's heights would be short by g/G; the scale that
// undoes it, at the three decimals that lesson prints.
export const scaleOfLessonOne = (G: number, g: number): number => shown(G / g, 3);

const range = (xs: readonly number[]) => [Math.min(...xs), Math.max(...xs)] as const;

// The sample of the run nearest the rim's centre in the plane.
export function closestToRim(run: readonly Sample[], rimX: number): number {
  const d = run.map((p) => Math.hypot(rimX - p.x, -p.y));
  return d.indexOf(Math.min(...d));
}

export function entryFigures(file: EntryFile, run: readonly Sample[], matches: readonly EntryMatch[], hookG: number) {
  const c: EntryConstants = file;
  const rimX = file.example.rim_x;
  const f = flight(run, c, rimX);
  const perfect = flight(perfectRun(run, f, c), c, rimX);
  const at = (o: Options) => flight(run, c, rimX, o);
  const step = 0.01;
  const dReqDg = (at({ g: c.g + step }).required - at({ g: c.g - step }).required) / (2 * step);
  const dRepDs = (at({ zScale: 1 + step }).reported - at({ zScale: 1 - step }).reported) / 2;
  const dReqDs = (at({ zScale: 1 + step }).required - at({ zScale: 1 - step }).required) / 2;
  const heightScale = scaleOfLessonOne(c.g, hookG);
  const scaled = at({ zScale: heightScale });
  const lowG = at({ g: hookG });
  const closest = closestToRim(run, rimX);

  const m = matches;
  const [repLo, repHi] = range(m.map((r) => r.reported));
  const [reqLo, reqHi] = range(m.map((r) => r.required));
  const [gapLo, gapHi] = range(m.map((r) => r.gap));
  const [reoLo, reoHi] = range(m.map((r) => r.reordered));
  const [shotsLo, shotsHi] = range(m.map((r) => r.shots));

  return {
    // The example, at the check's values.
    ex_samples: run.length + file.search_offset,
    ex_v_h: shown(f.vH, 2),
    ex_d: shown(f.d, 2),
    ex_t: shown(f.T, 2),
    ex_k: f.k,
    ex_reported: shown(f.reported, 4),
    ex_required: shown(f.required, 4),
    ex_gap: shown(f.gap, 2),
    ex_dist_at_k: shown(Math.hypot(rimX - run[f.k].x, -run[f.k].y), 2),
    ex_z_at_k: shown(run[f.k].z, 2),
    ex_closest_after: closest - f.k,
    ex_closest_d: shown(Math.hypot(rimX - run[closest].x, -run[closest].y), 2),
    // The method on a perfect flight.
    perfect_reported: shown(perfect.reported, 2),
    method_gap: shown(perfect.gap, 2),
    left_gap: shown(f.gap - perfect.gap, 2),
    tail_middle: c.tail_back / 2,
    // Sensitivities.
    dreq_dg: shown(dReqDg, 2),
    drep_ds: shown(dRepDs, 2),
    dreq_ds: shown(dReqDs, 2),
    rim_effect: shown(Math.abs(at({ rim: FIBA_RIM_M }).required - f.required), 3),
    fiba_mm: shown(1000 * FIBA_RIM_M, 0),
    check_rim_mm: shown(1000 * c.rim_height, 0),
    // Lesson 1's two scales, one at a time.
    hook_g: hookG,
    height_scale: heightScale,
    scaled_reported: shown(scaled.reported, 2),
    scaled_required: shown(scaled.required, 2),
    scaled_gap: shown(scaled.gap, 2),
    low_g_required: shown(lowG.required, 2),
    low_g_gap: shown(lowG.gap, 2),
    // Every match.
    matches: m.length,
    rep_lo: repLo,
    rep_hi: repHi,
    req_lo: reqLo,
    req_hi: reqHi,
    gap_lo: gapLo,
    gap_hi: gapHi,
    reo_lo: reoLo,
    reo_hi: reoHi,
    shots_lo: shotsLo,
    shots_hi: shotsHi,
    shots: m.reduce((s, r) => s + r.shots, 0),
  };
}

export type EntryFigures = ReturnType<typeof entryFigures>;
