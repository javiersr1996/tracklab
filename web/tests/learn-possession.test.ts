import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CANVAS } from "../components/learn/gravity/Plot";
import { Lesson } from "../components/learn/possession/Lesson";
import { PerMatch } from "../components/learn/possession/PerMatch";
import { Timeline } from "../components/learn/possession/Timeline";
import { display } from "../lib/learn/display";
import fence from "../lib/learn/fence.json";
import { figureAt } from "../lib/learn/json-figure";
import { expRatio, expSurvival, quantile, survival } from "../lib/learn/possession";
import { durations, POSSESSION, spells } from "../lib/learn/possession-data";
import { lessonPossessionFigures } from "../lib/learn/possession-figures";

// Lesson 10: the arithmetic of lib/learn/possession.ts, the timelines against possession.json's
// rows, the fence, then the text as the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - `quantile` at position n·q instead of (n − 1)·q: "interpolates as quantile_cont" fails, and so
//   does "each timeline gives its match's row".
// - `survival` counting durations equal to t: "is the share strictly longer" fails.
// - `expSurvival` with e for 2: "halves every median" fails.
// - `spells` reading the team's column as the phases: "each timeline gives its match's row"
//   fails (the share over more than one phase).
// - A median typed in the text for its `data-fig`: "has no digit typed in the prose" fails.

const F = lessonPossessionFigures(POSSESSION);
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));
const TIMELINES = { football: POSSESSION.football.timeline, basketball: POSSESSION.basketball.timeline };

describe("durations as a distribution", () => {
  it("interpolates as quantile_cont: position (n − 1)·q in the sorted values", () => {
    expect(quantile([4, 1, 3, 2], 0.5)).toBe(2.5);
    expect(quantile([1, 2, 3, 4], 0.9)).toBeCloseTo(3.7, 12);
    expect(quantile([7], 0.9)).toBe(7);
  });

  it("is the share strictly longer than t", () => {
    expect(survival([1, 2, 3, 4], 2)).toBe(0.5);
    expect(survival([1, 2, 3, 4], 0)).toBe(1);
    expect(survival([1, 2, 3, 4], 4)).toBe(0);
  });

  it("the exponential halves every median, and its ninetieth percentile is log2 10 medians", () => {
    expect(expSurvival(12, 12)).toBe(0.5);
    expect(expSurvival(12, 24)).toBe(0.25);
    expect(expRatio(0.9)).toBeCloseTo(Math.log2(10), 12);
    // A sample drawn at its own quantiles: its p90 over its median comes out at the same ratio.
    const m = 9;
    const sample = Array.from({ length: 20001 }, (_, i) => (-m / Math.LN2) * Math.log(1 - (i + 0.5) / 20001));
    expect(quantile(sample, 0.9) / quantile(sample, 0.5)).toBeCloseTo(expRatio(0.9), 2);
  });
});

describe("the timelines against possession.json", () => {
  it("each timeline gives its match's row of the table", () => {
    const fb = POSSESSION.football.matches.find((m) => m.match_id === TIMELINES.football.match_id)!;
    const s = spells(TIMELINES.football);
    const d = durations(s);
    expect(d).toHaveLength(fb.runs);
    expect(Math.abs(quantile(d, 0.5) - fb.run_median_s)).toBeLessThan(5e-5);
    expect(Math.abs(quantile(d, 0.9) - fb.run_p90_s)).toBeLessThan(5e-5);
    expect(Number(((100 * s.filter((x) => x.phases > 1).length) / s.length).toFixed(2))).toBe(fb.multi_phase_pct);
    const bb = POSSESSION.basketball.matches.find((m) => m.match_id === TIMELINES.basketball.match_id)!;
    const e = durations(spells(TIMELINES.basketball));
    expect(e).toHaveLength(bb.possessions);
    expect(Math.abs(quantile(e, 0.5) - bb.median_s)).toBeLessThan(5e-5);
    expect(Math.abs(quantile(e, 0.9) - bb.p90_s)).toBeLessThan(5e-5);
  });

  it("the runs of a period follow one another and alternate teams", () => {
    const s = spells(TIMELINES.football);
    for (let i = 1; i < s.length; i++) {
      if (s[i].period !== s[i - 1].period) continue;
      expect(s[i].start).toBeGreaterThanOrEqual(s[i - 1].end);
      expect(s[i].team).not.toBe(s[i - 1].team);
    }
  });

  it("keeps the fence: ten football matches, none held out", () => {
    const ids = POSSESSION.football.matches.map((m) => m.match_id.replace(/^fb:/, ""));
    expect(ids).toHaveLength(10);
    expect(fence.held_out.filter((h) => ids.includes(h))).toEqual([]);
    const file = readFileSync(join(process.cwd(), "public", "data", "learn", "possession.json"), "utf-8");
    expect(fence.held_out.filter((h) => file.includes(h))).toEqual([]);
  });

  it("the figure opens on football", () => {
    const markup = html(Timeline, { timelines: TIMELINES });
    const cell = (name: string) => markup.match(new RegExp(`data-fig="${name}">([^<]*)<`))?.[1];
    expect(cell("learn.timeline.n")).toBe(String(F.fb.n));
    expect(cell("learn.timeline.median")).toBe(String(F.fb.median));
    expect(cell("learn.timeline.beyond2_pct")).toBe(String(F.fb.beyond2_pct));
  });
});

// The text as the server renders it.
const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "possession.sql"), "utf-8");
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
    : figureAt(POSSESSION, "possession", name);

describe("the text of lesson 10", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(100);
    const wrong = figs.filter(([name, shown]) => {
      // The figure's readouts live in its state; "the figure opens on football" checks them.
      if (name.startsWith("learn.timeline.")) return false;
      const value = source(name);
      return value === undefined || shown !== display(String(value), name);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,30}\d+.{0,30}/g)).toBeNull();
  });

  it("keeps the fence: no forbidden key outside a quote, no held-out id, no team shape, no outcome", () => {
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    expect(["detected", "width", "length", "pressure", "press", "goal", "shot", "score"].filter((w) => outside.includes(w))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
  });

  it("is between 1,300 and 2,300 words: its figures counted, its formulas, query and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 10: ${words} words`);
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
  it("every stroke and fill the timeline and the tables render is 3:1 or more on the canvas", () => {
    const markups = [
      html(Timeline, { timelines: TIMELINES }),
      html(PerMatch, { football: POSSESSION.football.matches, basketball: POSSESSION.basketball.matches, ratios: F }),
    ];
    const colours = new Set(markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none"));
    expect(colours.size).toBeGreaterThan(2);
    expect([...colours].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3)).toEqual([]);
  });
});
