import { describe, expect, it } from "vitest";
import { layerDurations, poseShare, silverModelRows, type LineageData, type PlatformData } from "../lib/platform";

// `layerDurations` (task 35): on-screen seconds per layer for the flow
// animation. Five layers, one at 0 s (a step that never ran in the fixture
// selection, or a layer whose slowest step rounded to 0.0), the rest with
// real seconds -- the two properties the animation depends on: no layer
// flashes by at 0 s, and the layers always fill exactly one 8 s cycle no
// matter how the steps split.
//
// Mutation checked by hand: dropping the `minSeconds +` term (so a layer's
// share of `extra` is its whole duration) sends the 0 s layer's duration to
// 0, failing `never lets a 0 s layer disappear`; using `cycleSeconds` instead
// of `cycleSeconds - floor` as `extra` makes the durations sum to 11 s (the
// 3 s floor plus the full 8 s cycle) for five layers, failing `always fills
// exactly one cycle`.
// `silverModelRows` (task 36): joins `lineage.json`'s dbt-owned silver nodes
// with `platform.json`'s per-table rows/bytes and the `silver` step's
// per-asset dbt seconds. Fabricated, not the real bundle, so a broken join
// (e.g. matching on the raw key instead of stripping the `silver_`/`seed_`
// prefix) fails here even if the real data happens to line up.
//
// Mutation checked by hand: matching `tableByName.get(n.key)` (the raw
// lineage key) instead of the prefix-stripped `tableName` fails
// `joins rows and bytes from platform.json's tables[]`, since no table in
// the fixture is named "silver_frames" -- `rows`/`bytes` both come back
// null instead of the fixture's 900000/1500. Restored byte for byte.
describe("silverModelRows", () => {
  const lineage: LineageData = {
    schema_version: 1,
    groups: ["silver"],
    nodes: [
      {
        key: "silver_frames",
        group: "silver",
        kind: "asset",
        description: "",
        step: "silver",
        sport: null,
        schema: "dbt",
        dbt_tests: 20,
        dbt_columns: ["x_m", "y_m"],
      },
      {
        key: "silver_frames_attacking",
        group: "silver",
        kind: "asset",
        description: "",
        step: "silver",
        sport: null,
        schema: "dbt",
        dbt_tests: 2,
        dbt_columns: ["entity_id"],
      },
    ],
    edges: [],
  };
  const platform: PlatformData = {
    schema_version: 1,
    title: "fixture",
    subtitle: "fixture",
    run: {
      git_sha: "abc1234",
      started_utc: "",
      finished_utc: "",
      wall_seconds: 0,
      host: { system: "", cpus: 0, ram_gb: 0 },
      versions: {},
    },
    guarantees: {
      dbt: { total: 0, generic: 0, by_kind: {}, singular: [] },
      contracts: { files: 0, names: [] },
      checks: { count: 0, commands: [] },
    },
    layers: [],
    raw_sources: [],
    steps: [
      {
        step_key: "silver",
        assets: ["silver_frames", "silver_frames_attacking"],
        group: "silver",
        status: "success",
        duration_ms: 0,
        dbt_seconds: { silver_frames: 69.0, silver_frames_attacking: 0.1 },
      },
    ],
    tables: [{ layer: "silver", sport: null, table: "frames", files: 30, rows: 900000, bytes: 1500 }],
    matches: [],
    season_files: { files: 0, bytes: 0, items: [] },
  };

  it("joins rows and bytes from platform.json's tables[] by the prefix-stripped key", () => {
    const rows = silverModelRows(lineage, platform);
    const frames = rows.find((r) => r.key === "silver_frames");
    expect(frames?.rows).toBe(900000);
    expect(frames?.bytes).toBe(1500);
    expect(frames?.dbt_tests).toBe(20);
    expect(frames?.dbt_seconds).toBeCloseTo(69.0, 6);
  });

  it("leaves rows and bytes null for a model with no Parquet table, never inventing 0", () => {
    const rows = silverModelRows(lineage, platform);
    const view = rows.find((r) => r.key === "silver_frames_attacking");
    expect(view?.rows).toBeNull();
    expect(view?.bytes).toBeNull();
    expect(view?.dbt_seconds).toBeCloseTo(0.1, 6);
  });
});

describe("layerDurations", () => {
  it("never lets a 0 s layer disappear", () => {
    const durations = layerDurations([0, 150, 150, 0, 0]);
    expect(durations[0]).toBeCloseTo(0.6, 9);
    expect(durations[3]).toBeCloseTo(0.6, 9);
    expect(durations[4]).toBeCloseTo(0.6, 9);
  });

  it("always fills exactly one cycle, whatever the split", () => {
    const cases = [
      [0, 150, 150, 0, 0],
      [6.8, 144.5, 150.8, 119.2, 8.1],
      [0, 0, 0, 0, 0],
    ];
    for (const seconds of cases) {
      const durations = layerDurations(seconds);
      const sum = durations.reduce((total, d) => total + d, 0);
      expect(sum).toBeCloseTo(8, 9);
    }
  });
});

// `poseShare`: the body-pose zips' slice of "in", read from `raw_sources[]`. Fabricated, with
// the pose source in the middle, so picking the first or last source instead of matching on
// `source_id` fails.
describe("poseShare", () => {
  const platform = {
    raw_sources: [
      { source_id: "opendata-football", sport: "football", files: 5, bytes: 500 },
      { source_id: "opendata-bodypose", sport: "football", files: 2, bytes: 70 },
      { source_id: "opendata-basketball", sport: "basketball", files: 3, bytes: 30 },
    ],
  } as unknown as PlatformData;

  it("returns the pose source's files and bytes and the sum of every other source", () => {
    expect(poseShare(platform)).toEqual({ files: 2, bytes: 70, otherBytes: 530 });
  });

  it("is null when the pose source is not in the ingest", () => {
    const without = { raw_sources: platform.raw_sources.filter((s) => s.sport === "basketball") };
    expect(poseShare(without as unknown as PlatformData)).toBeNull();
  });
});
