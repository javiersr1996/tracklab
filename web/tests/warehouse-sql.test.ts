import { describe, expect, it } from "vitest";
import { checkSql } from "../lib/warehouse/sql";

// The read-only gate of task 42 (`lib/warehouse/sql.ts`): one SELECT, WITH or EXPLAIN, no
// statement keyword that installs, loads, attaches, copies or configures, and no URL.
//
// Mutations checked by hand (each restored byte for byte):
// - dropping the `includes("://")` check lets the four URL cases through, failing
//   `rejects any URL ...`;
// - checking only the first statement (no split on `;`) lets `SELECT 1; INSTALL httpfs` through,
//   failing `rejects a second statement`;
// - tokenizing strings as plain text (no `quoted`) makes the keyword inside `'LOAD this'` a
//   word, failing `admits keywords inside strings ...`.

const TABLES = ["bb_shots", "fb_physical", "fact"];
const ok = (sql: string) => checkSql(sql, TABLES).ok;
const reason = (sql: string) => {
  const check = checkSql(sql, TABLES);
  return check.ok ? null : check.reason;
};

describe("checkSql admits", () => {
  it.each([
    "SELECT 1",
    "select * from fact limit 5",
    "WITH t AS (SELECT * FROM bb_shots) SELECT count(*) FROM t",
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 3) SELECT * FROM n",
    "EXPLAIN SELECT * FROM fact WHERE metric = 'handler_ppp'",
    "EXPLAIN ANALYZE SELECT quantile_cont(value, 0.9) FROM fact",
    "explain analyze with t as (select 1) select * from t",
    "(SELECT 1) UNION ALL (SELECT 2)",
    "SELECT 1;",
    "SELECT 1;  ;\n",
  ])("%s", (sql) => {
    expect(reason(sql)).toBeNull();
  });

  it("admits keywords inside strings, comments and quoted identifiers", () => {
    expect(ok("SELECT 'LOAD this' AS x")).toBe(true);
    expect(ok("-- INSTALL httpfs\nSELECT 1")).toBe(true);
    expect(ok("/* ATTACH 'x.db'; COPY */ SELECT 1")).toBe(true);
    expect(ok('SELECT 1 AS "set"')).toBe(true);
    expect(ok("SELECT 'it''s; INSTALL httpfs' AS x")).toBe(true);
  });

  it("names the registered tables the statement mentions, and only those", () => {
    expect(checkSql('SELECT * FROM bb_shots JOIN "FACT" USING (player_id)', TABLES)).toEqual({
      ok: true,
      tables: ["bb_shots", "fact"],
    });
    expect(checkSql("SELECT 'fb_physical' AS fact_name FROM Fb_Physical", TABLES)).toEqual({
      ok: true,
      tables: ["fb_physical"],
    });
    expect(checkSql("SELECT 1", TABLES)).toEqual({ ok: true, tables: [] });
  });
});

describe("checkSql rejects", () => {
  it.each([
    ["INSTALL httpfs", /Only SELECT/],
    ["FORCE INSTALL httpfs", /Only SELECT/],
    ["LOAD parquet", /Only SELECT/],
    ["ATTACH 'other.duckdb'", /Only SELECT/],
    ["COPY (SELECT 1) TO 'out.csv'", /Only SELECT/],
    ["SET enable_external_access = true", /Only SELECT/],
    ["PRAGMA version", /Only SELECT/],
    ["CREATE VIEW v AS SELECT 1", /Only SELECT/],
    ["DROP VIEW fact", /Only SELECT/],
    ["DESCRIBE fact", /Only SELECT/],
    ["EXPLAIN ANALYZE COPY (SELECT 1) TO 'out.csv'", /Only SELECT/],
  ])("%s", (sql, why) => {
    expect(reason(sql)).toMatch(why);
  });

  it("rejects the same keywords inside a read", () => {
    expect(reason("WITH t AS (SELECT 1) INSERT INTO fact SELECT * FROM t")).toMatch(/INSERT is not allowed/);
    expect(reason("EXPLAIN ANALYZE SELECT 1 FROM (LOAD parquet)")).toMatch(/LOAD is not allowed/);
    expect(reason("select 1 from x where y in (select 1) -- fine\n; attach 'x'")).toMatch(/One statement/);
  });

  it("rejects a second statement", () => {
    expect(reason("SELECT 1; INSTALL httpfs")).toMatch(/One statement at a time/);
    expect(reason("SELECT 1; SELECT 2")).toMatch(/One statement at a time/);
  });

  it("rejects any URL, quoted as a string, a dollar string or an identifier", () => {
    for (const sql of [
      "SELECT * FROM read_csv('https://example.com/x.csv')",
      "SELECT * FROM 'https://example.com/x.parquet'",
      'SELECT * FROM "s3://bucket/x.parquet"',
      "SELECT * FROM read_text($$http://example.com/$$)",
    ]) {
      expect(reason(sql), sql).toMatch(/No URLs/);
    }
  });

  it("rejects table functions that run a SQL string", () => {
    expect(reason("SELECT * FROM query('INSTALL httpfs')")).toMatch(/query\(\) is not allowed/);
    expect(reason("SELECT * FROM query_table('fact')")).toMatch(/query_table\(\) is not allowed/);
  });

  it("rejects nothing to run and unterminated quotes or comments", () => {
    expect(reason("")).toMatch(/Nothing to run/);
    expect(reason("  -- just a comment\n ; ")).toMatch(/Nothing to run/);
    expect(reason("SELECT 'open")).toMatch(/Unterminated string/);
    expect(reason('SELECT "open')).toMatch(/Unterminated identifier/);
    expect(reason("SELECT 1 /* open")).toMatch(/Unterminated comment/);
    expect(reason("SELECT $$open")).toMatch(/Unterminated dollar/);
  });
});
