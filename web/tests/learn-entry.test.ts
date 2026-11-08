import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EntryFigure } from "../components/learn/entry/EntryFigure";
import { Lesson } from "../components/learn/entry/Lesson";
import { PerMatch } from "../components/learn/entry/PerMatch";
import { CANVAS } from "../components/learn/gravity/Plot";
import { display } from "../lib/learn/display";
import { flight, lsSlope, median, perfectRun, roundHalfEven, type EntryConstants, type Sample } from "../lib/learn/entry";
import { ENTRY, ENTRY_MATCHES, ENTRY_RUN, ENTRY_SAMPLES } from "../lib/learn/entry-data";
import { entryFigures } from "../lib/learn/entry-figures";
import fence from "../lib/learn/fence.json";
import { qualityFigure } from "../lib/learn/gravity-data";
import { figureAt } from "../lib/learn/json-figure";
import { HOOK, QUALITY } from "../lib/quality";

// Lesson 8: the arithmetic of lib/learn/entry.ts against entry.py's, through the example the
// pipeline computed with it, then the text as the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - v_h over the first 4 samples instead of `v_h_frames`: "gives the pipeline's angles" fails.
// - The rim at 3.05 m in `flight` with 3.048 in the file: "gives the pipeline's angles" fails on
//   the required angle (its fourth decimal).
// - `roundHalfEven` as Math.round: "rounds a half to the even integer" fails.
// - The tail without its first sample (`k - tail_back + 1`): "gives the pipeline's angles" and "the
//   line through a parabola is its tangent at the middle sample" fail.
// - An angle typed in the text for its `data-fig`: "has no digit typed in the prose" fails.
// - The sweep's match range printed from its first row only: "the sweep of v_h's window" fails
//   (task 162).

const F: Record<string, unknown> = entryFigures(ENTRY, ENTRY_RUN, ENTRY_MATCHES, HOOK.g_data);
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));
const C: EntryConstants = ENTRY;

describe("the check's arithmetic", () => {
  it("rounds a half to the even integer, as Python does, and takes Python's median", () => {
    expect([0.5, 1.5, 2.5, 3.5, -2.5, 2.4, 2.6].map(roundHalfEven)).toEqual([0, 2, 2, 4, -2, 2, 3]);
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 3, 2])).toBe(2.5);
  });

  it("the line through a parabola is its tangent at the middle sample", () => {
    const t = Array.from({ length: 7 }, (_, i) => i / 25);
    const z = t.map((v) => 4 + 2 * v - 4.9 * v * v);
    expect(lsSlope(t, z)).toBeCloseTo(2 - 9.8 * t[3], 12);
  });

  it("on a perfect flight the required angle is the arrival's and the reported one is three frames early", () => {
    const vh = 5;
    const run: Sample[] = Array.from({ length: 40 }, (_, i) => ({ t: i / 25, x: 7 + vh * (i / 25), y: 0, z: 0 }));
    const rimX = 12; // 5 m from the first sample: T = 1 s, k = 25
    const f0 = flight(run, C, rimX);
    const perfect = perfectRun(run, f0, C);
    const f = flight(perfect, C, rimX);
    expect(f.k).toBe(25);
    expect(perfect[25].z).toBeCloseTo(C.rim_height, 9);
    const vz = (t: number) => f.vz0 - C.g * t;
    expect(f.required).toBeCloseTo((Math.atan2(Math.abs(vz(1)), vh) * 180) / Math.PI, 9);
    expect(f.reported).toBeCloseTo((Math.atan2(Math.abs(vz(22 / 25)), vh) * 180) / Math.PI, 9);
    expect(f.gap).toBeGreaterThan(3);
  });
});

describe("the example against entry.json", () => {
  it("gives the pipeline's angles from the published samples, to the decimals it publishes", () => {
    const f = flight(ENTRY_RUN, C, ENTRY.example.rim_x);
    const p = ENTRY.example.published;
    const at4 = (x: number) => Number(x.toFixed(4));
    expect([at4(f.vH), at4(f.d), at4(f.T), f.k, at4(f.reported), at4(f.required)]).toEqual([p.v_h, p.d, p.t, p.k, p.reported, p.required]);
  });

  it("is the first lesson's hook, and its run starts the check's offset after the release", () => {
    expect(ENTRY.example.shot_id).toBe(HOOK.shot_id);
    expect(ENTRY.example.start_frame).toBe(HOOK.start_frame);
    expect(ENTRY_SAMPLES.length - ENTRY_RUN.length).toBe(ENTRY.search_offset);
    expect(ENTRY_RUN.length).toBeGreaterThan(ENTRY.example.published.k);
  });

  it("neither of the first lesson's scales closes the gap, and the method's own gap is part of it", () => {
    const f = F as Record<string, number>;
    expect(f.method_gap).toBeGreaterThan(0);
    expect(f.method_gap).toBeLessThan(f.ex_gap);
    expect(f.low_g_gap).toBeGreaterThan(0);
    expect(f.scaled_gap).toBeGreaterThan(0);
    expect(f.ex_closest_after).toBeGreaterThan(0);
  });

  it("the sweep of v_h's window: its ranges are its rows', and at the check's own window it is the table", () => {
    const s = ENTRY.v_h_sweep;
    const ex = s.example_gaps.map((r) => r[2]);
    expect([s.example_gap_lo, s.example_gap_hi]).toEqual([Math.min(...ex), Math.max(...ex)]);
    const ends = s.match_gap_medians.flatMap((r) => [r[2], r[3]]);
    expect([s.match_gap_median_lo, s.match_gap_median_hi]).toEqual([Math.min(...ends), Math.max(...ends)]);
    const own = s.match_gap_medians.find((r) => r[0] === ENTRY.v_h_frames && r[1] === ENTRY.search_offset);
    expect(own?.slice(2)).toEqual([F.gap_lo, F.gap_hi]);
    const shown = (name: string) => HTML.match(new RegExp(`data-fig="${name}">([^<]*)<`))?.[1];
    expect(shown("entry.v_h_sweep.match_gap_median_lo")).toBe(String(s.match_gap_median_lo));
    expect(shown("entry.v_h_sweep.match_gap_median_hi")).toBe(String(s.match_gap_median_hi));
  });

  it("the figure opens at standard gravity and the file's heights", () => {
    const markup = html(EntryFigure, {
      samples: ENTRY_SAMPLES,
      offset: ENTRY.search_offset,
      constants: C,
      rimX: ENTRY.example.rim_x,
      hookG: HOOK.g_data,
      heightScale: F.height_scale as number,
    });
    const cell = (name: string) => markup.match(new RegExp(`data-fig="${name}">([^<]*)<`))?.[1];
    expect(cell("learn.entry.g")).toBe(String(ENTRY.g));
    expect(cell("learn.entry.scale")).toBe("1");
    expect(cell("learn.entry.required")).toBe(String(Number(ENTRY.example.published.required.toFixed(2))));
  });
});

// The text as the server renders it.
const SCRIPT = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "entry.py"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { script: SCRIPT }));
const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (h: string, tags: string[]) => tags.reduce((acc, tag) => acc.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), h);
const text = (h: string) => entities(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const PROSE = text(drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]));
const source = (name: string): unknown =>
  name.startsWith("learn.")
    ? name
        .slice(6)
        .split(".")
        .reduce<unknown>((o, k) => (o as Record<string, unknown>)?.[k], F)
    : name.startsWith("entry.")
      ? figureAt(ENTRY, "entry", name)
      : qualityFigure(QUALITY, name);

describe("the text of lesson 8", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(80);
    const wrong = figs.filter(([name, shown]) => {
      // The figure's readouts live in its state; "the figure opens at ..." checks them.
      if (name.startsWith("learn.entry.")) return false;
      const value = source(name);
      return value === undefined || shown !== display(String(value), name);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,30}\d+.{0,30}/g)).toBeNull();
  });

  it("has none of the fence's forbidden keys or watched words outside a quote or a citation", () => {
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    const watched = ["straight line at constant speed", "time to impact", "second difference", "straight line", "football"];
    expect(watched.filter((w) => outside.includes(w))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
  });

  it("is between 1,300 and 2,300 words: its figures counted, its formulas, script and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 8: ${words} words`);
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
  it("every stroke and fill the entry figure and the table render is 3:1 or more on the canvas", () => {
    const markups = [
      html(EntryFigure, { samples: ENTRY_SAMPLES, offset: ENTRY.search_offset, constants: C, rimX: ENTRY.example.rim_x, hookG: HOOK.g_data, heightScale: 1.2 }),
      html(PerMatch, { matches: ENTRY_MATCHES }),
    ];
    const colours = new Set(markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none"));
    expect(colours.size).toBeGreaterThan(3);
    expect([...colours].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3)).toEqual([]);
  });
});
