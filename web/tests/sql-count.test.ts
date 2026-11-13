import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

// P24: every place that says how many lessons /sql has counts SQL_LESSONS, never a typed word or
// number. The list is cut to three here, so a typed count (even the right one today) fails.
vi.mock("../lib/sql/course", async (original) => {
  const real = await original<typeof import("../lib/sql/course")>();
  return { ...real, SQL_LESSONS: real.SQL_LESSONS.slice(0, 3) };
});

const { SECTIONS } = await import("../lib/sections");
const { sqlMetadata } = await import("../lib/sql/metadata");

const count = (html: string) => [...html.matchAll(/data-sql-count="[^"]*">([^<]*)</g)].map((m) => m[1]);

describe("the count of the SQL lessons", () => {
  it("follows the list in the section's line and the course's description", () => {
    expect(SECTIONS.find((s) => s.href === "/sql")!.about).toMatch(/^3 lessons /);
    expect(sqlMetadata.description).toMatch(/^3 lessons /);
    expect(String(sqlMetadata.openGraph?.description)).toMatch(/^3 lessons /);
  });

  it("follows the list on /sql and on /warehouse", async () => {
    const { default: SqlPage } = await import("../app/sql/page");
    const { default: WarehousePage } = await import("../app/warehouse/page");
    expect(count(renderToStaticMarkup(createElement(SqlPage)))).toEqual(["3"]);
    expect(count(renderToStaticMarkup(createElement(WarehousePage)))).toEqual(["3"]);
  });
});
