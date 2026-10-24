import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FitPlot } from "../components/learn/gravity/FitPlot";
import { NoiseStrip } from "../components/learn/gravity/NoiseStrip";
import { PerMatch } from "../components/learn/gravity/PerMatch";
import { CANVAS, INK } from "../components/learn/gravity/Plot";
import { WindowPlot } from "../components/learn/gravity/WindowPlot";
import { shown } from "../lib/learn/expose";
import { apparentG } from "../lib/learn/gravity";
import { basketballGravity, GRAVITY_HOOK, GRAVITY_MATCHES, gravityFig, qualityFigure } from "../lib/learn/gravity-data";
import { CHECKS, QUALITY } from "../lib/quality";

// Lesson 1's figures (task 79), rendered to static markup as the server sends them.
//
// Mutations checked by hand, each restored byte for byte:
// - A median typed into `PerMatch` (`{"8.0837"}` for `r.g_median`): "shows the file's figure of a
//   mutated quality.json" fails on the mutated cell.
// - `INK.axis` at #596168 (--canvas-axis, 2.5:1): "every stroke and fill is 3:1" fails, and so does
//   a hex typed straight into one figure's stroke.
// - A `useEffect` starting a `requestAnimationFrame` loop at mount: no vitest can see it (effects do
//   not run on the server); the e2e of task 81 counts frames after load.

const G = GRAVITY_HOOK.g_real;
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));

const cell = (markup: string, path: string) => markup.match(new RegExp(`data-fig="${path}">([^<]*)<`))?.[1];

describe("PerMatch", () => {
  it("shows every per-match figure as the file has it, under the path that names it", () => {
    const markup = html(PerMatch, { matches: GRAVITY_MATCHES, g: G });
    const paths = [...markup.matchAll(/data-fig="(checks\.[^"]+)"/g)].map((m) => m[1]);
    expect(paths).toHaveLength(GRAVITY_MATCHES.length * 4);
    for (const p of paths) expect(cell(markup, p)).toBe(String(qualityFigure(QUALITY, p)));
  });

  it("shows the file's figure of a mutated quality.json, not one of its own", () => {
    const target = { match_id: "bb:114086", metric: "g_median" };
    const mutated = CHECKS.gravity.map((r) =>
      r.match_id === target.match_id && r.metric === target.metric ? { ...r, value: 1.2345 } : r,
    );
    const path = gravityFig(target.match_id, target.metric);
    expect(cell(html(PerMatch, { matches: GRAVITY_MATCHES, g: G }), path)).toBe(String(qualityFigure(QUALITY, path)));
    expect(cell(html(PerMatch, { matches: basketballGravity(mutated), g: G }), path)).toBe("1.2345");
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
  it("are drawn on the canvas globals.css defines", () => {
    const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf-8");
    expect(css.match(/--canvas:\s*(#[0-9a-f]{6})/i)?.[1].toLowerCase()).toBe(CANVAS);
  });

  it("every stroke and fill the four figures render is 3:1 or more on the canvas", () => {
    const markups = [
      html(FitPlot, { hook: GRAVITY_HOOK }),
      html(WindowPlot, { hook: GRAVITY_HOOK }),
      html(NoiseStrip, { hook: GRAVITY_HOOK }),
      html(PerMatch, { matches: GRAVITY_MATCHES, g: G }),
    ];
    const colours = markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none");
    expect(new Set(colours)).toEqual(new Set(Object.values(INK)));
    const low = [...new Set(colours)].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3);
    expect(low).toEqual([]);
  });
});

describe("the interactive figures", () => {
  it("open on the least-squares g and P3's whole window, with no noisy flight yet", () => {
    const fitted = shown(apparentG(GRAVITY_HOOK.t_s, GRAVITY_HOOK.z_data_m), 4);
    expect(cell(html(FitPlot, { hook: GRAVITY_HOOK }), "learn.fit.g")).toBe(String(fitted));
    expect(cell(html(WindowPlot, { hook: GRAVITY_HOOK }), "learn.window.h")).toBe(String((GRAVITY_HOOK.t_s.length - 1) / 2));
    expect(html(NoiseStrip, { hook: GRAVITY_HOOK })).not.toContain("<circle");
  });
});
