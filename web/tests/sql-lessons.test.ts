import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PROSE } from "../components/sql/lessons";
import { display } from "../lib/learn/display";
import { COURSE, courseLesson, SQL_LESSONS, SQL_SLUGS } from "../lib/sql/course";

// The prose of the eight lessons of /sql (task 101) as the server renders it: every number and
// name a lesson prints is a `data-fact` whose text is the fact of course.json, and nothing else
// in the prose has a digit (code is the exception: `LIMIT 11`, `7 // 2`).
//
// Mutations checked by hand, each restored byte for byte:
// - "{f("rows")}" of lesson 1 replaced by the typed "326": "no digit is typed" fails.
// - `<span data-fact="rows">327</span>` typed in lesson 1: "prints every fact" fails.

const entities = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const dropCode = (html: string) => html.replace(/<code[\s>][\s\S]*?<\/code>/g, " ");
const text = (html: string) => entities(html.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();

describe("the lessons of /sql", () => {
  it("are the eight of course.json, in order, each with exercises and an example", () => {
    expect(COURSE.lessons.map((l) => l.slug)).toEqual([...SQL_SLUGS]);
    expect(SQL_LESSONS.map((l) => l.n)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    for (const slug of SQL_SLUGS) {
      const l = courseLesson(slug);
      expect(l.exercises.length).toBeGreaterThanOrEqual(2);
      expect(l.example.rows.length).toBeGreaterThan(0);
      expect(l.example.rows.length).toBeLessThanOrEqual(20);
    }
  });

  describe.each(SQL_SLUGS.map((slug) => [slug]))("%s", (slug) => {
    const html = renderToStaticMarkup(createElement(PROSE[slug]));
    const facts = courseLesson(slug).facts;

    it("prints every fact as course.json has it", () => {
      const printed = [...html.matchAll(/data-fact="([^"]+)">([^<]*)</g)].map((m) => [m[1], entities(m[2])]);
      expect(printed.length).toBeGreaterThan(3);
      const wrong = printed.filter(([name, shown]) => facts[name] === undefined || shown !== display(facts[name], name));
      expect(wrong).toEqual([]);
    });

    it("types no digit outside a fact or code", () => {
      const prose = text(dropCode(html.replace(/<span data-fact="[^"]*">[^<]*<\/span>/g, " ")));
      expect(prose.length).toBeGreaterThan(400);
      expect(prose.match(/\d+/g) ?? []).toEqual([]);
    });
  });
});
