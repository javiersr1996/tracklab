import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BounceStrip } from "../components/learn/dribble/BounceStrip";
import { Lesson } from "../components/learn/dribble/Lesson";
import { PerMatch } from "../components/learn/dribble/PerMatch";
import { CANVAS } from "../components/learn/gravity/Plot";
import { display } from "../lib/learn/display";
import { intervals, lowest, lowPoints, rhythm } from "../lib/learn/dribble";
import { DRIBBLE, TOUCH } from "../lib/learn/dribble-data";
import { lessonDribbleFigures } from "../lib/learn/dribble-figures";
import fence from "../lib/learn/fence.json";
import { figureAt } from "../lib/learn/json-figure";

// Lesson 9: the arithmetic of lib/learn/dribble.ts, the example against dribble.json, then the
// text as the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - `lowest` with `<=` (ties to the latest frame): "ties to the earliest" fails, and so does
//   "the example's offsets are the pipeline's" (dribble 4).
// - `lowest` looking only after the event (k from 0): the example loses its pair on one low point,
//   `touchFigures` throws and the whole file fails.
// - `lowPoints` counting a run of equal lows at every frame: "counts a run of equal lows once" fails.
// - `rhythm` without the parabola's shift (the lag at the integer peak): "finds the period of a
//   bouncing height" fails.
// - A rate typed in the text for its `data-fig`: "has no digit typed in the prose" fails.

const F = lessonDribbleFigures(DRIBBLE, TOUCH);
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));

// A ball that bounces every `period` frames: its height falls and rises in a V, lowest at 0.3 m.
const bouncing = (n: number, period: number, phase = 0) =>
  Array.from({ length: n }, (_, i) => 0.3 + Math.abs((((i + phase) % period) + period) % period - period / 2) * 0.1);

describe("intervals, lowest points and rhythm", () => {
  it("an interval is the gap between consecutive events", () => {
    expect(intervals([100, 120, 140, 143])).toEqual([20, 20, 3]);
    expect(intervals([5])).toEqual([]);
  });

  it("finds the lowest height within the window, ties to the earliest, and none when a frame is missing", () => {
    const z = [1, 0.9, 0.5, 0.7, 0.5, 0.8, 1];
    expect(lowest(z, 100, 103, 2)).toEqual({ k: -1, z: 0.5 });
    expect(lowest(z, 100, 104, 1)).toEqual({ k: 0, z: 0.5 });
    expect(lowest(z, 100, 104, 2)).toEqual({ k: -2, z: 0.5 });
    expect(lowest([1, null, 0.4, 0.6, 1], 0, 2, 1)).toBeNull();
    expect(lowest([1, 0.4, 0.6], 0, 2, 2)).toBeNull(); // the window runs past the data
  });

  it("counts a run of equal lows once, at its first frame", () => {
    expect(lowPoints([1, 0.5, 0.5, 1, 0.4, 1])).toEqual([1, 4]);
    expect(lowPoints([1, 0.9, 0.8])).toEqual([]);
  });

  it("finds the period of a bouncing height from its autocorrelation", () => {
    // Periods between frames too: the parabola's shift takes the lag off the integer.
    for (const period of [16, 18.5, 20.25, 23.5]) {
      const peak = rhythm(bouncing(Math.round(5 * period), period, 3));
      expect(peak).not.toBeNull();
      expect(Math.abs(peak!.lag - period)).toBeLessThan(0.2);
    }
  });
});

describe("the example against dribble.json", () => {
  it("the example's offsets and lowest heights are the pipeline's, from the same published heights", () => {
    expect(F.dribbles.map((r) => r.offset)).toEqual(DRIBBLE.example.dribbles.map((e) => e.offset));
    expect(F.dribbles.map((r) => r.low_z)).toEqual(DRIBBLE.example.dribbles.map((e) => e.low_z));
  });

  it("the shared pair is two consecutive dribbles on one lowest frame", () => {
    const [a, b] = [F.dribbles[F.shared_first - 1], F.dribbles[F.shared - 1]];
    expect(F.shared).toBe(F.shared_first + 1);
    expect(a.low_frame).toBe(b.low_frame);
    expect(F.shared_gap_frames).toBe(b.gap_frames);
  });

  it("the touch's rhythm is resolved and the rates are one over the periods", () => {
    expect(F.ac_ratio).toBeGreaterThan(0);
    expect(F.ac_rate).toBeCloseTo(1 / F.ac_period_s, 1);
    expect(F.rate_hi).toBe(Number((1 / F.med_lo).toFixed(2)));
  });

  it("the selection adds up", () => {
    expect(F.dribbles_all - F.no_window).toBe(F.windows);
    expect(F.intervals).toBe(DRIBBLE.matches.reduce((s, m) => s + m.intervals, 0));
  });

  it("the figure opens on the first dribble", () => {
    const markup = html(BounceStrip, { ex: TOUCH, figures: { dribbles: F.dribbles, ac_lag: F.ac_lag, ac_k: F.ac_k } });
    const cell = (name: string) => markup.match(new RegExp(`data-fig="${name}">([^<]*)<`))?.[1];
    expect(cell("learn.strip.dribble")).toBe("1");
    expect(cell("learn.strip.low_z")).toBe(String(F.dribbles[0].low_z));
    expect(cell("learn.strip.offset")).toBe(String(F.dribbles[0].offset));
  });
});

// The text as the server renders it.
const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "dribble.sql"), "utf-8");
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
    : figureAt(DRIBBLE, "dribble", name);

describe("the text of lesson 9", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(150);
    const wrong = figs.filter(([name, shown]) => {
      // The figure's readouts live in its state; "the figure opens on the first dribble" checks them.
      if (name.startsWith("learn.strip.")) return false;
      const value = source(name);
      return value === undefined || shown !== display(String(value), name);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,30}\d+.{0,30}/g)).toBeNull();
  });

  it("never says the vetted words and keeps the fence", () => {
    const all = text(HTML).toLowerCase();
    expect(["straight line", "constant speed", "time to impact", "second difference"].filter((w) => all.includes(w))).toEqual([]);
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    expect(["detected", "football"].filter((w) => outside.includes(w))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
  });

  it("is between 1,300 and 2,300 words: its figures counted, its formulas, query and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 9: ${words} words`);
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
  it("every stroke and fill the bounce figure and the table render is 3:1 or more on the canvas", () => {
    const markups = [
      html(BounceStrip, { ex: TOUCH, figures: { dribbles: F.dribbles, ac_lag: F.ac_lag, ac_k: F.ac_k } }),
      html(PerMatch, { matches: DRIBBLE.matches }),
    ];
    const colours = new Set(markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none"));
    expect(colours.size).toBeGreaterThan(3);
    expect([...colours].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3)).toEqual([]);
  });
});
