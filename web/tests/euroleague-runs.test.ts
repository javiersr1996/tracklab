import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ranks, type Runs, score } from "../lib/euroleague/runs";

describe("the ranks of a list of runs", () => {
  it("gives a tie the same place and skips the ones it takes", () => {
    expect(ranks([25, 22, 18, 18, 18, 17])).toEqual([1, 2, 3, 3, 3, 6]);
    expect(ranks([5])).toEqual([1]);
    expect(ranks([])).toEqual([]);
  });

  it("writes a score with an en dash, the team's first", () => {
    expect(score([77, 50])).toBe("77–50");
  });
});

describe("runs.json, as the page reads it", () => {
  const file = JSON.parse(
    readFileSync(join(process.cwd(), "public", "data", "euroleague", "runs.json"), "utf-8"),
  ) as Runs;

  it("lists each season's runs and comebacks from the biggest, at least the top and no more than its ties", () => {
    for (const s of file.seasons) {
      for (const sizes of [s.runs.map((r) => r.size), s.comebacks.map((c) => c.deficit)]) {
        expect(sizes).toEqual([...sizes].sort((a, b) => b - a));
        expect(sizes.length).toBeGreaterThanOrEqual(file.top);
        // Whoever is listed past the top ties with the last of the top.
        expect(sizes.slice(file.top).every((n) => n === sizes[file.top - 1])).toBe(true);
      }
    }
  });
});
