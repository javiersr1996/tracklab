import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import { queryWarehouse } from "../lib/warehouse/node-engine";
import { quantileCont, SPOTS, type PositionsView } from "../lib/warehouse/positions";
import { positionsView } from "../lib/warehouse/positions-data";
import { checkSql } from "../lib/warehouse/sql";

// Task 184a: /warehouse/positions reads fb_physical's Parquet at build time. Its pools must be the
// scouting page's (scouting.json counts them in Python), and its quartiles what the query it prints
// returns when DuckDB runs it. Broken on purpose while writing these: a floor of 4 matches moved
// every n off scouting.json's; quartiles taken at the nearest rank instead of between the two
// closest moved a median off the query's; printing a quartile without rounding it as DuckDB does
// put one a hundredth off what the console prints.
const SCOUTING = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "scouting.json"), "utf-8")) as {
  tables: { table: string; metrics: { id: string }[]; pools: { group: string; players: number; n: number[] }[] }[];
};
const PHYSICAL = SCOUTING.tables.find((t) => t.table === "fb_physical")!;

let view: PositionsView;
beforeAll(async () => {
  view = await positionsView();
}, 60_000);

describe("/warehouse/positions", () => {
  it("counts each group's pool as scouting.json does, metric by metric", () => {
    for (const m of view.metrics) {
      const k = PHYSICAL.metrics.findIndex((x) => x.id === m.id);
      expect(m.groups.map((g) => [g.group, g.n])).toEqual(PHYSICAL.pools.map((p) => [p.group, p.n[k]]));
    }
    expect(view.metrics[0].groups.map((g) => g.n)).toEqual(PHYSICAL.pools.map((p) => p.players));
  });

  it("places every group it draws on the pitch", () => {
    for (const g of view.metrics[0].groups) expect(SPOTS[g.group], g.group).toBeDefined();
  });

  it("gets the quartiles the printed query returns from DuckDB, and the query passes the console's check", async () => {
    for (const m of view.metrics) {
      expect(checkSql(m.sql, ["fb_physical"]), m.id).toMatchObject({ ok: true });
      const exact = await queryWarehouse(m.sql.replace(/round\((quantile_cont\([^)]*\)), \d\)/g, "$1"));
      const byGroup = new Map(exact.map((r) => [r.position_group, r]));
      for (const g of m.groups) {
        const r = byGroup.get(g.group)!;
        expect(r.n, `${m.id} ${g.group}`).toBe(g.n);
        for (const q of ["q1", "median", "q3"] as const) expect(g[q], `${m.id} ${g.group} ${q}`).toBeCloseTo(r[q] as number, 9);
      }
      // As printed, the query rounds to the places the page prints.
      const rounded = await queryWarehouse(m.sql);
      for (const r of rounded) {
        const g = m.groups.find((x) => x.group === r.position_group)!;
        for (const q of ["q1", "median", "q3"] as const) {
          expect(Number(g.text[q].replaceAll(",", "")), `${m.id} ${g.group} ${q}`).toBeCloseTo(r[q] as number, 9);
        }
      }
    }
  }, 60_000);

  it("takes a quantile between the two closest ranks", () => {
    expect(quantileCont([1, 2, 3, 4], 0.5)).toBe(2.5);
    expect(quantileCont([1, 2, 3, 4, 10], 0.75)).toBe(4);
    expect(quantileCont([0, 10], 0.25)).toBe(2.5);
  });

  it("names the one competition and season of the file", () => {
    expect(view.competition.length).toBeGreaterThan(0);
    expect(view.season.length).toBeGreaterThan(0);
  });
});
