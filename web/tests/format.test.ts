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
