import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ClockFit } from "../components/learn/clock/ClockFit";
import { Lesson } from "../components/learn/clock/Lesson";
import { PerMatch } from "../components/learn/clock/PerMatch";
import { CANVAS } from "../components/learn/gravity/Plot";
import { firstMove, fitLine, gInSeconds, lineAt, residuals, slopeForG } from "../lib/learn/clock";
import { CLOCK, CLOCK_EXAMPLES } from "../lib/learn/clock-data";
import { clockFigures, fitFrom, flagRuns, moves } from "../lib/learn/clock-figures";
import { display } from "../lib/learn/display";
import fence from "../lib/learn/fence.json";
import { qualityFigure } from "../lib/learn/gravity-data";
import { figureAt } from "../lib/learn/json-figure";
import { HOOK, QUALITY } from "../lib/quality";

// Lesson 6: the arithmetic of lib/learn/clock.ts, the two possessions against clock.json, then the
// text as the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - `fitLine` returning the intercept at t = 0 instead of the clock at the mean time: "passes
//   through the means" fails, and so does the line drawn in the figure.
// - `fitLine` through the origin with the textbook sums: "keeps its digits at an hour" fails.
// - `firstMove` returning the first moved sample instead of the last held one: "the control
//   clock holds after the flag" fails (its fit from the move is no longer -1 with no residual).
// - A slope typed in the text for its `data-fig`: "has no digit typed in the prose" fails.

const F: Record<string, unknown> = clockFigures(CLOCK, CLOCK_EXAMPLES, HOOK.g_data, HOOK.g_real);
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));
const CAL = CLOCK_EXAMPLES.find((e) => e.key === "calibration")!;
const CTL = CLOCK_EXAMPLES.find((e) => e.key === "control")!;

describe("a line through two clocks", () => {
  it("recovers an exact line and passes through the means", () => {
    const t = Array.from({ length: 50 }, (_, i) => 10 + i / 25);
    const y = t.map((v) => 600 - 0.998 * v);
    const fit = fitLine(t, y);
    expect(fit.slope).toBeCloseTo(-0.998, 12);
    expect(fit.tMean).toBeCloseTo(10 + 49 / 50, 12);
    expect(fit.atMean).toBeCloseTo(600 - 0.998 * fit.tMean, 9);
    expect(lineAt(fit, 10)).toBeCloseTo(600 - 9.98, 9);
    expect(Math.max(...residuals(t, y, fit).map(Math.abs))).toBeLessThan(1e-9);
  });

  it("keeps its digits at an hour of video", () => {
    const t = Array.from({ length: 200 }, (_, i) => 3600 + i / 25);
    const y = t.map((v) => 600 - 0.999 * (v - 3600));
    expect(Math.abs(fitLine(t, y).slope + 0.999)).toBeLessThan(1e-12);
  });

  it("finds the last held sample, and the scale a g needs", () => {
    expect(firstMove([5, 5, 5, 4.96, 4.92])).toBe(2);
    expect(firstMove([5, 5, 5, 4.96], 1)).toBe(2);
    expect(slopeForG(9.80665 * 0.81, 9.80665)).toBeCloseTo(-0.9, 12);
    expect(gInSeconds(8, 0.5)).toBe(32);
  });
});

describe("the two possessions against clock.json", () => {
  it("the calibration possession never stops and its clock runs true to the file's rounding", () => {
    expect(CAL.stopped).toEqual([]);
    expect(flagRuns(CAL)).toBe(0);
    expect(Math.abs((F.cal_slope as number) + 1)).toBeLessThan(0.0001);
    expect(F.cal_rms_ms as number).toBeLessThan(F.half_unit_ms as number);
  });

  it("the control clock holds after the flag says it runs, then runs true", () => {
    expect(CTL.stopped).toHaveLength(1);
    expect(moves(CTL)).toBeGreaterThan(flagRuns(CTL));
    expect(CTL.clock[moves(CTL)]).toBe(CTL.clock[flagRuns(CTL)]);
    expect(CTL.clock[moves(CTL) + 1]).not.toBe(CTL.clock[flagRuns(CTL)]);
    expect(fitFrom(CTL, moves(CTL)).fit.slope).toBeCloseTo(-1, 9);
    expect(F.ctl_slope_all as number).toBeGreaterThan(F.ctl_slope_flag as number);
  });

  it("the medians split by the quality checks' flag, and only control matches hold", () => {
    const f = F as Record<string, number>;
    expect(f.cal_n + f.ctl_n).toBe(CLOCK.matches.length);
    expect(f.cal_held).toBe(0);
    expect(CLOCK.matches.filter((m) => !m.calibration).every((m) => m.held > 0)).toBe(true);
    expect(f.ctl_g_pct).toBeLessThan(f.need_g_pct);
  });

  it("the figure opens on the calibration possession, every frame fitted", () => {
    const markup = html(ClockFit, { examples: CLOCK_EXAMPLES, halfUnitMs: F.half_unit_ms as number });
    const cell = (path: string) => markup.match(new RegExp(`data-fig="${path}">([^<]*)<`))?.[1];
    expect(cell("learn.fit.slope")).toBe(String(F.cal_slope));
    expect(cell("learn.fit.frames")).toBe(String(F.cal_frames));
    expect(cell("learn.fit.rms_ms")).toBe(String(F.cal_rms_ms));
  });
});

// The text as the server renders it.
const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "clock.sql"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { sql: SQL }));
const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (h: string, tags: string[]) => tags.reduce((acc, tag) => acc.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), h);
const text = (h: string) => entities(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const PROSE = text(drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]));

const source = (path: string): unknown =>
  path.startsWith("learn.")
    ? path
        .slice(6)
        .split(".")
        .reduce<unknown>((o, k) => (o as Record<string, unknown>)?.[k], F)
    : path.startsWith("clock.")
      ? figureAt(CLOCK, "clock", path)
      : qualityFigure(QUALITY, path);

describe("the text of lesson 6", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(80);
    const wrong = figs.filter(([path, shown]) => {
      // The figure's readouts live in its state; "the figure opens on ..." checks them.
      if (path.startsWith("learn.fit.")) return false;
      const value = source(path);
      return value === undefined || shown !== display(String(value), path);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,30}\d+.{0,30}/g)).toBeNull();
  });

  it("has none of the fence's forbidden keys or watched words outside a quote or a citation", () => {
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    const watched = ["time to impact", "second difference", "straight line", "constant speed", "detected"];
    expect(watched.filter((w) => outside.includes(w))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
  });

  it("is between 1,300 and 2,300 words: its figures counted, its formulas, query and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 6: ${words} words`);
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
  it("every stroke and fill the clock figure and the table render is 3:1 or more on the canvas", () => {
    const markups = [html(ClockFit, { examples: CLOCK_EXAMPLES, halfUnitMs: 5 }), html(PerMatch, { matches: CLOCK.matches, held: F.held_pct as Record<string, number> })];
    const colours = new Set(markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none"));
    expect(colours.size).toBeGreaterThan(3);
    expect([...colours].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3)).toEqual([]);
  });
});
