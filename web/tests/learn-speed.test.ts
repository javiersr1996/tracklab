import { display } from "../lib/learn/display";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Lesson } from "../components/learn/speed/Lesson";
import fence from "../lib/learn/fence.json";
import { qualityFigure } from "../lib/learn/gravity-data";
import { SOURCES } from "../lib/learn/sources";
import {
  differenceWeights,
  estimate,
  gapTo,
  median,
  movingAverage,
  parabolaPath,
  roundingBound,
  savitzkyGolay,
  smoothed,
} from "../lib/learn/speed";
import { SPEED, SPEED_EXAMPLE, speedExample, speedFigure } from "../lib/learn/speed-data";
import { speedFigures } from "../lib/learn/speed-figures";
import { QUALITY } from "../lib/quality";
import possession from "../public/data/possessions/bb_possessions_possession-114099-1-41.json";

// Lesson 2: the arithmetic of lib/learn/speed.ts, then the text as the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - `smoothed` without its `/ k`: "a moving average of differences is one longer difference" fails.
// - `savitzkyGolay` keeping the slope (`solve(a, b)[1]`): "order one is a moving average" fails.
// - `difference` with `span = after * h`: "the central difference is exact on a parabola" fails.
// - `roundingBound` without the half unit: "the rounding bound" fails.
// - A median typed in the text for its `data-fig`: "prints every data-fig" fails.

const H = 1 / 25;
const near = (a: number, b: number, eps = 1e-9) => Math.abs(a - b) < eps;

// A seeded uniform generator, so the random series are the same on every run.
function lcg(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 2 ** 32);
}

describe("finite differences", () => {
  it("the central difference is exact on a parabola; the forward one is off by a·h/2", () => {
    const a = 3;
    const x = parabolaPath(a, H, 26);
    const y = x.map(() => 0);
    const truth = x.map((_, i) => a * i * H);
    expect(gapTo(truth, estimate(x, y, differenceWeights("central", H))).max).toBeLessThan(1e-12);
    const forward = gapTo(truth, estimate(x, y, differenceWeights("forward", H)));
    expect(near(forward.median, (a * H) / 2)).toBe(true);
    expect(near(forward.max, (a * H) / 2)).toBe(true);
  });

  it("a moving average of differences is one longer difference", () => {
    const w = smoothed(differenceWeights("central", H), 3);
    expect([...w.keys()]).toEqual([-2, -1, 1, 2]);
    expect([...w.values()].every((v, i) => near(v, (i < 2 ? -1 : 1) / (6 * H)))).toBe(true);
    const shaw = smoothed(differenceWeights("backward", H), 7);
    expect([...shaw.keys()]).toEqual([-4, 3]);
    expect(near(shaw.get(3) ?? 0, 1 / (7 * H))).toBe(true);
  });

  it("a moving average of k differences equals the average of the k estimates, axis by axis", () => {
    const rnd = lcg(7);
    const x = Array.from({ length: 40 }, () => rnd());
    const flat = x.map(() => 0);
    const vx = (i: number) => (x[i + 1] - x[i - 1]) / (2 * H);
    const avg = (i: number) => (vx(i - 1) + vx(i) + vx(i + 1)) / 3;
    const est = estimate(x, flat, smoothed(differenceWeights("central", H), 3));
    for (let i = 2; i < 38; i++) expect(near(est[i] ?? NaN, Math.abs(avg(i)), 1e-9)).toBe(true);
    expect(est[1]).toBeNull();
  });

  it("the rounding bound is half a unit times the sum of the weights", () => {
    expect(near(roundingBound(differenceWeights("central", H), 0.01), 0.01 / (2 * H))).toBe(true);
    expect(near(roundingBound(differenceWeights("forward", H), 0.01), 0.01 / H)).toBe(true);
    // At 1 cm the example's gap can exceed the file's own only by what the rounding adds.
    const w = differenceWeights("central", SPEED_EXAMPLE.h);
    const at1cm = gapTo(SPEED_EXAMPLE.speed, estimate(SPEED_EXAMPLE.x, SPEED_EXAMPLE.y, w));
    expect(at1cm.frames).toBe(SPEED.example.full_precision.frames);
    expect(at1cm.max).toBeLessThanOrEqual(SPEED.example.full_precision.max_gap + Math.SQRT2 * roundingBound(w, SPEED_EXAMPLE.resolution) + 5e-4);
  });
});

describe("Savitzky-Golay", () => {
  it("of order one is a moving average; of order two it is not", () => {
    const rnd = lcg(42);
    const v = Array.from({ length: 50 }, () => rnd() * 4);
    const sg1 = savitzkyGolay(v, 7, 1);
    const ma = movingAverage(v, 7);
    expect(sg1.every((s, i) => (s === null ? ma[i] === null : near(s, ma[i] ?? NaN, 1e-9)))).toBe(true);
    const sg2 = savitzkyGolay(v, 7, 2);
    expect(sg2.some((s, i) => s !== null && !near(s, ma[i] ?? NaN, 1e-6))).toBe(true);
  });

  it("of order two keeps a parabola", () => {
    const p = Array.from({ length: 20 }, (_, i) => 1 + 2 * i - 0.5 * i * i);
    expect(savitzkyGolay(p, 5, 2).every((s, i) => s === null || near(s, p[i], 1e-9))).toBe(true);
  });
});

describe("the example", () => {
  it("is the published possession's player, frame by frame, with the file's speeds", () => {
    expect(SPEED_EXAMPLE.x).toHaveLength(SPEED.example.frames);
    expect(SPEED_EXAMPLE.speed).toEqual(SPEED.example.speed);
    expect(median([3, 1, 2])).toBe(2);
  });

  it("refuses a possession that does not line up", () => {
    const shifted = { ...possession, frames: possession.frames.slice(1) };
    expect(() => speedExample(SPEED, shifted as never)).toThrow();
    expect(() => speedExample({ ...SPEED, example: { ...SPEED.example, entity_id: "bb:0" } }, possession as never)).toThrow();
  });
});

// The text.
const sqlOf = (name: string) => readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", name), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { sql: sqlOf("speed.sql") }));
const FIGURES: Record<string, unknown> = speedFigures(SPEED_EXAMPLE, SPEED);

const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (html: string, tags: string[]) =>
  tags.reduce((h, tag) => h.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), html);
const text = (html: string) => entities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const PROSE = text(
  drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]),
);

describe("the text of lesson 2", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(100);
    const wrong = figs.filter(([path, shown]) => {
      if (path.startsWith("learn.trace.")) return false; // the figure's state; the e2e reads it
      const value = path.startsWith("learn.")
        ? FIGURES[path.slice(6)]
        : path.startsWith("speed.")
          ? speedFigure(SPEED, path)
          : qualityFigure(QUALITY, path);
      return value === undefined || shown !== display(String(value), path);
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
    for (const word of ["wrong", "bug", "true speed", "real speed", "second difference", "straight line", "prederror"]) {
      expect(outside.includes(word), word).toBe(false);
    }
  });

  // That every source is cited by some lesson is checked across the series in learn-lesson.test.ts.
  it("cites only sources.ts", () => {
    const urls = Object.values(SOURCES).map((s) => s.url);
    const hrefs = [...HTML.matchAll(/<cite><a href="([^"]+)"/g)].map((m) => entities(m[1]));
    expect(hrefs.filter((h) => !urls.includes(h))).toEqual([]);
  });

  // Against the provider's dictionary where the clone is on disk; CI has no clone and skips.
  const receiptPath = join(process.cwd(), "..", "pipeline", "data", "raw", "opendata-basketball", "_receipt.json");
  const receipt = existsSync(receiptPath) ? (JSON.parse(readFileSync(receiptPath, "utf-8")) as { source_path: string }) : null;
  const dictionary = receipt ? join(receipt.source_path, "docs", "data_dictionary", "tracking_data.md") : "";
  it.skipIf(!receipt || !existsSync(dictionary))("quotes the provider's definition of speed word for word", () => {
    const line30 = readFileSync(dictionary, "utf-8").split("\n")[29];
    expect(line30.startsWith("| `speed` |")).toBe(true);
    expect(line30).toContain(SOURCES["skillcorner-speed"].quote);
  });

  it("is between 1,500 and 2,300 words: its figures counted, its formulas, query and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 2: ${words} words`);
    expect(words).toBeGreaterThanOrEqual(1500);
    expect(words).toBeLessThanOrEqual(2300);
  });
});
