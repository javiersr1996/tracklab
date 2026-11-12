import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import fence from "../lib/learn/fence.json";
import { cellPaths, check, FILE, type OccupancyFile, occupancyView, regions, stepOf, STEPS } from "../lib/occupancy/data";

// Task 184b: /tracking/occupancy's loader on the real `occupancy.json`, read here a second time
// from disk so nothing below trusts the import the page uses.
const RAW = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "occupancy.json"), "utf-8")) as OccupancyFile;
const copy = (): OccupancyFile => JSON.parse(JSON.stringify(RAW));

describe("occupancy.json", () => {
  it("names no held-out match and every group's shares add up to the whole", () => {
    expect(RAW.matches.filter((m) => fence.held_out.includes(m))).toEqual([]);
    expect(RAW.matches.length).toBeGreaterThan(0);
    for (const g of RAW.groups) {
      expect(g.share.reduce((a, b) => a + b, 0), g.group).toBe(RAW.share_scale);
      expect(g.share).toHaveLength(RAW.grid.cols * RAW.grid.rows);
    }
    expect(FILE).toEqual(RAW);
  });

  it("the loader refuses a held-out match and a group that does not add up", () => {
    const fenced = copy();
    fenced.matches.push(fence.held_out[0]);
    expect(() => check(fenced)).toThrow(/held-out/);
    const short = copy();
    short.groups[0].share[0] -= 1;
    expect(() => check(short)).toThrow(/sum/);
    expect(() => check(copy())).not.toThrow();
  });

  it("thirds and lanes each add up to the whole, and the outfield is the five groups pooled", () => {
    for (const g of RAW.groups) {
      const r = regions(RAW, g);
      expect(r.thirds.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 12);
      expect(r.lanes.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 12);
    }
    const [outfield, ...five] = [...RAW.groups].reverse();
    expect(outfield.group).toBe("Outfield");
    expect(outfield.player_frames).toBe(five.reduce((a, g) => a + g.player_frames, 0));
    expect(outfield.player_matches).toBe(five.reduce((a, g) => a + g.player_matches, 0));
  });

  it("the busiest third is the one with the most cells' share, counted here by columns", () => {
    const view = occupancyView(RAW);
    for (const [i, g] of RAW.groups.entries()) {
      const cols = RAW.grid.cols;
      const byThird = [0, 1, 2].map((t) => g.share.filter((_, c) => Math.floor((c % cols) / (cols / 3)) === t).reduce((a, b) => a + b, 0));
      const best = byThird.indexOf(Math.max(...byThird));
      expect(view.groups[i].third.share).toBeCloseTo(byThird[best] / RAW.share_scale, 12);
      expect(view.groups[i].third.name).toBe(["own third", "middle third", "attacking third"][best]);
    }
  });
});

describe("the colour steps", () => {
  it("leave a share under the floor at the pitch's colour and give the largest the top step", () => {
    expect(stepOf(0, 0.01)).toBe(0);
    expect(stepOf(0.00009, 0.01)).toBe(0);
    expect(stepOf(0.0001, 0.01)).toBe(1);
    expect(stepOf(0.01, 0.01)).toBe(STEPS);
    // Equal slices of the top: a quarter of it ends step 2 of 8, a hair more starts step 3.
    expect(stepOf(0.0025, 0.01)).toBe(2);
    expect(stepOf(0.00251, 0.01)).toBe(3);
  });

  it("draw every cell over the floor exactly once, in runs along a row", () => {
    const view = occupancyView(RAW);
    for (const g of view.groups) {
      const paths = cellPaths(g, RAW.grid.cols, view.top);
      let cells = 0;
      for (const p of paths) for (const m of p.d.matchAll(/h(\d+)/g)) cells += Number(m[1]);
      expect(cells, g.group).toBe(g.share.filter((s) => stepOf(s, view.top) > 0).length);
    }
    // A run never wraps to the next row: a row of three cells, then one on the next row.
    const toy = { share: [0.5, 0.5, 0.5, 0.5], slug: "t" } as Parameters<typeof cellPaths>[0];
    expect(cellPaths(toy, 3, 0.5)).toEqual([{ step: STEPS, d: "M0 0h3v1h-3zM0 1h1v1h-1z" }]);
  });
});
