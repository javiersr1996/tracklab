import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PostgresPanel, type PgState } from "../components/warehouse/PostgresPanel";
import type { QueryResult } from "../lib/warehouse/engine";
import WarehousePage from "../app/warehouse/page";
import { summary } from "../lib/warehouse/pg";
import { CLIENT_LIMIT_MS } from "../lib/warehouse/pg-client";

// Review V of P4, B4 and B7: what the Postgres panel says comes from the constants and the
// snapshot, not from text typed beside them.
const SUMMARY = summary();
const EXAMPLE = SUMMARY.examples[0];
const PARQUET: QueryResult = {
  sql: "",
  columns: [],
  rows: [],
  rowCount: 0,
  ms: 1,
  bytes: 0,
  distinctBytes: 0,
  requests: 0,
  files: [],
};

const panel = (pg: PgState) =>
  renderToStaticMarkup(createElement(PostgresPanel, { pg, summary: SUMMARY, example: EXAMPLE, parquet: PARQUET }));

const rows = (html: string, figure: string) =>
  [...html.matchAll(new RegExp(`<tr data-side="postgres" data-figure="${figure}">(.*?)</tr>`, "g"))].map((m) => m[1]);

describe("the Postgres panel", () => {
  it("says it waits as long as the client does", () => {
    expect(panel({ id: EXAMPLE.id, backend: "running" })).toContain(`for up to ${CLIENT_LIMIT_MS / 1000} seconds`);
  });

  it("names where the plan was measured beside live rows", () => {
    const html = panel({ id: EXAMPLE.id, backend: "live", columns: [], rows: [], ms: 1 });
    const planRows = ["buffers", "indexes", "ms"].flatMap((f) => rows(html, f));
    expect(planRows).toHaveLength(3);
    for (const row of planRows) expect(row).toContain(SUMMARY.source.where);
  });
});

describe("the warehouse page", () => {
  it("says how many queries the route runs, as many as warehouse_pg.json holds", () => {
    const html = renderToStaticMarkup(createElement(WarehousePage));
    expect(html).toContain(`runs only those ${SUMMARY.examples.length} queries`);
  });
});
