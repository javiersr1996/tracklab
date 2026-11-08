import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { latestContractRun, type HistoryEntry } from "../lib/history";
import { DUCKDB_VERSION } from "../lib/platform";

// P19, task 155: the figures `/engineering`, `/engineering/quality` and the lessons used to type
// by hand are read from the JSON that holds them. Read here straight from the files, not through
// the app's helpers, so a change to the JSON or to the helpers shows up as a disagreement.

const read = (name: string) => JSON.parse(readFileSync(join(process.cwd(), "public/data", name), "utf-8"));
const source = (...p: string[]) => readFileSync(join(process.cwd(), ...p), "utf-8");

afterEach(() => {
  vi.doUnmock("../public/data/quality.json");
  vi.resetModules();
});

describe("the DuckDB version the lessons name", () => {
  it("is the one platform.json records", () => {
    expect(DUCKDB_VERSION).toBe(read("platform.json").run.versions.duckdb);
    expect(DUCKDB_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("is in no lesson as a literal", () => {
    const lessons = readdirSync(join(process.cwd(), "components/learn"), { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => join("components/learn", d.name, "Lesson.tsx"));
    expect(lessons.length).toBeGreaterThan(5);
    for (const f of lessons) expect(source(f), f).not.toContain(DUCKDB_VERSION);
  });
});

describe("the contract tests of /engineering", () => {
  const entry = (id: string, executed: boolean, passed: number | null) =>
    ({ id, quality: { contracts: { executed, passed } } }) as unknown as HistoryEntry;

  it("count the newest record that ran them, not the newest record", () => {
    expect(latestContractRun([entry("a", true, 90), entry("b", true, 104), entry("c", false, null)])).toEqual({
      id: "b",
      passed: 104,
    });
    expect(latestContractRun([entry("a", false, null)])).toBeNull();
  });

  it("are history.json's last executed record", () => {
    const executed = read("history.json").entries.filter((e: HistoryEntry) => e.quality.contracts.executed === true);
    expect(latestContractRun()).toEqual({ id: executed.at(-1).id, passed: executed.at(-1).quality.contracts.passed });
  });

  it("are not called 'contract tests' for a number of files", () => {
    expect(source("app/engineering/page.tsx")).not.toMatch(/contracts\.files[^\n]*<\/span> contract tests/);
  });
});

describe("the checks of /engineering/quality", () => {
  const lede = async (checks: Record<string, unknown[]>) => {
    const real = read("quality.json");
    vi.resetModules();
    vi.doMock("../public/data/quality.json", () => ({ default: { ...real, checks } }));
    const { default: Page } = await import("../app/engineering/quality/page");
    return /(\d+) checks/.exec(renderToStaticMarkup(Page()))?.[1];
  };

  it("are counted from quality.json, with a column in the table", async () => {
    const real = read("quality.json").checks as Record<string, unknown[]>;
    const tabulated = ["detection", "gravity", "entry_angle", "noise", "clock"].filter((c) => real[c]?.length);
    expect(await lede(real)).toBe(String(tabulated.length));
  });

  it("follow the JSON: a check dropped from it is dropped from the count", async () => {
    const real = read("quality.json").checks as Record<string, unknown[]>;
    const { gravity: _gravity, ...without } = real;
    expect(await lede(without)).toBe(String(["detection", "entry_angle", "noise", "clock"].filter((c) => real[c]?.length).length));
  });

  it("are not typed as a number word", () => {
    expect(source("app/engineering/quality/page.tsx")).not.toMatch(/\bfive checks\b/);
  });
});
