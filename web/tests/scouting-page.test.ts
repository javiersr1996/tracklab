import { describe, expect, it } from "vitest";
import type { QueryResult } from "../lib/duckdb/engine";
import {
  comparedOf,
  defaultPair,
  filterRows,
  formatPctl,
  placeStep,
  keyText,
  paramsQuery,
  pctlStep,
  probeMetrics,
  poolsOf,
  readParams,
  rowsOf,
  SCOUTING,
  SMALL_POOL,
  smallPoolNote,
  sortRows,
  tableOf,
} from "../lib/scouting/catalog";
import type { ScoutingProbe } from "../lib/scouting/catalog";
import type { RawValue } from "../lib/warehouse/cell";

// The helpers of /warehouse/scouting (task 136) on the real `scouting.json`: what the URL may say,
// the cell's step, and the rows, pools, filters and order of a result. What the engine answers is
// e2e/scouting.spec.ts's (task 137).

const q = (s: string) => readParams(new URLSearchParams(s));

function result(columns: string[], values: RawValue[][]): QueryResult {
  return {
    sql: "",
    columns,
    rows: values.map((r) => r.map(String)),
    values,
    rowCount: values.length,
    ms: 0,
    bytes: 0,
    distinctBytes: 0,
    requests: 0,
    files: [],
  };
}

describe("the URL's state", () => {
  it("defaults to football's first table, all groups and the JSON's default pair", () => {
    const p = q("");
    const [a, b] = defaultPair("football");
    expect(p).toEqual({ sport: "football", table: SCOUTING.tables[0].table, group: null, a, b });
    expect(keyText(a)).toBe("159688-868-Midfield");
  });

  it("keeps what the JSON has and drops what it does not", () => {
    expect(q("sport=basketball&table=bb_picks").table).toBe("bb_picks");
    expect(q("sport=basketball&table=fb_obr").table).toBe("bb_shots");
    expect(q("sport=tennis").sport).toBe("football");
    expect(q("table=fb_passing&group=Goalkeeper").group).toBe("Goalkeeper");
    // fb_physical has no goalkeepers.
    expect(q("table=fb_physical&group=Goalkeeper").group).toBeNull();
    expect(q("sport=basketball&group=Midfield").group).toBeNull();
  });

  it("takes a player only with the whole key of the sport, integers and a listed group", () => {
    const [a] = defaultPair("football");
    expect(q("a=51675-1803-Midfield").a).toEqual({ player_id: 51675, team_id: 1803, position_group: "Midfield" });
    expect(q("a=51675-1803-Center+Forward").a.position_group).toBe("Center Forward");
    for (const bad of ["51675-1803", "51675-1803-Striker", "x-1803-Midfield", "51675-1803-Midfield';DROP TABLE x;--", "1.5-2-Midfield"]) {
      expect(q(`a=${encodeURIComponent(bad)}`).a, bad).toEqual(a);
    }
    const [bbA] = defaultPair("basketball");
    expect(q("sport=basketball&a=28390-1315").a).toEqual({ player_id: 28390, team_id: 1315 });
    expect(q("sport=basketball&a=28390-1315-Midfield").a).toEqual(bbA);
  });

  it("writes back what it reads", () => {
    const text = "sport=football&table=fb_obr&group=Full+Back&a=51675-1803-Midfield&b=159688-868-Midfield";
    expect(paramsQuery(q(text))).toBe(text);
  });
});

describe("the percentile's step", () => {
  it("is the fifth of the pool, with no fill under 20", () => {
    expect([0, 19.9, 20, 39.9, 40, 59.9, 60, 79.9, 80, 100].map(pctlStep)).toEqual([0, 0, 1, 1, 2, 2, 3, 3, 4, 4]);
  });
});

describe("the percentile as printed, and small pools", () => {
  it("prints a whole number: the pool cannot tell one decimal", () => {
    expect([0, 3.7, 63.75, 63.8, 99.4, 100].map(formatPctl)).toEqual(["0", "4", "64", "64", "99", "100"]);
  });

  it("the football pools are the small ones, 14 to 47 players with a value; basketball's are not", () => {
    const small = (sport: string) =>
      SCOUTING.tables
        .filter((t) => t.sport === sport)
        .flatMap((t) => t.pools.flatMap((p) => p.n));
    const fb = small("football");
    expect(Math.min(...fb)).toBe(14);
    expect(Math.max(...fb)).toBe(47);
    expect(fb.every((n) => n < SMALL_POOL)).toBe(true);
    expect(Math.min(...small("basketball"))).toBeGreaterThanOrEqual(SMALL_POOL);
  });

  it("says what a place in the ranking is worth, from the pool's size", () => {
    expect(placeStep(14)).toBeCloseTo(100 / 13);
    expect(smallPoolNote(1)).toBe("Small pool (1 player, under 50): too few for a ranking.");
    expect(smallPoolNote(0)).toBe("Small pool (0 players, under 50): too few for a ranking.");
    expect(smallPoolNote(2)).toContain("100.0 points");
    expect(smallPoolNote(33)).toBe(
      "Small pool (33 players, under 50): one place in the ranking is 3.1 points of percentile.",
    );
  });
});

describe("a table's rows", () => {
  const t = tableOf("bb_shots")!;
  const metricCols = t.metrics.flatMap((m) => [m.id, `${m.id}_pctl`]);
  const columns = ["player_id", "team_id", "player_name", "team_name", "sample", ...metricCols];
  const row = (id: number, team: number, name: string, games: number, first: number | null, pctl: number | null) => [
    id,
    team,
    name,
    "Team",
    games,
    ...t.metrics.flatMap((_, i) => (i === 0 ? [first, pctl] : [1, 50])),
  ];
  // 92815 is an alias of 59180 in scouting.json, on the same team.
  const r = result(columns, [
    row(92815, 1330, "Alejandro REYES", 13, 0.4, 30),
    row(59180, 1330, "Alex Reyes", 19, null, null),
    row(1, 1, "José Zed", 30, 0.6, 90),
    row(2, 1, "Ann Bee", 12, 0.5, 60),
  ]);
  const rows = rowsOf(t, r);

  it("marks the alias row and the row of its new id", () => {
    expect(rows.map((x) => [x.aliasOf, x.hasAlias])).toEqual([
      [59180, null],
      [null, 92815],
      [null, null],
      [null, null],
    ]);
  });

  it("counts each pool's rows, players, sample and the n of each metric without its NULLs", () => {
    const [pool] = poolsOf(t, rows);
    expect(pool).toMatchObject({ group: null, rows: 4, players: 4, sample: 74 });
    expect(pool.n[0]).toBe(3);
    expect(pool.n[1]).toBe(4);
  });

  it("filters by name or team without accents and never changes a percentile", () => {
    const found = filterRows(rows, { search: "jose", maxAge: null });
    expect(found.map((x) => x.name)).toEqual(["José Zed"]);
    expect(found[0].cells[0].pctl).toBe(90);
    expect(filterRows(rows, { search: "", maxAge: null })).toHaveLength(4);
  });

  it("sorts by the value, a missing value last either way", () => {
    const by = (descending: boolean) => sortRows(rows, { column: "m:0", descending }).map((x) => x.name);
    expect(by(true)).toEqual(["José Zed", "Ann Bee", "Alejandro REYES", "Alex Reyes"]);
    expect(by(false)).toEqual(["Alejandro REYES", "Ann Bee", "José Zed", "Alex Reyes"]);
    expect(sortRows(rows, { column: "sample", descending: true }).map((x) => x.sample)).toEqual([30, 19, 13, 12]);
  });
});

describe("a comparison", () => {
  it("leaves a table under its floor without values and takes each pool from the JSON", () => {
    const tables = SCOUTING.tables.filter((t) => t.sport === "football");
    const columns = ["slot", "player_id", "team_id", "position_group", "player_name", "team_name", "age"];
    const values: RawValue[] = [0, 7, 8, "Midfield", "A Name", "A Team", 22];
    for (const [i, t] of tables.entries()) {
      columns.push(`${t.table}_below_floor`);
      values.push(i === 1);
      for (const m of t.metrics) {
        columns.push(`${t.table}__${m.id}`, `${t.table}__${m.id}_pctl`);
        values.push(i === 1 ? null : 1, i === 1 ? null : 42);
      }
    }
    const [c] = comparedOf("football", result(columns, [values]));
    expect(c.key).toEqual({ player_id: 7, team_id: 8, position_group: "Midfield" });
    expect(c.tables.map((t) => t.below)).toEqual([false, true, false]);
    expect(c.tables[1].cells.every((x) => x.value === null && x.pctl === null)).toBe(true);
    expect(c.tables[0].cells[0]).toEqual({ value: 1, pctl: 42 });
    expect(c.tables[0].pool?.players).toBe(SCOUTING.tables[0].pools.find((p) => p.group === "Midfield")?.players);
  });
});

describe("the head panel's probe", () => {
  const metrics = [
    { id: "a", expr: "a", label: "A", scale: "per_match", unit: "" },
    { id: "b", expr: "b", label: "B", scale: "per_match", unit: "" },
  ];
  const table = { table: "t", sport: "football", sample: "count_match", floor: "count_match >= 5", metrics } as never;

  it("leaves out a metric the probe has no value for instead of failing", () => {
    const probe: ScoutingProbe = { player_id: 1, team_id: 2, in_pool: true, values: { a: [1.5, 40], b: null } };
    expect(probeMetrics(table, probe)).toEqual([{ id: "a", label: "A", pctl: 40 }]);
  });

  it("draws every metric when the probe has them all", () => {
    const probe: ScoutingProbe = { player_id: 1, team_id: 2, in_pool: true, values: { a: [1, 10], b: [2, 90] } };
    expect(probeMetrics(table, probe).map((m) => m.pctl)).toEqual([10, 90]);
  });
});
