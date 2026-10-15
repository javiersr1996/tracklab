import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Client } from "pg";
import { GET } from "../app/api/warehouse/pg/route";
import { exampleIds, summary } from "../lib/warehouse/pg";
import { DEADLINE_MS, STATEMENT_TIMEOUT_MS, isTimeout, runExample } from "../lib/warehouse/pg-run";
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

  it("closes the connection when its own deadline passes before the statement_timeout", async () => {
    const started = Date.now();
    const error = await runExample(url!, "SELECT pg_sleep(1.5)", 300).then(
      () => null,
      (e) => e,
    );
    expect(isTimeout(error)).toBe(true);
    expect(Date.now() - started).toBeLessThan(1000);
  });

  // Review V of P4, M1: Postgres lets any role change its own defaults in a database, so whoever
  // holds the reader's password can switch off task 44's 2 s and read-only default for every
  // later session. The route must hold its limits without them.
  describe("after the role switched off its own defaults", () => {
    const asReader = async (statements: string[]) => {
      const client = new Client({ connectionString: url });
      await client.connect();
      try {
        const results = [];
        for (const statement of statements) results.push((await client.query(statement)).rows);
        return results;
      } finally {
        await client.end();
      }
    };
    const setOwnDefaults = async (timeout: string, readOnly: string) => {
      const [[{ db }]] = await asReader(["SELECT current_database() AS db"]);
      const role = `ALTER ROLE warehouse_reader IN DATABASE "${db}" SET`;
      await asReader([
        "SET default_transaction_read_only = off",
        `${role} statement_timeout = '${timeout}'`,
        `${role} default_transaction_read_only = ${readOnly}`,
      ]);
    };
    beforeAll(() => setOwnDefaults("0", "off"));
    afterAll(() => setOwnDefaults("2s", "on"));

    it("a new session of the role has no time limit and may write", async () => {
      const [[timeout], [readOnly]] = await asReader(["SHOW statement_timeout", "SHOW default_transaction_read_only"]);
      expect([timeout.statement_timeout, readOnly.default_transaction_read_only]).toEqual(["0", "off"]);
    });

    it("the route still cancels a slow statement at its own statement_timeout", async () => {
      const started = Date.now();
      const error = await runExample(url!, "SELECT pg_sleep(3)").then(
        () => null,
        (e) => e,
      );
      const elapsed = Date.now() - started;
      // Cancelled by the server (57014) at the route's 2 s, not by the route's own 3 s deadline.
      expect(isTimeout(error)).toBe(true);
      expect(error?.code).toBe("57014");
      expect(elapsed).toBeGreaterThanOrEqual(STATEMENT_TIMEOUT_MS);
      expect(elapsed).toBeLessThan(DEADLINE_MS - 500);
    });

    it("the route still cannot write a large object", async () => {
      const error = await runExample(url!, "SELECT lo_from_bytea(0, decode('41', 'hex'))").then(
        () => null,
        (e) => e,
      );
      expect(error?.code).toBe("25006");
    });
  });

  // Review V of P4, S5: whatever happens to the statement, the transaction ends before the
  // connection is closed. `end` is made a no-op here, as if the Terminate never arrived (a frozen
  // function, a pooler that keeps the server connection). Without the ROLLBACK a statement that
  // finished leaves its session `idle in transaction` with its AccessShareLock, so the owner's
  // ALTER TABLE cannot get through; one cut by the timeout leaves it `idle in transaction (aborted)`.
  it.each([
    ["a statement that finished", "SELECT count(*) FROM warehouse.dim_team", null],
    ["a statement cut by the timeout", "SELECT count(*), pg_sleep(3) FROM warehouse.dim_team", "57014"],
  ])("leaves no open transaction or lock behind after %s", async (_name, query, code) => {
    const owner = process.env.TRACKLAB_TEST_WEB_PG_ADMIN_URL;
    if (!owner) throw new Error("TRACKLAB_TEST_WEB_PG_ADMIN_URL is the owner's connection string");
    const leaked: Client[] = [];
    const end = vi.spyOn(Client.prototype, "end").mockImplementation(function (this: Client) {
      leaked.push(this);
      return Promise.resolve();
    });
    const admin = new Client({ connectionString: owner });
    await admin.connect();
    try {
      const error = await runExample(url!, query).then(
        () => null,
        (e) => e,
      );
      expect(error?.code ?? null).toBe(code);
      const open = await admin.query(
        "SELECT state FROM pg_stat_activity WHERE usename = 'warehouse_reader' AND state LIKE 'idle in transaction%'",
      );
      expect(open.rows).toEqual([]);
      await admin.query("SET lock_timeout = '1s'");
      await admin.query('ALTER TABLE warehouse.dim_team ALTER COLUMN team_name SET DATA TYPE text COLLATE "C"');
    } finally {
      end.mockRestore();
      await Promise.all(leaked.map((c) => c.end().catch(() => {})));
      await admin.end();
    }
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
