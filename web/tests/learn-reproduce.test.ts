import { describe, expect, it } from "vitest";
import { browserSql, parseBrowserSql } from "../lib/learn/browser-sql";
import { reproduced } from "../lib/learn/reproduce";

// Task 86: the rows of "Run it here" against the page, and the build-time reading of the lessons'
// `.browser.sql` (the same rules as `tracklab.learn.browser.parse`).
describe("reproduced", () => {
  const page: Record<string, string[]> = { "learn.fit_g": ["8.14535"], "learn.all_rows": ["8,297,040", "8,297,040"], "learn.x": ["1", "2"] };
  const printed = (f: string) => page[f] ?? [];

  it("matches a row when every place the page prints its figure reads the row's value", () => {
    const rows = reproduced(["figure", "value"], [["learn.fit_g", "8.14535"], ["learn.all_rows", "8297040"]], printed);
    expect(rows?.map((r) => r.matched)).toEqual([true, true]);
  });

  it("does not match a wrong value, a figure the page does not print, or one it prints two ways", () => {
    const rows = reproduced(["figure", "value"], [["learn.fit_g", "4.07268"], ["learn.none", "1"], ["learn.x", "1"]], printed);
    expect(rows?.map((r) => r.matched)).toEqual([false, false, false]);
  });

  it("compares nothing when the result has no figure and value columns", () => {
    expect(reproduced(["n"], [["1"]], printed)).toBeNull();
  });
});

describe("browserSql", () => {
  it.each(["gravity", "speed", "coordinates", "rebound", "cadence"])("%s: files, views and one query", (slug) => {
    const { query, views, sql } = browserSql(slug);
    expect(query.files.length).toBeGreaterThan(0);
    expect(query.files.every((f) => f.bytes > 0)).toBe(true);
    expect(query.views.length).toBeGreaterThan(0);
    expect(views).toContain("CREATE VIEW");
    expect(sql).not.toContain("CREATE VIEW");
    expect(sql.trimEnd().endsWith(";")).toBe(false);
  });

  it("refuses a file that is not views followed by one query", () => {
    expect(() => parseBrowserSql("x", "CREATE VIEW a AS SELECT 1;\nSELECT 2\n")).toThrow(/files/);
    expect(() => parseBrowserSql("x", "-- files: /data/a.json\nSELECT 1;\nSELECT 2\n")).toThrow(/CREATE VIEW/);
  });
});
