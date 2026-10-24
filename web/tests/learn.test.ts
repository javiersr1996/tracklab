import { describe, expect, it } from "vitest";
import { LESSONS } from "../lib/learn/series";
import { SOURCES, sourceProblems } from "../lib/learn/sources";
import { isCurrent, SECTIONS } from "../lib/sections";

describe("the series", () => {
  it("lists only the five lessons before the Analytics Cup fence, numbered in order", () => {
    expect(LESSONS.map((l) => l.n)).toEqual([1, 2, 3, 4, 5]);
    expect(new Set(LESSONS.map((l) => l.slug)).size).toBe(LESSONS.length);
  });

  it("opens with the gravity lesson, published", () => {
    expect(LESSONS[0]).toMatchObject({ slug: "gravity", status: "published" });
  });
});

describe("sources", () => {
  it("every source has a label, an https url and a read date", () => {
    expect(Object.entries(SOURCES).flatMap(([id, s]) => sourceProblems(id, s))).toEqual([]);
  });

  it("flags a source that lacks them", () => {
    expect(sourceProblems("x", { label: "", url: "http://a", read: "soon" })).toHaveLength(3);
  });
});

describe("isCurrent", () => {
  it("matches the section page and the pages under it, not a sibling prefix", () => {
    expect(isCurrent("/learn", "/learn")).toBe(true);
    expect(isCurrent("/learn/gravity", "/learn")).toBe(true);
    expect(isCurrent("/learner", "/learn")).toBe(false);
    expect(isCurrent("/", "/learn")).toBe(false);
  });

  it("makes Learn the seventh section", () => {
    expect(SECTIONS).toHaveLength(7);
    expect(SECTIONS.at(-1)?.href).toBe("/learn");
  });
});
