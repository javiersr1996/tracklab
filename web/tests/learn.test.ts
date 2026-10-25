import { describe, expect, it } from "vitest";
import { LESSONS } from "../lib/learn/series";
import { SOURCES, sourceProblems } from "../lib/learn/sources";
import { isCurrent, SECTIONS } from "../lib/sections";

describe("the series", () => {
  it("numbers its lessons in order with no gap (P9 renumbers after the lesson Javier dropped)", () => {
    expect(LESSONS.map((l) => l.n)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
    expect(new Set(LESSONS.map((l) => l.slug)).size).toBe(LESSONS.length);
  });

  it("gives every lesson a sport, and no digit in a title (the OG card prints the title and the lesson's number only)", () => {
    expect(LESSONS.filter((l) => !["Basketball", "Football", "Basketball and football"].includes(l.sport))).toEqual([]);
    expect(LESSONS.filter((l) => /\d/.test(l.title))).toEqual([]);
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
