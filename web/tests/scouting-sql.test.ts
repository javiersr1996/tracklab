import { describe, expect, it } from "vitest";
import { compareSql, tableSql, type ScoutingCatalog } from "../lib/scouting/sql";

// The SQL of /warehouse/scouting (`lib/scouting/sql.ts`) over a toy catalog: its shape, the
// identifiers it refuses and the integers it insists on. What the SQL answers is checked against
// the real Parquet files by the two-path script of task 135 (Python computes `scouting.json`,
// DuckDB runs this SQL) and by e2e/scouting.spec.ts.

const toy: ScoutingCatalog = {
  age_reference: "2025-06-30",
  tables: [
    {
      table: "fb_a",
      sport: "football",
      key: ["player_id", "team_id", "position_group"],
      sample: "count_match",
      floor: "count_match >= 5",
      partition: "position_group",
      metrics: [
        { id: "dist", expr: "dist", label: "Distance", scale: "per_match", unit: "m" },
        { id: "sprints", expr: "sprints", label: "Sprints", scale: "per_match", unit: "" },
      ],
      pools: [{ group: "Midfield" }, { group: "Full Back" }],
    },
    {
      table: "fb_b",
      sport: "football",
      key: ["player_id", "team_id", "position_group"],
      sample: "performance_count",
      floor: "performance_count >= 5",
      partition: "position_group",
      metrics: [{ id: "passes", expr: "passes", label: "Passes", scale: "per_30_tip", unit: "" }],
      pools: [{ group: "Midfield" }, { group: "Goalkeeper" }],
    },
    {
      table: "bb_a",
      sport: "basketball",
      key: ["player_id", "team_id"],
      sample: "games_played",
      floor: "NOT is_season_total AND games_played >= 10",
      partition: null,
      metrics: [
        { id: "total_points_per_game", expr: "total_points / games_played", label: "Points", scale: "per_match", unit: "" },
      ],
      pools: [{ group: null }],
    },
  ],
};

const pair = [
  { player_id: 1, team_id: 2, position_group: "Midfield" },
  { player_id: 3, team_id: 4, position_group: "Full Back" },
] as const;

const clone = (): ScoutingCatalog => JSON.parse(JSON.stringify(toy));

describe("tableSql", () => {
  it("ranks each metric inside its group, ascending, apart from its NULLs, after the floor", () => {
    const sql = tableSql(toy, "fb_a");
    expect(sql).toContain("FROM fb_a WHERE count_match >= 5");
    expect(sql).toContain(
      "floor(percent_rank() OVER (PARTITION BY position_group, ((dist) IS NULL) ORDER BY (dist)) * 1000 + 0.5 + 1e-6) / 10",
    );
    expect(sql).toContain("CASE WHEN (dist) IS NULL THEN NULL ELSE");
    expect(sql).toContain("AS dist_pctl");
    expect(sql).toContain("count_match AS sample");
    expect(sql).not.toMatch(/DESC/i);
    expect(sql).toContain("ORDER BY player_name, player_id, team_id, position_group");
  });

  it("reads the published player_age, never a birthdate, in football only", () => {
    const sql = tableSql(toy, "fb_a");
    expect(sql).toContain("player_age AS age");
    expect(sql).not.toContain("birth");
    expect(tableSql(toy, "bb_a")).not.toContain("player_age");
  });

  it("ranks the league as a whole in basketball and keeps the floor's season-total clause", () => {
    const sql = tableSql(toy, "bb_a");
    expect(sql).toContain("PARTITION BY ((total_points / games_played) IS NULL) ORDER BY");
    expect(sql).toContain("WHERE NOT is_season_total AND games_played >= 10");
    expect(sql).toContain("(total_points / games_played) AS total_points_per_game");
  });

  it("takes a subset of the catalog's metrics", () => {
    const sql = tableSql(toy, "fb_a", ["sprints"]);
    expect(sql).toContain("sprints_pctl");
    expect(sql).not.toContain("dist_pctl");
  });

  it("throws for a table or a metric outside the catalog", () => {
    expect(() => tableSql(toy, "fact")).toThrow(/not a table/);
    expect(() => tableSql(toy, "fb_a", ["dist; DROP TABLE x"])).toThrow(/not a metric/);
    expect(() => tableSql(toy, "fb_a", ["height"])).toThrow(/not a metric/);
  });

  it("throws for a catalog entry that is not a plain identifier or a known shape", () => {
    const names = (edit: (c: ScoutingCatalog) => void) => {
      const c = clone();
      edit(c);
      return () => tableSql(c, "fb_a");
    };
    expect(names((c) => (c.tables[0].metrics[0].expr = "dist) FROM x --"))).toThrow(/expression/);
    expect(names((c) => (c.tables[0].metrics[0].id = "Dist"))).toThrow(/plain name/);
    expect(names((c) => (c.tables[0].partition = "position_group; x"))).toThrow(/plain name/);
    expect(names((c) => (c.tables[0].key[0] = "player_id, 1"))).toThrow(/plain name/);
    expect(names((c) => (c.tables[0].floor = "count_match >= 5 OR 1 = 1"))).toThrow(/floor/);
    expect(names((c) => (c.tables[0].floor = "other >= 5"))).toThrow(/floor/);
  });
});

describe("compareSql", () => {
  it("ranks inside each table's pool in its own CTE and only then joins on the whole key", () => {
    const sql = compareSql(toy, "football", pair);
    const ctes = sql.slice(sql.indexOf("c0 AS"), sql.indexOf(" SELECT k.slot"));
    expect(ctes).toContain("c0 AS (SELECT * FROM (SELECT player_id, team_id, position_group, (dist) AS fb_a__dist");
    expect(ctes).toContain("FROM fb_a WHERE count_match >= 5)");
    expect(ctes).toContain("FROM fb_b WHERE performance_count >= 5)");
    expect(sql).not.toContain("fb_a JOIN");
    expect(sql).toContain(
      "LEFT JOIN c0 ON c0.player_id = k.player_id AND c0.team_id = k.team_id AND c0.position_group = k.position_group",
    );
    expect(sql).toContain("k(slot, player_id, team_id, position_group) AS (VALUES (0, 1, 2, 'Midfield'), (1, 3, 4, 'Full Back'))");
    expect(sql).toContain("(c0.player_id IS NULL) AS fb_a_below_floor");
    expect(sql).toContain("c1.fb_b__passes_pctl");
    // The pool size per metric, counted by the engine over the same window as the percentile.
    expect(sql).toContain("count(dist) OVER (PARTITION BY position_group) AS fb_a__dist_n");
    expect(sql).toContain("c1.fb_b__passes_n");
    expect(tableSql(toy, "fb_a")).not.toMatch(/_n\b/);
    expect(sql).toContain("ORDER BY k.slot");
  });

  it("joins basketball by player and team only and has no age", () => {
    const sql = compareSql(toy, "basketball", [
      { player_id: 5, team_id: 6 },
      { player_id: 7, team_id: 6 },
    ]);
    expect(sql).toContain("k(slot, player_id, team_id) AS (VALUES (0, 5, 6), (1, 7, 6))");
    expect(sql).toContain("LEFT JOIN c0 ON c0.player_id = k.player_id AND c0.team_id = k.team_id ");
    expect(sql).not.toContain("age");
  });

  it("validates ids as integers and the group against the catalog", () => {
    const bad = (p: object) => () => compareSql(toy, "football", [{ ...pair[0], ...p }, pair[1]]);
    expect(bad({ player_id: "1; DROP TABLE x" })).toThrow(/integer/);
    expect(bad({ player_id: 1.5 })).toThrow(/integer/);
    expect(bad({ player_id: -1 })).toThrow(/integer/);
    expect(bad({ team_id: Number.NaN })).toThrow(/integer/);
    expect(bad({ team_id: 1e300 })).toThrow(/integer/);
    expect(bad({ position_group: "Midfield' OR 1=1 --" })).toThrow(/group/);
    expect(bad({ position_group: "Striker" })).toThrow(/group/);
    expect(bad({ position_group: undefined })).toThrow(/group/);
    expect(() => compareSql(toy, "football", [{ ...pair[0], position_group: "Goalkeeper" }, pair[1]])).not.toThrow();
  });

  it("throws for a sport the catalog does not have", () => {
    expect(() => compareSql(toy, "tennis", pair)).toThrow(/not a sport/);
  });
});
