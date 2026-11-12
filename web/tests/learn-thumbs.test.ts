import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { LESSONS } from "../lib/learn/series";
import { type Mark, THUMB, thumbOf } from "../lib/learn/thumbs";

// Task 182: the drawing beside each lesson on /learn. Broken on purpose while writing these: a
// thumbnail drawn for one slug only fails the first; the same drawing for two lessons the second;
// a bar width from a typed share, or the ticks of another touch, the two that reread the files.
const json = (...parts: string[]) => JSON.parse(readFileSync(join(process.cwd(), "public", "data", ...parts), "utf-8"));
const published = LESSONS.filter((l) => l.status === "published");

// Every point an absolute M or L command visits, every dot and every rect's corners.
function points(m: Mark): [number, number][] {
  if (m.kind === "dots") return m.at.map(([x, y]) => [x, y]);
  if (m.kind === "rect") return [[m.x, m.y], [m.x + m.w, m.y + m.h]];
  return [...m.d.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g)].map((g) => [Number(g[1]), Number(g[2])]);
}

describe("lesson thumbnails", () => {
  it("draws one for every published lesson, and none for a slug it does not know", () => {
    for (const l of published) expect(thumbOf(l.slug)?.length ?? 0, l.slug).toBeGreaterThanOrEqual(2);
    expect(thumbOf("no-such-lesson")).toBeNull();
  });

  it("draws no two lessons alike", () => {
    const drawn = published.map((l) => JSON.stringify(thumbOf(l.slug)));
    expect(new Set(drawn).size).toBe(published.length);
  });

  it("keeps every data mark inside the box (a court or a pitch may run past it and is clipped)", () => {
    for (const l of published) {
      for (const m of thumbOf(l.slug)!.filter((x) => x.tone !== "axis")) {
        for (const [x, y] of points(m)) {
          expect(x, `${l.slug} x`).toBeGreaterThanOrEqual(0);
          expect(x, `${l.slug} x`).toBeLessThanOrEqual(THUMB.w);
          expect(y, `${l.slug} y`).toBeGreaterThanOrEqual(0);
          expect(y, `${l.slug} y`).toBeLessThanOrEqual(THUMB.h);
        }
      }
    }
  });

  it("sizes lesson 12's bars from expected-points.json: widths by attempts, heights by points per shot", () => {
    const season = json("euroleague", "expected-points.json").seasons[0];
    const classes = ["rim", "mid", "three"];
    const bars = thumbOf("expected-points")!.filter((m): m is Extract<Mark, { kind: "rect" }> => m.kind === "rect");
    expect(bars).toHaveLength(classes.length);
    const total = classes.reduce((s, c) => s + season.league[c].n, 0);
    const inner = THUMB.w - 2 * THUMB.pad;
    const tallest = Math.max(...classes.map((c) => season.pps[c]));
    classes.forEach((c, i) => {
      expect(bars[i].w + 2, c).toBeCloseTo((inner * season.league[c].n) / total, 0);
      expect(bars[i].h, c).toBeCloseTo(((THUMB.h - 2 * THUMB.pad) * season.pps[c]) / tallest, 0);
    });
  });

  it("ticks each dribble of dribble.json's example touch, and draws each player of rebound.json's example", () => {
    const ticks = thumbOf("dribble")!.find((m) => m.tone === "alt" && m.kind === "stroke")!;
    expect(ticks.kind === "stroke" && ticks.d.match(/M/g)?.length).toBe(json("learn", "dribble.json").example.dribbles.length);
    const players = json("learn", "rebound.json").example.players as { team: string }[];
    const dots = thumbOf("rebound")!.filter((m): m is Extract<Mark, { kind: "dots" }> => m.kind === "dots");
    expect(dots.map((d) => d.at.length)).toEqual(["shooting", "defending"].map((t) => players.filter((p) => p.team === t).length));
  });
});
