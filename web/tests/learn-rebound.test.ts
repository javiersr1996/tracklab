import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement, type FunctionComponent } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CANVAS } from "../components/learn/gravity/Plot";
import { Lesson } from "../components/learn/rebound/Lesson";
import { RaceFigure } from "../components/learn/rebound/RaceFigure";
import { ReactionPlot } from "../components/learn/rebound/ReactionPlot";
import fence from "../lib/learn/fence.json";
import { argmin, arrival, chanceFirst, nearest, type Runner } from "../lib/learn/rebound";
import { REBOUND, reboundFigure } from "../lib/learn/rebound-data";
import { raceAt, reboundFigures, SPEED_MAX, SPEED_MIN, SPEED_STEP, steps } from "../lib/learn/rebound-figures";

// Lesson 4: the arithmetic of lib/learn/rebound.ts against the pipeline's example, then the text
// as the server renders it.
//
// Mutations checked by hand, each restored byte for byte:
// - `arrival` without the velocity: "is the reaction plus what is left", "the times and chances
//   are the pipeline's" and "no reaction gives the nearest player; ..." fail.
// - `logisticScale` returning the spread itself: "the times and chances are the pipeline's" fails.
// - `argmin` keeping the last of a tie (`<=`): "argmin keeps the first of a tie" fails.
// - A percentage typed in the text for its `data-fig`: "has no digit typed in the prose" fails.

const EX = REBOUND.example;
const F: Record<string, unknown> = reboundFigures(REBOUND);
const html = <P extends object>(c: FunctionComponent<P>, props: P) => renderToStaticMarkup(createElement(c, props));

describe("the time to arrive", () => {
  const still: Runner = { x: 3, y: 4, vx: 0, vy: 0 };
  const runner: Runner = { x: -4, y: 0, vx: 5, vy: 0 };

  it("is the reaction plus what is left at top speed", () => {
    const [a, b] = arrival([still, runner], [0, 0], 0.7, 5);
    expect(a).toBeCloseTo(0.7 + 5 / 5, 12);
    expect(b).toBeCloseTo(0.7 + 0.5 / 5, 12); // the reaction carries the runner 3.5 m of 4
    expect(nearest([still, runner], [0, 0])).toBe(1);
  });

  it("argmin keeps the first of a tie, like numpy", () => {
    expect(argmin([2, 1, 1, 3])).toBe(1);
  });

  it("the chances add up to one, split evenly between equal times, and favour the earlier", () => {
    const c = chanceFirst([0.8, 0.8], 0.54);
    expect(c[0]).toBeCloseTo(0.5, 9);
    expect(c[1]).toBeCloseTo(0.5, 9);
    const d = chanceFirst([0.8, 1.2, 2.5, 0.9], 0.54);
    expect(d.reduce((s, v) => s + v, 0)).toBeCloseTo(1, 6);
    expect(argmin(d.map((v) => -v))).toBe(0);
  });
});

describe("the example against the pipeline", () => {
  it("the times and chances are the pipeline's, to the decimals it publishes", () => {
    const race = raceAt(REBOUND, REBOUND.reaction_s, REBOUND.top_speed);
    expect(race.times.map((t) => Number(t.toFixed(3)))).toEqual(EX.times);
    expect(race.chance.map((c) => Number(c.toFixed(3)))).toEqual(EX.chance_first);
    expect([race.first, race.nearest]).toEqual([EX.model, EX.nearest]);
  });

  it("no reaction gives the nearest player; the top speed never changes the first", () => {
    expect(raceAt(REBOUND, 0, REBOUND.top_speed).first).toBe(EX.nearest);
    const firsts = steps(SPEED_MIN, SPEED_MAX, SPEED_STEP).map((v) => raceAt(REBOUND, REBOUND.reaction_s, v).first);
    expect(new Set(firsts)).toEqual(new Set([EX.model]));
  });

  it("is what the text says it is: the model names the player who took it, the nearest rule does not", () => {
    expect(EX.model).toBe(EX.rebounder);
    expect(EX.nearest).not.toBe(EX.rebounder);
    expect(F.ex_gap_ms as number).toBeLessThan(1000 * REBOUND.spread_s);
  });

  it("the race figure opens on the sources' values", () => {
    const markup = html(RaceFigure, { file: REBOUND });
    const cell = (path: string) => markup.match(new RegExp(`data-fig="${path}">([^<]*)<`))?.[1];
    expect(cell("learn.race.reaction")).toBe(String(REBOUND.reaction_s));
    expect(cell("learn.race.first_time")).toBe(String(F.ex_first_time));
    expect(cell("learn.race.first_chance")).toBe(String(F.ex_first_chance));
  });
});

describe("the figures over ten matches", () => {
  it("the selection adds up to the file's rebounds, and every match is one of three cases", () => {
    const sum = (k: "rebounds" | "n") => REBOUND.matches.reduce((s, m) => s + m[k], 0);
    const f = F as Record<string, number>;
    expect(f.rebounds).toBe(sum("rebounds"));
    expect(f.team_rebounds + f.not_field_goal + f.no_location + f.not_after + f.not_ten + f.raced).toBe(f.rebounds);
    expect(f.raced).toBe(sum("n"));
    expect(f.ahead + f.level + f.behind).toBe(REBOUND.matches.length);
    expect(f.zero_is_nearest).toBe(REBOUND.matches.length);
  });
});

// The text as the server renders it.
const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "rebound.sql"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { sql: SQL }));
const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (html: string, tags: string[]) =>
  tags.reduce((h, tag) => h.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), html);
const text = (html: string) => entities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const PROSE = text(
  drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]),
);

describe("the text of lesson 4", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(100);
    const wrong = figs.filter(([path, shown]) => {
      // The race figure's readouts live in its state; "the race figure opens on the sources' values" checks them.
      if (path.startsWith("learn.race.")) return false;
      const value = path.startsWith("learn.")
        ? path.slice(6).split(".").reduce<unknown>((o, k) => (o as Record<string, unknown>)?.[k], F)
        : reboundFigure(REBOUND, path);
      return value === undefined || shown !== String(value);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/.{0,30}\d+.{0,30}/g)).toBeNull();
  });

  it("has none of the fence's forbidden keys or watched words outside a quote or a citation", () => {
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    const watched = ["time to impact", "pressure", "pressing", "defensive line", "straight line", "second difference", "constant velocity", "football"];
    expect(watched.filter((w) => outside.includes(w))).toEqual([]);
    expect(outside).toContain("time to arrive");
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
  });

  it("is between 1,500 and 2,300 words: its figures counted, its formulas, query and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 4: ${words} words`);
    expect(words).toBeGreaterThanOrEqual(1500);
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
  it("every stroke and fill the race and the reaction plot render is 3:1 or more on the canvas", () => {
    const markups = [html(RaceFigure, { file: REBOUND }), html(ReactionPlot, { file: REBOUND })];
    const colours = new Set(markups.flatMap((m) => [...m.matchAll(/(?:stroke|fill)="([^"]+)"/g)].map((x) => x[1])).filter((c) => c !== "none"));
    expect(colours.size).toBeGreaterThan(3);
    expect([...colours].filter((c) => !/^#[0-9a-f]{6}$/i.test(c) || contrast(c, CANVAS) < 3)).toEqual([]);
  });
});
