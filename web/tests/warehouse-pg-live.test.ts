import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Client } from "pg";
import { GET } from "../app/api/warehouse/pg/route";
import { exampleIds, summary } from "../lib/warehouse/pg";
import { isTimeout, runExample } from "../lib/warehouse/pg-run";
import type { PgCell } from "../lib/warehouse/pg-types";

// Task 45 against a real Postgres: `TRACKLAB_TEST_WEB_PG_URL` is the connection string of the
// `warehouse_reader` role, on a Docker `postgres:17.11` (locally, with the real gold loaded by
// `tracklab load postgres`) or on the service container of ci.yml (the schema of task 44 and no
// rows). Never Neon. Without the variable these skip, unless TRACKLAB_REQUIRE_PG is set, as in CI.
const URL_ENV = "TRACKLAB_TEST_WEB_PG_URL";
const url = process.env[URL_ENV];
if (!url && process.env.TRACKLAB_REQUIRE_PG) throw new Error(`TRACKLAB_REQUIRE_PG is set and ${URL_ENV} is not`);
const live = url ? describe : describe.skip;

let loaded = false;
beforeAll(async () => {
  if (!url) return;
  const client = new Client({ connectionString: url });
  await client.connect();
  loaded = Number((await client.query("SELECT count(*) AS n FROM warehouse.dim_player")).rows[0].n) > 0;
  await client.end();
});
afterEach(() => vi.unstubAllEnvs());

const near = (a: PgCell, b: PgCell) =>
  typeof a === "number" && typeof b === "number" ? Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b)) : a === b;

live("the route against Postgres, as the read-only role", () => {
  it.each(exampleIds())("answers the example %s with the columns of the snapshot", async (id) => {
    vi.stubEnv("DATABASE_URL", url!);
    const body = await (await GET(new Request(`http://localhost/api/warehouse/pg?id=${id}`))).json();
    const expected = summary().examples.find((e) => e.id === id)!;
    expect(body.status).toBe("live");
    expect(body.columns).toEqual(expected.columns);
    expect(body.ms).toBeGreaterThan(0);
    if (loaded) {
      // Real gold loaded: the rows are the snapshot's (numbers, not the strings pg gives).
      expect(body.rows).toHaveLength(expected.rows.length);
      body.rows.forEach((row: PgCell[], i: number) =>
        row.forEach((cell, j) => expect(near(cell, expected.rows[i][j]), `${id} row ${i} col ${j}`).toBe(true)),
      );
    }
  });

  it("answers unavailable, not an error status, when the server is not there", async () => {
    vi.stubEnv("DATABASE_URL", "postgresql://127.0.0.1:1/postgres");
    const res = await GET(new Request("http://localhost/api/warehouse/pg?id=teams"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "unavailable" });
  });

  it("turns numeric and bigint into numbers", async () => {
    const run = await runExample(url!, "SELECT 2.5::numeric AS n, 3::bigint AS b, 'x' AS t, NULL AS z");
    expect(run.columns).toEqual(["n", "b", "t", "z"]);
    expect(run.rows).toEqual([[2.5, 3, "x", null]]);
  });

  it("cancels a statement longer than the role's statement_timeout", async () => {
    const started = Date.now();
    const error = await runExample(url!, "SELECT pg_sleep(10)").then(
      () => null,
      (e) => e,
    );
    expect(error).not.toBeNull();
    expect(isTimeout(error)).toBe(true);
    // The role's 2 s (or the route's own 3 s deadline), never the ten seconds of the sleep.
    expect(Date.now() - started).toBeLessThan(3500);
  });

  it("closes the connection when its own deadline passes before the role's", async () => {
    const started = Date.now();
    const error = await runExample(url!, "SELECT pg_sleep(1.5)", 300).then(
      () => null,
      (e) => e,
    );
    expect(isTimeout(error)).toBe(true);
    expect(Date.now() - started).toBeLessThan(1000);
  });

  it("cannot write, even in a transaction opened read-write", async () => {
    const client = new Client({ connectionString: url });
    await client.connect();
    try {
      await client.query("BEGIN READ WRITE");
      await expect(client.query("DELETE FROM warehouse.dim_player")).rejects.toMatchObject({ code: "42501" });
    } finally {
      await client.end();
    }
  });
});
