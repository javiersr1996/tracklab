import { describe, expect, it } from "vitest";
import { formatBytes, pluralize } from "../lib/format";

describe("pluralize", () => {
  it("uses the singular form for a count of one", () => {
    expect(pluralize(1, "player")).toBe("1 player");
  });

  it("uses the default regular plural otherwise", () => {
    expect(pluralize(0, "player")).toBe("0 players");
    expect(pluralize(12, "player")).toBe("12 players");
  });

  it("accepts an explicit irregular plural", () => {
    expect(pluralize(2, "child", "children")).toBe("2 children");
  });
});

// Mirrors `pipeline/tests/unit/test_publish_format.py` case for case, so this
// function and Python's `fmt` (task 34) can never quietly diverge.
//
// Mutation checked by hand: base 1024 instead of base 10 turns
// `formatBytes(2316182304)` into `"2.2 GB"` (2316182304 / 1024**3 =
// 2.157...), not the `"2.3 GB"` asserted below, so
// `matches the real platform.json numbers` would fail under that mutation.
describe("formatBytes", () => {
  it("matches the real platform.json numbers", () => {
    expect(formatBytes(2316182304)).toBe("2.3 GB");
    expect(formatBytes(1230786)).toBe("1.2 MB");
    expect(formatBytes(999)).toBe("999 B");
  });

  it("switches unit at the 1000 boundary", () => {
    expect(formatBytes(1000)).toBe("1.0 KB");
  });

  it("picks the unit after rounding", () => {
    expect(formatBytes(999_949)).toBe("999.9 KB");
    expect(formatBytes(999_950)).toBe("1.0 MB");
    expect(formatBytes(999_950_000)).toBe("1.0 GB");
  });

  it("rounds an exact tie up, like Python's fmt", () => {
    expect(formatBytes(1250)).toBe("1.3 KB");
  });
});
