// `web/public/data/history.json` (task 131), one entry per `tracklab build` record, imported at build
// time like `lib/platform.ts`: every figure on `/engineering/history` (task 132) is computed here from
// it, or from `platform.json`'s `freshness`, never typed.
import historyJson from "../public/data/history.json";
import { LINEAGE, PLATFORM, type PlatformData } from "./platform";

export type TestCounts = { pass: number; fail: number; warn: number; error: number; skipped: number };

export interface HistoryStep {
  step_key: string;
  group: string;
  status: string;
  duration_ms: number | null;
  started_utc: string | null;
  finished_utc: string | null;
  dbt: { tests: TestCounts; elapsed_seconds: number } | null;
  incremental: { mode: string; reason: string } | null;
  partitions: { written: number | null; skipped: number | null; deleted: number | null } | null;
}

export interface HistoryContracts {
  files: number | null;
  executed: boolean | null;
  status: string | null;
  passed: number | null;
  failed: number | null;
  skipped: number | null;
  errors: number | null;
  duration_seconds: number | null;
}

export interface HistoryEntry {
  id: string;
  record_version: number;
  sha: string | null;
  select: string | null;
  started_utc: string;
  finished_utc: string;
  wall_seconds: number;
  steps: HistoryStep[];
  quality: { dbt: { tests: TestCounts | null; source: string | null }; contracts: HistoryContracts };
}

export interface HistoryData {
  schema_version: number;
  entries: HistoryEntry[];
}

export const HISTORY = historyJson as unknown as HistoryData;

// A step's mode is its record's `incremental.mode` (P16: full, incremental, skip); a v1 record, and a
// step with no incremental logic, keep none.
export const NO_MODE = "none";
export const stepMode = (s: HistoryStep) => s.incremental?.mode ?? NO_MODE;

// A threshold needs a spread, and a spread two earlier runs at least (task 124 measured its own from two).
export const MIN_EARLIER = 2;

export function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export interface StepPoint {
  run: string;
  seconds: number;
  mode: string;
  // Same mode as the series' last run of this step, so part of what that run is judged against.
  comparable: boolean;
}

export interface StepSeries {
  step_key: string;
  group: string;
  points: StepPoint[];
  last: StepPoint;
  lastStep: HistoryStep;
  // The earlier runs of the same mode as the last one: their median, spread (max - min) and the
  // threshold median + spread. Null with fewer than MIN_EARLIER of them.
  earlier: number;
  median: number | null;
  spread: number | null;
  threshold: number | null;
  verdict: "above" | "within" | "too few";
}

export interface Series {
  select: string | null;
  runs: HistoryEntry[];
  steps: StepSeries[];
}

const groupRank = (g: string) => (LINEAGE.groups.includes(g) ? LINEAGE.groups.indexOf(g) : LINEAGE.groups.length);

function stepSeries(runs: HistoryEntry[], key: string): StepSeries | null {
  const ran = runs.flatMap((e) =>
    e.steps
      .filter((s) => s.step_key === key && s.status === "success" && s.duration_ms !== null)
      .map((s) => ({ run: e.id, step: s })),
  );
  if (ran.length === 0) return null;
  const lastStep = ran[ran.length - 1].step;
  const mode = stepMode(lastStep);
  const points = ran.map(({ run, step }) => ({
    run,
    seconds: step.duration_ms! / 1000,
    mode: stepMode(step),
    comparable: stepMode(step) === mode,
  }));
  const last = points[points.length - 1];
  const earlier = points.slice(0, -1).filter((p) => p.comparable).map((p) => p.seconds);
  const enough = earlier.length >= MIN_EARLIER;
  const med = enough ? median(earlier) : null;
  const spread = enough ? Math.max(...earlier) - Math.min(...earlier) : null;
  const threshold = med !== null && spread !== null ? med + spread : null;
  return {
    step_key: key,
    group: lastStep.group,
    points,
    last,
    lastStep,
    earlier: earlier.length,
    median: med,
    spread,
    threshold,
    verdict: threshold === null ? "too few" : last.seconds > threshold ? "above" : "within",
  };
}

// One series per selection (`select`, null for a complete build): a partial build never sits next to
// a complete one. Complete builds first, then by number of runs, then by first run.
export function seriesOf(entries: HistoryEntry[] = HISTORY.entries): Series[] {
  const bySelect = new Map<string | null, HistoryEntry[]>();
  for (const e of [...entries].sort((a, b) => a.id.localeCompare(b.id))) {
    bySelect.set(e.select, [...(bySelect.get(e.select) ?? []), e]);
  }
  return [...bySelect.entries()]
    .map(([select, runs]) => {
      const keys = [...new Set(runs.flatMap((e) => e.steps.map((s) => s.step_key)))];
      const steps = keys
        .map((k) => stepSeries(runs, k))
        .filter((s): s is StepSeries => s !== null)
        .sort((a, b) => groupRank(a.group) - groupRank(b.group) || b.last.seconds - a.last.seconds);
      return { select, runs, steps };
    })
    .sort(
      (a, b) =>
        Number(b.select === null) - Number(a.select === null) ||
        b.runs.length - a.runs.length ||
        a.runs[0].id.localeCompare(b.runs[0].id),
    );
}

export interface ModeSummary {
  step_key: string;
  mode: string;
  runs: number;
  median: number;
  min: number;
  max: number;
  tests: number | null; // the dbt tests the step ran, the same in every run of the mode, else null
}

// A step's seconds by mode within one series: what P16 changed, without mixing modes.
export function modeSummary(series: Series, keys: string[]): ModeSummary[] {
  return series.steps
    .filter((s) => keys.includes(s.step_key))
    .flatMap((s) => {
      const steps = series.runs.flatMap((e) =>
        e.steps.filter((x) => x.step_key === s.step_key && x.status === "success" && x.duration_ms !== null),
      );
      const modes = [...new Set(steps.map(stepMode))];
      return modes.map((mode) => {
        const of = steps.filter((x) => stepMode(x) === mode);
        const seconds = of.map((x) => x.duration_ms! / 1000);
        const tests = [...new Set(of.map((x) => (x.dbt ? x.dbt.tests.pass + x.dbt.tests.fail + x.dbt.tests.warn + x.dbt.tests.error + x.dbt.tests.skipped : null)))];
        return {
          step_key: s.step_key,
          mode,
          runs: of.length,
          median: median(seconds),
          min: Math.min(...seconds),
          max: Math.max(...seconds),
          tests: tests.length === 1 ? tests[0] : null,
        };
      });
    });
}

export const testTotal = (t: TestCounts | null) => (t ? t.pass + t.fail + t.warn + t.error + t.skipped : null);

// "20261102T190029Z_5caf04b" -> "2026-11-02 19:00 · 5caf04b"
export function runLabel(id: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})\d{2}Z_(\w+)$/.exec(id);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]} · ${m[6]}` : id;
}

// --- freshness: `platform.json`'s own, measured by `tracklab publish platform` (decision 4) -------

export interface FreshnessRow {
  key: string;
  label: string;
  // Age at publish, in seconds, of each directory of the row (or of the run).
  ages: { id: string; seconds: number; written_utc: string }[];
}

const ms = (iso: string) => new Date(iso).getTime();

export function freshnessRows(platform: PlatformData = PLATFORM): { published_utc: string; rows: FreshnessRow[] } {
  const { published_utc, partitions } = platform.freshness;
  const at = ms(published_utc);
  const age = (p: (typeof partitions)[number]) => ({
    id: `${p.layer}/${p.table}${p.partition ? `/${p.partition}` : ""}`,
    seconds: (at - ms(p.written_utc)) / 1000,
    written_utc: p.written_utc,
  });
  const pick = (f: (p: (typeof partitions)[number]) => boolean) => partitions.filter(f).map(age);
  const rows: FreshnessRow[] = [
    { key: "silver-frames", label: "silver frames", ages: pick((p) => p.layer === "silver" && p.table === "frames") },
    { key: "silver-events", label: "silver events", ages: pick((p) => p.layer === "silver" && p.table === "events") },
    {
      key: "silver-whole",
      label: "silver, whole tables",
      ages: pick((p) => p.layer === "silver" && p.table !== "frames" && p.table !== "events"),
    },
    { key: "gold", label: "gold tables", ages: pick((p) => p.layer === "gold") },
    {
      key: "run",
      label: "platform.json's run",
      ages: [{ id: "run", seconds: (at - ms(platform.run.finished_utc)) / 1000, written_utc: platform.run.finished_utc }],
    },
  ];
  return { published_utc, rows: rows.filter((r) => r.ages.length > 0) };
}

// An age in the unit that keeps it readable: minutes under two hours, hours under two days, else days.
export function ageUnit(maxSeconds: number): { unit: string; per: number } {
  if (maxSeconds < 2 * 3600) return { unit: "min", per: 60 };
  if (maxSeconds < 2 * 86400) return { unit: "h", per: 3600 };
  return { unit: "d", per: 86400 };
}
