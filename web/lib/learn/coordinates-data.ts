// Lesson 3's slice of what is already published, read at build time: the possessions of
// `public/data/possessions` that `fence.json` allows, the row counts of `stats.json` and the clock
// check of `quality.json`. Nothing new is published; a figure the page prints is either a value of
// one of these files (`publishedFigure` names it by path) or computed here from them.
import index from "../../public/data/index.json";
import stats from "../../public/data/stats.json";
import bb114086 from "../../public/data/possessions/bb_possessions_possession-114086-1-36.json";
import bb114099 from "../../public/data/possessions/bb_possessions_possession-114099-1-41.json";
import bb114169 from "../../public/data/possessions/bb_possessions_possession-114169-4-140.json";
import bb114243 from "../../public/data/possessions/bb_possessions_possession-114243-3-79.json";
import bb184439 from "../../public/data/possessions/bb_possessions_possession-184439-2-38.json";
import bb191313 from "../../public/data/possessions/bb_possessions_possession-191313-2-69.json";
import fb1874553 from "../../public/data/possessions/fb_possession_1874553_1.json";
import fb1886347 from "../../public/data/possessions/fb_possession_1886347_40.json";
import fb1925299 from "../../public/data/possessions/fb_possession_1925299_71.json";
import { QUALITY, type QualityRow } from "../quality";
import type { Frame, Possession, Sport } from "../replay/types";
import { FOOT_M, cornerTurn, sharedClock } from "./coordinates";
import { shown } from "./expose";
import fence from "./fence.json";

// The possessions' positions are written at two decimals (`publish/possessions.py:61`), so a
// metre in the file is within half a centimetre of the one it was rounded from.
export const POSITION_HALF_UNIT_M = 0.005;

// What each provider delivers: basketball in feet and football in metres, both with the origin at
// the centre and x along the long side (sources.ts: `skillcorner-bb-coords`, `skillcorner-fb-coords`).
export const PROVIDER: Record<Sport, { unit: "ft" | "m"; unit_to_m: number }> = {
  basketball: { unit: "ft", unit_to_m: FOOT_M },
  football: { unit: "m", unit_to_m: 1 },
};

const HELD_OUT = new Set(fence.held_out);
export const isHeldOut = (match_id: string) => HELD_OUT.has(match_id.replace(/^[a-z]+:/, ""));

// The published possessions this lesson reads: the nine it was written on, one per match and none
// of a held-out football match (tests/learn-coordinates.test.ts checks both). The replay has more.
export const PUBLISHED: Readonly<Record<string, Possession>> = Object.fromEntries(
  [bb114086, bb114099, bb114169, bb114243, bb184439, bb191313, fb1874553, fb1886347, fb1925299].map((p) => {
    const possession = p as unknown as Possession;
    const entry = index.possessions.find((e) => e.possession_id === possession.possession_id);
    if (!entry) throw new Error(`${possession.possession_id} is not in index.json`);
    return [stemOf(entry.file), possession];
  }),
);

export function stemOf(file: string): string {
  return file.replace(/^possessions\//, "").replace(/\.json$/, "");
}

// The home page's two possessions, chosen by its own rule: the first published of each sport.
export const HOME_STEMS: Record<Sport, string> = {
  basketball: stemOf(index.possessions.find((p) => p.sport === "basketball")!.file),
  football: stemOf(index.possessions.find((p) => p.sport === "football")!.file),
};

export function possession(stem: string): Possession {
  const p = PUBLISHED[stem];
  if (!p) throw new Error(`no allowed possession ${stem}`);
  return p;
}

const CLOCK = QUALITY.checks.clock.filter((r) => r.metric === "clock_step_exact_pct");

// The `data-fig` path of a published figure, and its value. `stats.<table>.<match or sport>.rows`
// is a row count of `stats.json`; `quality.<check>.<match>.<metric>` the value of a row of
// `quality.json` and `...<metric>.n` its n; `possession.<stem>.<path>` a value of that file.
export function publishedFigure(path: string): unknown {
  const [file, ...parts] = path.split(".");
  if (file === "stats") {
    const [table, key, field] = parts;
    const row = stats.tables.find((r) => r.table === table && (r.match_id === key || (r.match_id === "" && r.sport === key)));
    return field === "rows" ? row?.rows : undefined;
  }
  if (file === "quality" && parts[0] === "summary") {
    return parts.reduce<unknown>((at, k) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[k] : undefined), QUALITY);
  }
  if (file === "quality") {
    const [check, match_id, metric, n] = parts;
    const row: QualityRow | undefined = QUALITY.checks[check]?.find((r) => r.match_id === match_id && r.metric === metric);
    return n === "n" ? row?.n : row?.value;
  }
  if (file === "possession") {
    const [stem, ...rest] = parts;
    return rest.reduce<unknown>((at, k) => (at !== null && typeof at === "object" ? (at as Record<string, unknown>)[k] : undefined), PUBLISHED[stem]);
  }
  return undefined;
}

export const statsFig = (table: string, key: string) => `stats.${table}.${key}.rows`;
export const clockFig = (match_id: string, n = false) => `quality.clock.${match_id}.clock_step_exact_pct${n ? ".n" : ""}`;
export const possessionFig = (stem: string, path: string) => `possession.${stem}.${path}`;

export interface MatchCoordinates {
  match_id: string;
  sport: Sport;
  steps: number;
  exact_pct: number;
  rows: number;
  minutes: number;
  stem: string | null; // the published possession of the match, if there is one
}

const rateOf = (sport: Sport) => possession(HOME_STEMS[sport]).sample_rate_hz;

// One row per match of `stats.json`'s `frames`, held-out football matches left out.
export function matchRows(): MatchCoordinates[] {
  return stats.tables
    .filter((r) => r.table === "frames" && !isHeldOut(r.match_id))
    .map((r) => {
      const sport = r.sport as Sport;
      const clock = CLOCK.find((c) => c.match_id === r.match_id);
      if (!clock) throw new Error(`quality.json has no clock step for ${r.match_id}`);
      const stem = Object.keys(PUBLISHED).find((s) => PUBLISHED[s].match.match_id === r.match_id) ?? null;
      return {
        match_id: r.match_id,
        sport,
        steps: clock.n,
        exact_pct: clock.value,
        rows: r.rows,
        minutes: shown(clock.n / rateOf(sport) / 60, 1),
        stem,
      };
    })
    .sort((a, b) => (a.sport === b.sport ? a.match_id.localeCompare(b.match_id) : a.sport.localeCompare(b.sport)));
}

export const MATCHES = matchRows();

// The first frame of a possession, as the figure draws it: metres in the venue frame, each entity
// with its side, and the first player of the team in possession picked out.
export interface FrameView {
  sport: Sport;
  match_id: string;
  stem: string;
  spec: string;
  length_m: number;
  width_m: number;
  sign: 1 | -1;
  unit: "ft" | "m";
  unit_to_m: number;
  t_ms: number;
  entities: { i: number; role: "attack" | "defence" | "ball"; x: number; y: number }[];
  highlight: number;
  jersey: string;
}

export function frameView(stem: string): FrameView {
  const p = possession(stem);
  const byIndex = new Map(p.entities.map((e) => [e.i, e]));
  const role = (i: number) => {
    const e = byIndex.get(i);
    return e?.kind === "ball" ? "ball" : e?.team_id === p.team_in_possession ? "attack" : "defence";
  };
  const first = p.frames[0];
  const entities = first.o.map(([i, x, y]) => ({ i, role: role(i), x, y }) as const);
  const highlight = entities.find((e) => e.role === "attack");
  if (!highlight) throw new Error(`${stem}: no player of the team in possession in the first frame`);
  return {
    sport: p.sport,
    match_id: p.match.match_id,
    stem,
    spec: p.surface.spec,
    length_m: p.surface.length_m,
    width_m: p.surface.width_m,
    sign: p.attack_sign,
    ...PROVIDER[p.sport],
    t_ms: first.t,
    entities,
    highlight: highlight.i,
    jersey: byIndex.get(highlight.i)?.jersey ?? "",
  };
}

// The ball over the first `windowMs` of a possession, as frames the replay engine reads.
export interface ClockTrack {
  sport: Sport;
  match_id: string;
  rate: number;
  t0: number;
  ball: number;
  frames: Frame[];
}

export const CLOCK_WINDOW_MS = 1000;

export function clockTrack(stem: string, windowMs = CLOCK_WINDOW_MS): ClockTrack {
  const p = possession(stem);
  const ball = p.entities.find((e) => e.kind === "ball")?.i;
  if (ball === undefined) throw new Error(`${stem}: no ball`);
  const t0 = p.frames[0].t;
  const frames = p.frames.filter((f) => f.t - t0 <= windowMs).map((f) => ({ ...f, o: f.o.filter((o) => o[0] === ball) }));
  return { sport: p.sport, match_id: p.match.match_id, rate: p.sample_rate_hz, t0, ball, frames };
}

// The distinct surfaces of a sport's published possessions, as [length, width], shortest first.
function surfaces(sport: Sport): number[][] {
  const seen = new Map<string, number[]>();
  for (const p of Object.values(PUBLISHED)) {
    if (p.sport === sport) seen.set(p.surface.spec, [p.surface.length_m, p.surface.width_m]);
  }
  return [...seen.values()].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}

const median = (xs: readonly number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// Every figure the text computes, rounded as it is printed: the page shows each as
// `data-fig="learn.<key>"` and the browser puts the same object in `window.__learn`.
export function coordinatesFigures(matches: readonly MatchCoordinates[] = MATCHES) {
  const bb = possession(HOME_STEMS.basketball);
  const fb = possession(HOME_STEMS.football);
  const clock = sharedClock(bb.sample_rate_hz, fb.sample_rate_hz);
  const of = (sport: Sport) => matches.filter((m) => m.sport === sport);
  const ratio = (sport: Sport) => {
    const periods = publishedFigure(statsFig("dim_period", sport)) as number;
    return (publishedFigure(statsFig("dim_team_period", sport)) as number) / periods;
  };
  const fbView = frameView(HOME_STEMS.football);
  const player = fbView.entities.find((e) => e.i === fbView.highlight)!;
  const corner = cornerTurn([player.x, player.y], fb.surface.length_m, fb.surface.width_m);
  const r2 = (p: readonly [number, number]) => p.map((v) => shown(v, 2));

  return {
    foot_m: FOOT_M,
    court_ft_length: shown(bb.surface.length_m / FOOT_M, 2),
    court_ft_width: shown(bb.surface.width_m / FOOT_M, 2),
    feet_bound: shown(POSITION_HALF_UNIT_M / FOOT_M, 3),
    frame_bb: bb.frames[0].t / clock.stepA,
    frame_fb: fb.frames[0].t / clock.stepB,
    step_bb_ms: clock.stepA,
    step_fb_ms: clock.stepB,
    shared_ms: clock.shared,
    every_bb: clock.everyA,
    every_fb: clock.everyB,
    missing_fb_on_bb: clock.missingOnA,
    missing_bb_on_fb: clock.missingOnB,
    rate_ratio: bb.sample_rate_hz / fb.sample_rate_hz,
    max_rows_s_bb: bb.sample_rate_hz * bb.entities.length,
    max_rows_s_fb: fb.sample_rate_hz * fb.entities.length,
    matches_bb: of("basketball").length,
    matches_fb: of("football").length,
    // Ten matches each: the median falls between two counts, printed to the nearest row.
    median_rows_bb: Math.round(median(of("basketball").map((m) => m.rows))),
    median_rows_fb: Math.round(median(of("football").map((m) => m.rows))),
    median_minutes_bb: shown(median(of("basketball").map((m) => m.minutes)), 1),
    median_minutes_fb: shown(median(of("football").map((m) => m.minutes)), 1),
    team_period_ratio_bb: ratio("basketball"),
    team_period_ratio_fb: ratio("football"),
    ft_per_m: shown(1 / FOOT_M, 2),
    surfaces_bb: surfaces("basketball"),
    surfaces_fb: surfaces("football"),
    signs_plus: Object.values(PUBLISHED).filter((p) => p.attack_sign === 1).length,
    signs_minus: Object.values(PUBLISHED).filter((p) => p.attack_sign === -1).length,
    corner: { point: r2(corner.corner), negated: r2(corner.negated), turned: r2(corner.turned) },
    minutes: Object.fromEntries(matches.map((m) => [m.match_id, m.minutes])),
  };
}

export type CoordinatesFigures = ReturnType<typeof coordinatesFigures>;
