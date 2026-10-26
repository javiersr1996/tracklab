import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { check, type ExerciseMeta, shapeVerdict, verdictText } from "../lib/sql/check";
import { fingerprint, normalize, NotComparable, number, wrap } from "../lib/sql/normalize";

// The normalization of /sql (task 101, `lib/sql/normalize.ts`) against the fixtures that pytest
// reads too (`tests/fixtures/sql-normalize.json`): the same wrapper text has to give the same
// canonical JSON and the same SHA-256 in Python and in the browser, and a case the rule rejects
// (NaN, Infinity, too large) has to be rejected on both sides.
//
// Mutations checked by hand, each restored byte for byte:
// - `+ 0.5` removed from `number`: the tie cases (1/32, the negative tie, thirds) fail.
// - sorting unordered rows by `localeCompare` instead of bytes: "UTF-8 bytes, not UTF-16 units" fails.

interface Fixture {
  name: string;
  ordered: boolean;
  rows: string[];
  rejected: boolean;
  canonical?: string;
  sha256?: string;
}

const FIXTURES: { cases: Fixture[] } = JSON.parse(
  readFileSync(join(process.cwd(), "tests", "fixtures", "sql-normalize.json"), "utf-8"),
);

describe("the fixtures", () => {
  it("are the 27 cases pytest reads, 8 of them rejected", () => {
    expect(FIXTURES.cases).toHaveLength(27);
    expect(FIXTURES.cases.filter((c) => c.rejected)).toHaveLength(8);
  });

  it.each(FIXTURES.cases.filter((c) => !c.rejected).map((c) => [c.name, c]))("%s", async (_, c) => {
    const { canonical, sha256 } = await fingerprint(c.rows, c.ordered);
    expect(canonical).toBe(c.canonical);
    expect(sha256).toBe(c.sha256);
  });

  it.each(FIXTURES.cases.filter((c) => c.rejected).map((c) => [c.name, c]))("%s", (_, c) => {
    expect(() => normalize(c.rows, c.ordered)).toThrow(NotComparable);
  });
});

describe("wrap", () => {
  it("puts the query on its own lines inside the wrapper and strips a trailing semicolon", () => {
    expect(wrap("SELECT 1;")).toBe("SELECT json_array(*COLUMNS(*))::VARCHAR FROM (\nSELECT 1\n) q");
    expect(wrap("  SELECT 1 ; \n")).toBe("SELECT json_array(*COLUMNS(*))::VARCHAR FROM (\nSELECT 1\n) q");
  });

  it("keeps a trailing line comment from swallowing the closing parenthesis", () => {
    expect(wrap("SELECT 1 -- one")).toMatch(/-- one\n\) q$/);
  });
});

describe("number", () => {
  it("rounds half up at the fourth decimal, away from zero, and -0 to 0", () => {
    expect(number(0.03125)).toBe(313);
    expect(number(-0.00005)).toBe(-1);
    expect(Object.is(number(-0), 0)).toBe(true);
    expect(Object.is(number(-0.00001), 0)).toBe(true);
  });

  it("refuses NaN, infinities and the limit", () => {
    for (const x of [NaN, Infinity, -Infinity, 1e12, 900719925474.0992]) expect(() => number(x)).toThrow(NotComparable);
    expect(number(123456789012)).toBe(1234567890120000);
  });
});

// `select-1` of course.json as the checker sees it: 11 rows x 3 columns, ordered.
const META: ExerciseMeta = { ordered: true, columns: 3, rows: 11, sha256: "0".repeat(64) };

describe("the verdict", () => {
  it("names the shape difference the reader can act on first", () => {
    expect(shapeVerdict(META, { columns: 3, rowCount: 1001 })).toBe("over_limit");
    expect(shapeVerdict(META, { columns: 2, rowCount: 1001 })).toBe("over_limit");
    expect(shapeVerdict(META, { columns: 2, rowCount: 12 })).toBe("columns");
    expect(shapeVerdict(META, { columns: 3, rowCount: 12 })).toBe("rows");
    expect(shapeVerdict(META, { columns: 3, rowCount: 11 })).toBeNull();
  });

  it("hashes only a result of the right shape", async () => {
    const rows = ["[1,\"a\",null]"];
    const meta = { ...META, rows: 1, sha256: (await fingerprint(rows, true)).sha256 };
    expect(await check(meta, { columns: 3, rowCount: 1 }, rows)).toBe("correct");
    expect(await check(meta, { columns: 3, rowCount: 1 }, ["[2,\"a\",null]"])).toBe("values");
    expect(await check(meta, { columns: 3, rowCount: 2 }, rows)).toBe("rows");
    expect(await check(meta, { columns: 3, rowCount: 1 }, ["[NaN,\"a\",null]"])).toBe("uncomparable");
    expect(await check(meta, { columns: 3, rowCount: 1 }, ["[1e300,\"a\",null]"])).toBe("uncomparable");
  });

  it("compares an unordered exercise as a set and an ordered one in order", async () => {
    const rows = ["[2]", "[1]"];
    const unordered = { ordered: false, columns: 1, rows: 2, sha256: (await fingerprint(rows, false)).sha256 };
    expect(await check(unordered, { columns: 1, rowCount: 2 }, ["[1]", "[2]"])).toBe("correct");
    const ordered = { ...unordered, ordered: true, sha256: (await fingerprint(rows, true)).sha256 };
    expect(await check(ordered, { columns: 1, rowCount: 2 }, ["[1]", "[2]"])).toBe("values");
  });

  it("says what the reader sees", () => {
    const shape = { columns: 4, rowCount: 12 };
    expect(verdictText("correct", META, shape)).toBe("Correct");
    expect(verdictText("columns", META, shape)).toBe("3 columns expected, you have 4");
    expect(verdictText("columns", { ...META, columns: 1 }, shape)).toBe("1 column expected, you have 4");
    expect(verdictText("rows", META, shape)).toBe("11 rows expected, you have 12");
    expect(verdictText("values", META, shape)).toBe("Same shape, different values");
    expect(verdictText("over_limit", META, { columns: 3, rowCount: 5000 })).toBe("More than 1,000 rows; 11 expected");
    expect(verdictText("uncomparable", META, shape)).toMatch(/NaN, Infinity or very large numbers/);
  });
});
