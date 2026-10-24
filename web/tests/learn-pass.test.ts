import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CANVAS } from "../components/learn/gravity/Plot";
import { Lesson } from "../components/learn/pass/Lesson";
import { PassArc } from "../components/learn/pass/PassArc";
import { PerMatch } from "../components/learn/pass/PerMatch";
import { display } from "../lib/learn/display";
import fence from "../lib/learn/fence.json";
import { figureAt } from "../lib/learn/json-figure";
import { chord, path, perSecond, type Point3 } from "../lib/learn/pass";
import { PASS, PASS_EXAMPLES } from "../lib/learn/pass-data";
import { lessonPassFigures } from "../lib/learn/pass-figures";

// Lesson 7: the arithmetic of lib/learn/pass.ts, the example against pass.json, then the text as
// the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - `chord` in the plane (no z): "the example's chords and paths are the pipeline's" fails, and so
//   does "no path is shorter than its chord" on the bounce.
// - `path` skipping the last step: "the example's chords and paths are the pipeline's" fails.
// - `perSecond` over frames, not seconds: "is a length over a time" fails.
// - A speed typed in the text for its `data-fig`: "has no digit typed in the prose" fails.

const F = lessonPassFigures(PASS, PASS_EXAMPLES);
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));

describe("chord and path", () => {
  const up: Point3[] = [
    [0, 0, 1],
    [3, 0, 0],
    [6, 0, 1],
  ];

  it("the chord joins the ends in three dimensions; the path adds every step", () => {
    expect(chord([0, 0, 0], [3, 4, 12])).toBe(13);
    expect(path(up)).toBeCloseTo(2 * Math.hypot(3, 1), 12);
    expect(chord(up[0], up[2])).toBe(6);
  });

  it("no path is shorter than its chord, and a level line makes them equal", () => {
    expect(path(up)).toBeGreaterThan(chord(up[0], up[2]));
    const level: Point3[] = Array.from({ length: 6 }, (_, k) => [k, 2 * k, 1]);
    expect(path(level)).toBeCloseTo(chord(level[0], level[5]), 12);
  });

  it("is a length over a time", () => {
    expect(perSecond(6, 10, 25)).toBe(15);
  });
});

describe("the example against pass.json", () => {
  it("the example's chords and paths are the pipeline's, to the decimals it publishes", () => {
    for (const ex of PASS_EXAMPLES) {
      const c = chord(ex.ball[0], ex.ball[ex.ball.length - 1]);
      expect(Number(c.toFixed(4))).toBe(ex.entry.chord_m);
      expect(Number(path(ex.ball).toFixed(4))).toBe(ex.entry.path_m);
      expect(Number(perSecond(c, ex.entry.frames, PASS.fps).toFixed(2))).toBe(ex.entry.chord_speed);
    }
  });

  it("the provider's distance is the players' separation at the first frame, to the possession's centimetre", () => {
    for (const p of F.passes) expect(Math.abs(p.distance_m - p.separation_m)).toBeLessThanOrEqual(0.015);
    expect(F.separation_gap).toBe(0);
  });

  it("the bounce pass is the one whose path bends most, and its ball reaches the floor's height range", () => {
    const b = F.passes[F.bounce - 1];
    expect(b.path_pct).toBe(Math.max(...F.passes.map((p) => p.path_pct)));
    expect(b.z_min).toBeLessThan(Math.min(...F.passes.filter((_, i) => i !== F.bounce - 1).map((p) => p.z_min)));
  });

  it("the selection adds up", () => {
    expect(F.complete - F.not_forward - F.no_ball).toBe(F.measured);
    expect(F.measured).toBe(PASS.matches.reduce((s, m) => s + m.n, 0));
  });

  it("the figure opens on the first pass", () => {
    const markup = html(PassArc, { passes: PASS_EXAMPLES, fps: PASS.fps });
    const cell = (name: string) => markup.match(new RegExp(`data-fig="${name}">([^<]*)<`))?.[1];
    expect(cell("learn.arc.pass")).toBe("1");
    expect(cell("learn.arc.chord_speed")).toBe(String(F.passes[0].chord_speed));
    expect(cell("learn.arc.distance_speed")).toBe(String(F.passes[0].distance_speed));
  });
});

// The text as the server renders it.
const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "pass.sql"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { sql: SQL }));
const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (h: string, tags: string[]) => tags.reduce((acc, tag) => acc.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), h);
const text = (h: string) => entities(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const PROSE = text(drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]));
const FIGS = F as unknown as Record<string, unknown>;
const source = (name: string): unknown =>
  name.startsWith("learn.")
    ? name
        .slice(6)
        .split(".")
        .reduce<unknown>((o, k) => (o as Record<string, unknown>)?.[k], FIGS)
    : figureAt(PASS, "pass", name);

describe("the text of lesson 7", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(100);
    const wrong = figs.filter(([name, shown]) => {
      // The figure's readouts live in its state; "the figure opens on the first pass" checks them.
      if (name.startsWith("learn.arc.")) return false;
      const value = source(name);
      return value === undefined || shown !== display(String(value), name);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,30}\d+.{0,30}/g)).toBeNull();
  });

  it("never says the vetted words, quotes included, and keeps the fence", () => {
    const all = text(HTML).toLowerCase();
    expect(["straight line", "constant speed", "time to impact", "second difference"].filter((w) => all.includes(w))).toEqual([]);
    expect(all).toContain("chord");
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    expect(["detected", "football"].filter((w) => outside.includes(w))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
  });

  it("is between 1,300 and 2,300 words: its figures counted, its formulas, query and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 7: ${words} words`);
    expect(words).toBeGreaterThanOrEqual(1300);
    expect(words).toBeLessThanOrEqual(2300);
  });
});

// WCAG relative luminance and contrast of two #rrggbb colours.
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

describe("the figures' colours", () => {
  it("every stroke and fill the pass figure and the table render is 3:1 or more on the canvas", () => {
    const markups = [html(PassArc, { passes: PASS_EXAMPLES, fps: PASS.fps }), html(PerMatch, { matches: PASS.matches })];
    const colours = new Set(markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none"));
    expect(colours.size).toBeGreaterThan(3);
    expect([...colours].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3)).toEqual([]);
  });
});
