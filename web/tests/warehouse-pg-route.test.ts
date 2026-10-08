import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Task 45: the route takes the id of an example and nothing else. The driver is mocked so the
// test can count the connections the route opens: a request it refuses must open none.
const connections = vi.hoisted(() => ({ opened: 0 }));
vi.mock("pg", () => {
  class Client {
    constructor() {
      connections.opened += 1;
    }
    on() {}
    async connect() {}
    async query() {
      return { fields: [{ name: "x" }], rows: [[1]] };
    }
    async end() {}
  }
  return { Client, types: { getTypeParser: () => String } };
});

import * as route from "../app/api/warehouse/pg/route";
import { EXAMPLES } from "../lib/warehouse/examples";
import { exampleIds, sqlOf, summary } from "../lib/warehouse/pg";

const ask = (query: string) => route.GET(new Request(`http://localhost/api/warehouse/pg${query}`));

beforeEach(() => {
  connections.opened = 0;
  vi.stubEnv("DATABASE_URL", "postgresql://reader@db.invalid/db");
});
afterEach(() => vi.unstubAllEnvs());

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
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(await res.json()).toMatchObject({ status: "live", id: "profile", columns: ["x"], rows: [[1]] });
    expect(connections.opened).toBe(1);
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
