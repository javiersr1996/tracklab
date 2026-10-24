import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Lesson } from "../components/learn/gravity/Lesson";
import fence from "../lib/learn/fence.json";
import { GRAVITY_HOOK, GRAVITY_MATCHES, qualityFigure } from "../lib/learn/gravity-data";
import { lessonFigures } from "../lib/learn/lesson-figures";
import { SOURCES } from "../lib/learn/sources";
import { QUALITY } from "../lib/quality";

// The text of lesson 1 (task 80) as the server renders it. The e2e of task 81 repeats the figure
// and prose checks in the browser; these run on every `npm test`.
//
// Mutations checked by hand, each restored byte for byte:
// - "the RMS rises to 44 mm" typed for its `data-fig`: "no digit is typed" fails.
// - `<Fig name="learn.fit_g">8.1455</Fig>` for `l("fit_g")`: "every data-fig" fails.
// - "undetected" in Limitations, outside the quote: "none of the fence's forbidden keys" fails.
// - A `<Cite id>` of a source missing from sources.ts: the render throws, every test fails.

const SQL = readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", "gravity.sql"), "utf-8");
const HTML = renderToStaticMarkup(createElement(Lesson, { sql: SQL }));
const FIGURES: Record<string, unknown> = lessonFigures(GRAVITY_HOOK, GRAVITY_MATCHES);

const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const drop = (html: string, tags: string[]) =>
  tags.reduce((h, tag) => h.replace(new RegExp(`<${tag}[\\s>][\\s\\S]*?</${tag}>`, "g"), " "), html);
const text = (html: string) => entities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();

// What is left once the figures and everything the rule exempts are taken out.
const PROSE = text(
  drop(HTML.replace(/<span data-(?:fig|series-n)="[^"]*">[^<]*<\/span>/g, " "), ["figure", "pre", "math", "table", "cite", "q", "code"]),
);

describe("the text of lesson 1", () => {
  it("prints every data-fig as its source has it", () => {
    const figs = [...HTML.matchAll(/data-fig="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
    expect(figs.length).toBeGreaterThan(60);
    const wrong = figs.filter(([path, shown]) => {
      const value = path.startsWith("learn.") ? path.slice(6).split(".").reduce<unknown>((o, k) => (o as Record<string, unknown>)?.[k], FIGURES) : qualityFigure(QUALITY, path);
      // The figures' own readouts (`learn.fit.g`, ...) live in their state; the vitest of task 79 checks them.
      if (value === undefined && /^learn\.(fit|window|noise)\./.test(path)) return false;
      return value === undefined || shown !== String(value);
    });
    expect(wrong).toEqual([]);
  });

  it("has no digit typed in the prose", () => {
    expect(PROSE.match(/\d+/g)).toBeNull();
  });

  it("has none of the fence's forbidden keys outside a quote or a citation", () => {
    const outside = text(drop(HTML, ["cite", "q"])).toLowerCase();
    expect(fence.forbidden_keys.filter((k) => outside.includes(k))).toEqual([]);
    expect(fence.held_out.filter((id) => HTML.includes(id))).toEqual([]);
  });

  // That every source is cited by some lesson is checked across the series, in
  // tests/learn-coordinates.test.ts, now that sources.ts holds more than this lesson's.
