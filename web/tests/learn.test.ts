import { describe, expect, it } from "vitest";
import { LESSONS } from "../lib/learn/series";
import { SOURCES, sourceProblems } from "../lib/learn/sources";
import { BUILT, EXPLORE, inEntry, isCurrent, NAV, pageOf, SECTIONS } from "../lib/sections";

describe("the series", () => {
  it("numbers its lessons in order with no gap (P9 renumbers after the lesson Javier dropped)", () => {
    expect(LESSONS.map((l) => l.n)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
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

  it("keeps Learn, SQL (P12) and EuroLeague (P14) last; P23 adds scouting, positions and occupancy", () => {
    expect(SECTIONS).toHaveLength(12);
    expect(SECTIONS.map((s) => s.href).slice(-3)).toEqual(["/learn", "/sql", "/euroleague"]);
    expect(SECTIONS.map((s) => s.href)).toEqual(expect.arrayContaining(["/warehouse/scouting", "/warehouse/positions", "/tracking/occupancy"]));
  });

  it("puts every section on the home (P23): a card under Explore or How it is built, or the lessons' band", () => {
    const home = [...EXPLORE, ...BUILT, "/learn", "/sql"];
    expect(new Set(home).size).toBe(home.length);
    expect([...home].sort()).toEqual(SECTIONS.map((s) => s.href).sort());
  });

  it("gives the header its entries (P15; P21: SQL under Learn) and About (P20), each group current on its pages and every section but /euroleague in the menu", () => {
    expect(NAV.map((n) => n.nav)).toEqual(["Tracking", "Engineering", "Warehouse", "Learn", "About"]);
    for (const n of NAV) for (const p of n.pages ?? []) expect(inEntry(p.href, n), p.href).toBe(true);
    const learn = NAV.find((n) => n.nav === "Learn")!;
    expect(learn.pages!.map((p) => p.href)).toEqual(["/learn", "/sql"]);
    expect(inEntry("/sql/joins", learn)).toBe(true);
    expect(inEntry("/sqlx", learn)).toBe(false);
    expect(pageOf("/sql/joins", learn.pages!)?.nav).toBe("SQL course");
    expect(pageOf("/learn/gravity", learn.pages!)?.nav).toBe("Lessons");
    const engineering = NAV.find((n) => n.nav === "Engineering")!;
    expect(pageOf("/engineering/quality", engineering.pages!)?.nav).toBe("Quality");
    expect(pageOf("/engineering", engineering.pages!)?.nav).toBe("Platform");
    expect(pageOf("/tracking", NAV[0].pages!)).toBeUndefined();
    const reachable = NAV.flatMap((n) => [n.href, ...(n.pages ?? []).map((p) => p.href)]);
    // /euroleague is the one section off the menu (P27): the home and a lesson lead to it.
    for (const s of SECTIONS) expect(reachable.includes(s.href), s.href).toBe(s.href !== "/euroleague");
  });
});
