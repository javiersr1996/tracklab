import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { formatMetric, HOOK, scaleOf, seriesOf, stacked, TABLE_METRICS } from "../lib/quality";

// Task 183: the charts of /engineering/quality read the same rows as its table. Broken on purpose
// while writing these: a series that dropped football's rows, a median of the sorted values' first
// half, and a scale that left the reference out each failed here.
const FILE = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "quality.json"), "utf-8")) as {
  checks: Record<string, { sport: string; match_id: string; metric: string; value: number }[]>;
};

function middle(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
}

describe("the quality charts", () => {
  it("plot every row of quality.json once, per sport, with the median of those rows", () => {
    for (const m of TABLE_METRICS) {
      const series = seriesOf(m);
      for (const sport of ["basketball", "football"]) {
        const rows = FILE.checks[m.check].filter((r) => r.metric === m.metric && r.sport === sport);
        const s = series[sport];
        if (rows.length === 0) {
          expect(s, `${m.metric} ${sport}`).toBeNull();
          continue;
        }
        expect(s!.points.map((p) => p.match_id).sort(), `${m.metric} ${sport}`).toEqual(rows.map((r) => r.match_id).sort());
        expect(s!.median, `${m.metric} ${sport}`).toBe(middle(rows.map((r) => r.value)));
      }
    }
  });

  it("leaves football out of the entry angle, which has no football row", () => {
    expect(seriesOf(TABLE_METRICS.find((m) => m.check === "entry_angle")!).football).toBeNull();
  });

  it("puts shares on 0 to 100, and every other axis round the values and the reference", () => {
    for (const m of TABLE_METRICS) {
      const values = Object.values(seriesOf(m)).flatMap((s) => s?.points.map((p) => p.value) ?? []);
      const { domain, ticks } = scaleOf(m, values);
      if (m.share) expect(domain, m.metric).toEqual([0, 100]);
      for (const v of [...values, ...(m.reference ? [m.reference.value] : [])]) {
        expect(v, m.metric).toBeGreaterThanOrEqual(domain[0]);
        expect(v, m.metric).toBeLessThanOrEqual(domain[1]);
      }
      expect(ticks[0]).toBeCloseTo(domain[0], 9);
      expect(ticks[ticks.length - 1]).toBeCloseTo(domain[1], 9);
    }
    expect(TABLE_METRICS.find((m) => m.metric === "g_median")!.reference!.value).toBe(HOOK.g_real);
  });

  it("stacks the basketball ball's ten zeros in one column", () => {
    const m = TABLE_METRICS.find((x) => x.metric === "ball_detected_pct")!;
    const dots = stacked(seriesOf(m).basketball!.points, [0, 100]);
    expect(dots.every((d) => d.x === 0)).toBe(true);
    expect(dots.map((d) => d.level)).toEqual(dots.map((_, i) => i));
    expect(formatMetric(m, 0)).toBe("0.0");
  });
});
