import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Task 45: the route takes the id of an example and nothing else. The driver is mocked so the
// test can count the connections the route opens: a request it refuses must open none.
const connections = vi.hoisted(() => ({
  opened: 0,
  sent: [] as string[],
  fail: null as Error | null,
  role: "warehouse_reader",
  rows: [[1]] as unknown[][],
}));
vi.mock("pg", () => {
  class Client {
    constructor() {
      connections.opened += 1;
    }
    on() {}
    async connect() {}
    async query(query: string | { text: string }) {
      connections.sent.push(typeof query === "string" ? query : query.text);
      if (connections.fail) throw connections.fail;
      // The header is three statements: pg answers a list of results, the last one is the role.
      if (connections.sent.at(-1)?.startsWith("BEGIN")) return [{}, {}, { rows: [[connections.role]] }];
      return { fields: [{ name: "x" }], rows: connections.rows };
    }
    async end() {}
  }
  return { Client, types: { getTypeParser: () => String } };
});

import * as route from "../app/api/warehouse/pg/route";
import { EXAMPLES } from "../lib/warehouse/examples";
import { exampleIds, sqlOf, summary } from "../lib/warehouse/pg";
import { MAX_ROWS, STATEMENT_TIMEOUT_MS } from "../lib/warehouse/pg-run";

const ask = (query: string) => route.GET(new Request(`http://localhost/api/warehouse/pg${query}`));

beforeEach(() => {
  connections.opened = 0;
  connections.sent = [];
  connections.fail = null;
  connections.role = "warehouse_reader";
  connections.rows = [[1]];
  vi.stubEnv("DATABASE_URL", "postgresql://reader@db.invalid/db");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("a request that is not one example id", () => {
  const refused: [string, string][] = [
    ["no id", ""],
    ["empty id", "?id="],
    ["unknown id", "?id=nope"],
    ["SQL as the id", `?id=${encodeURIComponent("SELECT 1")}`],
    ["SQL appended to a real id", `?id=${encodeURIComponent("profile; DROP TABLE warehouse.dim_player")}`],
    ["an object property", "?id=constructor"],
    ["the prototype", "?id=__proto__"],
    ["SQL beside a real id", `?id=profile&sql=${encodeURIComponent("SELECT 1")}`],
    ["the SQL alone", `?sql=${encodeURIComponent("SELECT 1")}`],
    ["a repeated id", "?id=profile&id=teams"],
    ["an id of another case", "?id=PROFILE"],
  ];
  it.each(refused)("gets 400 and opens no connection: %s", async (_name, query) => {
    const res = await ask(query);
    expect(res.status).toBe(400);
    expect(connections.opened).toBe(0);
  });

  it("has no handler for a method that could carry a body", () => {
    expect(Object.keys(route).filter((k) => /^(POST|PUT|PATCH|DELETE)$/.test(k))).toEqual([]);
  });
});

describe("an example id", () => {
  it("runs the SQL of warehouse_pg.json and answers live", async () => {
    const res = await ask("?id=profile");
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ status: "live", id: "profile", columns: ["x"], rows: [[1]], truncated: false });
    expect(connections.opened).toBe(1);
  });

  // P19, task 154: a live answer is fixed by the id and cacheable; every state that can change at
  // once is not.
  it("caches a live answer at the CDN and nothing else", async () => {
    const live = await ask("?id=profile");
    expect(live.headers.get("cache-control")).toMatch(/^public, max-age=0, s-maxage=[0-9]+, stale-while-revalidate=[0-9]+$/);

    vi.spyOn(console, "error").mockImplementation(() => {});
    connections.fail = new Error("boom");
    expect((await ask("?id=profile")).headers.get("cache-control")).toBe("no-store");
    connections.fail = null;
    vi.stubEnv("DATABASE_URL", "");
    const absent = await ask("?id=profile");
    expect(await absent.json()).toEqual({ status: "absent" });
    expect(absent.headers.get("cache-control")).toBe("no-store");
    expect((await ask("?id=nope")).headers.get("cache-control")).toBe("no-store");
  });

  it("hands back at most MAX_ROWS rows and says when it cut", async () => {
    connections.rows = Array.from({ length: MAX_ROWS + 5 }, (_, i) => [i]);
    const body = await (await ask("?id=profile")).json();
    expect(body.rows).toHaveLength(MAX_ROWS);
    expect(body.truncated).toBe(true);
    expect(body.rows.at(-1)).toEqual([MAX_ROWS - 1]);
  });

  it("runs it inside a read-only transaction with its own statement_timeout", async () => {
    await ask("?id=profile");
    // Not the role's defaults, which the role can change on itself (review V of P4, M1).
    expect(connections.sent).toEqual([
      `BEGIN READ ONLY; SET LOCAL statement_timeout = ${STATEMENT_TIMEOUT_MS}; SELECT current_user AS u`,
      sqlOf("profile"),
      "ROLLBACK",
    ]);
  });

  it("rolls back after an error too", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    connections.fail = new Error("boom");
    await ask("?id=profile");
    expect(connections.sent.at(-1)).toBe("ROLLBACK");
  });

  // Review V of P4, S4: another role (the owner's URL pasted into Vercel) gets no query.
  it("does not query as another role, and does not name it", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    connections.role = "neondb_owner";
    const res = await ask("?id=profile");
    expect(await res.json()).toEqual({ status: "unavailable" });
    expect(connections.sent).not.toContain(sqlOf("profile"));
    expect(JSON.stringify(log.mock.calls)).not.toContain("neondb_owner");
  });

  it("logs the code of an error, never its message", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    connections.fail = Object.assign(new Error('password authentication failed for user "reader" at db.invalid'), {
      code: "28P01",
    });
    expect(await (await ask("?id=profile")).json()).toEqual({ status: "unavailable" });
    expect(log.mock.calls).toEqual([["warehouse pg route: 28P01"]]);
  });

  it("without DATABASE_URL answers absent and opens no connection", async () => {
    vi.stubEnv("DATABASE_URL", "");
    const res = await ask("?id=profile");
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "absent" });
    expect(connections.opened).toBe(0);
  });
});

describe("the examples", () => {
  it("are the ones of the console, by id", () => {
    expect(exampleIds().sort()).toEqual(EXAMPLES.map((e) => e.id).sort());
  });

  it("each have SQL that reads the warehouse schema and writes nothing", () => {
    for (const id of exampleIds()) {
      const sql = sqlOf(id)!;
      expect(sql, id).toMatch(/warehouse\./);
      expect(sql, id).not.toMatch(/\b(insert|update|delete|truncate|create|drop|alter|grant)\b/i);
    }
  });

  it("reach the page without their SQL or their plans", () => {
    const json = JSON.stringify(summary());
    for (const id of exampleIds()) expect(json).not.toContain(sqlOf(id)!.slice(0, 40));
    expect(json).not.toContain('"plan"');
    expect(json).not.toContain('"sql"');
  });
});
