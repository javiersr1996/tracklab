import { display } from "../lib/learn/display";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Lesson } from "../components/learn/cadence/Lesson";
import { LagPlot } from "../components/learn/cadence/LagPlot";
import { NoiseCloud } from "../components/learn/cadence/NoiseCloud";
import { PerPlayer } from "../components/learn/cadence/PerPlayer";
import { CANVAS, INK } from "../components/learn/gravity/Plot";
import { autocorrelation, cadenceHz, firstPeak, linearSd, monteCarlo, sd, signalSd } from "../lib/learn/cadence";
import { column, FAST_ROWS, fastRows, HOOKS, POSE, publishedFigure } from "../lib/learn/cadence-data";
import { cadenceFigures } from "../lib/learn/cadence-figures";
import fence from "../lib/learn/fence.json";
import { mulberry32, gaussian } from "../lib/learn/gravity";
import { SOURCES } from "../lib/learn/sources";
import type { PoseSummary } from "../lib/pose/types";

// Lesson 5: the arithmetic in `cadence.ts`, the slice of `pose.json` in `cadence-data.ts`, and
// the text as the server renders it.
//
// Mutations checked by hand, each restored:
// - `cadenceHz` without the factor two: "recovers a planted cadence" fails (half of it).
// - `firstPeak` with `shift` forced to 0: "recovers a planted cadence" fails (whole lags only).
// - `cadenceHz` reading every peak, the band's test removed: "white noise has no cadence" fails.
// - `linearSd` with `h` left out of the central difference: "first order meets Monte Carlo" fails.
// - `fastRows` without the floor on windows: "every player over the floor" fails (more rows than M1).
// - "a cadence of 3.56 steps/s" typed in the text: "no digit is typed" fails.

const fps = 25;
const sine = (f: number, n: number, phase = 0.3) => Array.from({ length: n }, (_, i) => Math.sin(2 * Math.PI * f * (i / fps) + phase));
const [A, B] = HOOKS;

describe("cadence.ts", () => {
  // Whole lags miss these by 0.046 to 0.075 steps/s; the parabola brings each within 0.025.
  it("recovers a planted cadence closer than whole lags can", () => {
    for (const steps of [3.2, 3.8, 4.1]) {
      expect(Math.abs(cadenceHz(sine(steps / 2, 50), fps) - steps)).toBeLessThan(0.025);
    }
  });

  it("finds the first peak after the autocorrelation turns negative, at the period in frames", () => {
    const p = firstPeak(autocorrelation(sine(1.25, 50)));
    expect(p?.k).toBe(20);
    expect(p?.resolved).toBe(true);
  });

  it("gives white noise no cadence most of the time", () => {
    const rng = mulberry32(3);
    const noise = Array.from({ length: 200 }, () => Array.from({ length: 50 }, () => gaussian(rng)));
    expect(noise.filter((s) => Number.isFinite(cadenceHz(s, fps))).length).toBeLessThan(40);
  });

  it("adds the two ankles' variances", () => {
    const [a, b] = signalSd([0.03, 0.12], [0.04, 0.05]);
    expect(a).toBeCloseTo(0.05, 12);
    expect(b).toBeCloseTo(0.13, 12);
  });

  it("first order meets Monte Carlo when the noise is small", () => {
    const s = sine(1.8, 50);
    const sigma = s.map(() => 0.01);
    const mc = monteCarlo(s, sigma, fps, 400, 5).filter(Number.isFinite);
    expect(mc).toHaveLength(400);
    expect(Math.abs(sd(mc) / linearSd(s, sigma, fps) - 1)).toBeLessThan(0.15);
  });

  it("draws the same copies for the same seed, and a longer run starts with them", () => {
    const s = sine(1.8, 50);
    const sigma = s.map(() => 0.2);
    const short = monteCarlo(s, sigma, fps, 20, 59);
    expect(monteCarlo(s, sigma, fps, 40, 59).slice(0, 20)).toEqual(short);
  });

  it("reads the published windows' cadence from their s(t), to the rounding of the millimetre", () => {
    for (const h of HOOKS) {
      expect(Math.abs(cadenceHz(h.s_m, h.fps) - h.cadence_hz)).toBeLessThan(0.001);
      expect(Math.abs(cadenceHz(h.joints_s_m, h.fps) - h.cadence_hz)).toBeLessThan(0.01);
    }
  });
});

describe("cadence-data.ts", () => {
  it("builds s(t) from the clip's joints within their centimetre of the published s(t)", () => {
    for (const h of HOOKS) {
      expect(h.joints_s_m).toHaveLength(h.s_m.length);
      expect(Math.max(...h.joints_s_m.map((v, i) => Math.abs(v - h.s_m[i])))).toBeLessThan(0.015);
      expect(Math.min(...h.sigma_m)).toBeGreaterThan(0);
    }
    expect([A.match_id, B.match_id]).toEqual([POSE.protocol.calibration, POSE.protocol.confirmation]);
  });

  it("every player over the floor, as many as the verdict counted, in the file's order", () => {
    const verdict = POSE.verdict as unknown as { calibration: { m1_players: number }; confirmation: { m4: { m1_players: number } } };
    expect(FAST_ROWS[String(A.match_id)]).toHaveLength(verdict.calibration.m1_players);
    expect(FAST_ROWS[String(B.match_id)]).toHaveLength(verdict.confirmation.m4.m1_players);
    for (const rows of Object.values(FAST_ROWS)) {
      expect(rows.map((r) => r.row)).toEqual([...rows.map((r) => r.row)].sort((x, y) => x - y));
    }
  });

  it("takes each value from the file, so a mutated file shows the mutation", () => {
    const tables = POSE.tables!;
    const i = FAST_ROWS[String(A.match_id)][0].row;
    const mutated = structuredClone(POSE) as PoseSummary;
    mutated.tables!.matches[String(A.match_id)][i][column("cad_s_p50_hz")] = 1.2345;
    expect(fastRows(mutated)[String(A.match_id)][0].cadence_hz).toBe(1.2345);
    expect(tables.matches[String(A.match_id)][i][column("cad_s_p50_hz")]).not.toBe(1.2345);
  });
});

// ---------------------------------------------------------------------------------------------
// The text.
// ---------------------------------------------------------------------------------------------
const SCRIPT = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "cadence.py"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { script: SCRIPT }));
const FIGURES = cadenceFigures(HOOKS, FAST_ROWS) as unknown as Record<string, unknown>;

const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (html: string, tags: string[]) =>
  tags.reduce((h, tag) => h.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), html);
const text = (html: string) => entities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const PROSE = text(
  drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]),
);
const at = (root: unknown, path: string) => path.split(".").reduce<unknown>((o, k) => (o as Record<string, unknown> | undefined)?.[k], root);

describe("the text of lesson 5", () => {
  it("prints every data-fig as its file or the lesson's arithmetic has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(80);
    const wrong = figs.filter(([name, shown]) => {
      // The figures' own readouts (`learn.lag.k`, ...) live in their state; checked below.
      if (/^learn\.(lag|noise|player)\./.test(name)) return false;
      const value = name.startsWith("learn.") ? at(FIGURES, name.slice(6)) : publishedFigure(name);
      return value === undefined || shown !== display(String(value), name);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,20}\d+.{0,20}/g)).toBeNull();
  });

  it("has none of the fence's forbidden keys outside a quote or a citation, and no held-out id", () => {
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
    for (const phrase of ["second difference", "straight line", "pressure", "pressing", "defensive line"]) expect(outside).not.toContain(phrase);
  });

  // That every source is cited by some lesson is checked across the series in learn-lesson.test.ts.
  it("cites only sources.ts", () => {
    const urls = Object.values(SOURCES).map((s) => s.url);
    const hrefs = [...HTML.matchAll(/<cite><a href="([^"]+)"/g)].map((m) => entities(m[1]));
    expect(hrefs.filter((h) => !urls.includes(h))).toEqual([]);
  });

  it("quotes every source it cites with a quote, word for word as sources.ts has it", () => {
    const quotes = [...HTML.matchAll(/<q>([\s\S]*?)<\/q>/g)].map((m) => text(m[1]));
    for (const id of ["skillcorner-bodypose", "nist-autocorrelation", "smith-parabola", "nist-propagation", "jcgm-101"]) {
      expect(quotes).toContain(SOURCES[id].quote);
    }
  });

  it("shows the script it was checked with", () => {
    expect(text(HTML)).toContain("def cadence(s: list[float], fps: float) -> float:");
  });

  it("is between 1,500 and 2,300 words: its figures counted, its formulas, script and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 5: ${words} words`);
    expect(words).toBeGreaterThanOrEqual(1500);
    expect(words).toBeLessThanOrEqual(2300);
  });
});

// ---------------------------------------------------------------------------------------------
// The figures.
// ---------------------------------------------------------------------------------------------
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
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));
const COLUMNS = { team_id: column("team_id"), number: column("number"), finite_s: column("finite_s"), cad_s_p50_hz: column("cad_s_p50_hz"), cad_s_sd_hz: column("cad_s_sd_hz") };

describe("the figures of lesson 5", () => {
  const markups = [html(LagPlot, { hook: A }), html(NoiseCloud, { hook: A }), html(PerPlayer, { rows: FAST_ROWS, columns: COLUMNS })];

  it("draw every stroke and fill at 3:1 or more on the canvas, in lesson 1's inks", () => {
    const colours = markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none");
    expect(new Set(colours)).toEqual(new Set(Object.values(INK)));
    expect([...new Set(colours)].filter((c) => contrast(c, CANVAS) < 3)).toEqual([]);
  });

  it("open on the first peak, with no noisy copy, on the first match's first player", () => {
    const cell = (m: string, name: string) => m.match(new RegExp(`data-fig="${name.replace(/\./g, "\\.")}">([^<]*)<`))?.[1];
    expect(cell(markups[0], "learn.lag.k")).toBe(String(firstPeak(autocorrelation(A.s_m))?.k));
    expect(markups[1]).toContain('data-draws="0"');
    const first = FAST_ROWS[String(A.match_id)][0];
    const path = `pose.json:tables.matches.${A.match_id}.${first.row}.${column("cad_s_p50_hz")}`;
    expect(cell(markups[2], path)).toBe(String(publishedFigure(path)));
  });
});
