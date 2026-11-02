import { describe, expect, it } from "vitest";
import { ageUnit, freshnessRows, median, seriesOf, type HistoryEntry } from "../lib/history";
import type { PlatformData } from "../lib/platform";

// Task 132: the series, medians and thresholds of /engineering/history, on fabricated entries so a
// rule that mixes selections or modes fails here even if the real history happens to agree.
// Mutations checked by hand, each restored: comparing against every earlier run whatever its mode
// fails "judges the last run only against earlier runs of its mode"; one series for all selections
// fails "never mixes"; `MIN_EARLIER` at 1 fails "too few".

const entry = (id: string, select: string | null, steps: [string, number, string | null][]): HistoryEntry => ({
  id,
  record_version: 2,
  sha: "abc",
  select,
  started_utc: "2026-11-02T10:00:00+00:00",
  finished_utc: "2026-11-02T10:10:00+00:00",
  wall_seconds: 600,
  steps: steps.map(([step_key, seconds, mode]) => ({
    step_key,
    group: "silver",
    status: "success",
    duration_ms: seconds * 1000,
    started_utc: null,
    finished_utc: null,
    dbt: null,
    incremental: mode ? { mode, reason: `${mode} reason` } : null,
    partitions: null,
  })),
  quality: {
    dbt: { tests: null, source: null },
    contracts: { files: 15, executed: null, status: null, passed: null, failed: null, skipped: null, errors: null, duration_seconds: null },
  },
});

describe("seriesOf", () => {
  const entries = [
    entry("20261102T100000Z_a", "group:silver", [["silver", 10, "full"]]),
    entry("20261102T110000Z_a", null, [["silver", 100, null]]),
    entry("20261102T120000Z_a", "group:silver", [["silver", 12, "full"]]),
    entry("20261102T130000Z_a", "group:silver", [["silver", 1, "skip"]]),
    entry("20261102T140000Z_a", "group:silver", [["silver", 14, "full"]]),
    entry("20261102T150000Z_a", "group:silver", [["silver", 30, "full"]]),
  ];

  it("never mixes selections: one series each, the complete builds first", () => {
    const series = seriesOf(entries);
    expect(series.map((s) => [s.select, s.runs.length])).toEqual([
      [null, 1],
      ["group:silver", 5],
    ]);
  });

  it("judges the last run only against earlier runs of its mode", () => {
    const silver = seriesOf(entries)[1].steps[0];
    expect(silver.points.map((p) => p.comparable)).toEqual([true, true, false, true, true]);
    expect(silver.earlier).toBe(3);
    expect(silver.median).toBe(12);
    expect(silver.spread).toBe(4);
    expect(silver.threshold).toBe(16);
    expect(silver.verdict).toBe("above");
  });

  it("has no threshold with fewer than two earlier runs of the mode", () => {
    const silver = seriesOf(entries.slice(0, 3))[1].steps[0];
    expect(silver.earlier).toBe(1);
    expect([silver.median, silver.threshold, silver.verdict]).toEqual([null, null, "too few"]);
  });

  it("median of an even count is the mean of the two middle values", () => {
    expect(median([4, 1, 3, 2])).toBe(2.5);
    expect(median([5, 1, 3])).toBe(3);
  });
});

describe("freshnessRows", () => {
  const platform = {
    run: { finished_utc: "2026-11-02T19:00:00+00:00" },
    freshness: {
      published_utc: "2026-11-02T20:00:00+00:00",
      partitions: [
        { layer: "silver", table: "frames", partition: "sport=basketball/native_match_id=1", files: 1, written_utc: "2026-11-02T18:30:00.000+00:00" },
        { layer: "silver", table: "dim_match", partition: null, files: 1, written_utc: "2026-11-02T18:00:00.000+00:00" },
        { layer: "gold", table: "dim_player", partition: null, files: 1, written_utc: "2026-11-02T19:30:00.000+00:00" },
      ],
    },
  } as unknown as PlatformData;

  it("ages each directory and the run at the instant of publishing, rows without one dropped", () => {
    const { rows } = freshnessRows(platform);
    expect(rows.map((r) => [r.key, r.ages.map((a) => a.seconds)])).toEqual([
      ["silver-frames", [5400]],
      ["silver-whole", [7200]],
      ["gold", [1800]],
      ["run", [3600]],
    ]);
  });

  it("picks the unit by the oldest age", () => {
    expect(ageUnit(3600).unit).toBe("min");
    expect(ageUnit(10 * 3600).unit).toBe("h");
    expect(ageUnit(5 * 86400).unit).toBe("d");
  });
});
