import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Lesson as CadenceLesson } from "../components/learn/cadence/Lesson";
import { Lesson as CoordinatesLesson } from "../components/learn/coordinates/Lesson";
import { Lesson } from "../components/learn/gravity/Lesson";
import { Lesson as ReboundLesson } from "../components/learn/rebound/Lesson";
import { Lesson as SpeedLesson } from "../components/learn/speed/Lesson";
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

  it("cites only sources.ts, and lessons 1 to 5 together cite every source in it", () => {
    const learn = (name: string) => readFileSync(join(process.cwd(), "..", "pipeline", "src", "tracklab", "learn", name), "utf-8");
    const hrefs = (html: string) => [...html.matchAll(/<cite><a href="([^"]+)"/g)].map((m) => entities(m[1]));
    const urls = Object.values(SOURCES).map((s) => s.url);
    const cited = new Set([
      ...hrefs(HTML),
      ...hrefs(renderToStaticMarkup(createElement(SpeedLesson, { sql: learn("speed.sql") }))),
      ...hrefs(renderToStaticMarkup(createElement(CoordinatesLesson, { sql: learn("coordinates.sql") }))),
      ...hrefs(renderToStaticMarkup(createElement(ReboundLesson, { sql: learn("rebound.sql") }))),
      ...hrefs(renderToStaticMarkup(createElement(CadenceLesson, { script: learn("cadence.py") }))),
    ]);
    expect([...cited].filter((h) => !urls.includes(h))).toEqual([]);
    expect(urls.filter((u) => !cited.has(u))).toEqual([]);
  });

  // Against the provider's own file where the clone the pipeline reads is on disk (its receipt
  // names it and the commit it was verified at); CI has no clone and skips.
  const receiptPath = join(process.cwd(), "..", "pipeline", "data", "raw", "opendata-basketball", "_receipt.json");
  const receipt = existsSync(receiptPath) ? (JSON.parse(readFileSync(receiptPath, "utf-8")) as { commit: string; source_path: string }) : null;
  const dictionary = receipt ? join(receipt.source_path, "docs", "data_dictionary", "tracking_data.md") : "";
  it.skipIf(!receipt || !existsSync(dictionary))("quotes the provider's definition of the ball's flag word for word", () => {
    expect(receipt?.commit.startsWith("4bbed2e")).toBe(true);
    const line42 = readFileSync(dictionary, "utf-8").split("\n")[41];
    const q = HTML.match(/<q>(<code>1\.0<\/code>[^]*?)<\/q>/)?.[1] ?? "";
    const quoted = text(q.replace(/<\/?code>/g, "`"));
    expect(quoted).toBe(SOURCES["skillcorner-tracking"].quote);
    expect(line42.startsWith("| `isDetected` |")).toBe(true);
    expect(line42).toContain(quoted);
  });

  it("is between 1,800 and 2,300 words: its figures counted, its formulas, query and figure panels not", () => {
    const words = text(drop(HTML, ["figure", "pre", "math"])).split(" ").filter((w) => /[A-Za-z0-9]/.test(w)).length;
    console.log(`lesson 1: ${words} words`);
    expect(words).toBeGreaterThanOrEqual(1800);
    expect(words).toBeLessThanOrEqual(2300);
  });
});
