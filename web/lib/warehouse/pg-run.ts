// Runs one example's SQL on Postgres for the route of task 45 (server only: the driver is `pg`,
// node-postgres 8.23.1, which Next keeps out of the client bundle).
//
// Driver: `pg`, because it speaks the plain wire protocol to Neon over TCP in the Node runtime,
// is the most used Node driver, and takes a hard `query_timeout`. Neon's serverless driver
// (WebSocket or HTTP) buys nothing for a Node function, and `postgres` adds nothing `pg` lacks
// for five fixed queries.
//
// Limits, innermost first: the role's `statement_timeout` (task 44, 2 s, set on the role in the
// database, so it holds through a pooler that rejects startup parameters), the connection
// timeout, and a deadline over connect and query together, after which the connection is closed.
import { Client, types } from "pg";
import type { PgCell } from "./pg-types";

export const CONNECT_MS = 2000;
export const DEADLINE_MS = 3000;

export class PgTimeout extends Error {}

// bigint and numeric arrive as text by default; these answers (counts, rounded values) fit a double.
const NUMBER_OIDS = new Set([20, 1700]);
const asNumbers = {
  getTypeParser: ((oid: number, format?: "text" | "binary") =>
    NUMBER_OIDS.has(oid) ? Number : types.getTypeParser(oid, format as "text")) as typeof types.getTypeParser,
};

export interface PgRun {
  columns: string[];
  rows: PgCell[][];
  // The query alone, measured here; the connection is not in it.
  ms: number;
}

export async function runExample(
  dsn: string,
  sql: string,
  deadlineMs = DEADLINE_MS,
  connectMs = CONNECT_MS,
): Promise<PgRun> {
  const client = new Client({
    connectionString: dsn,
    connectionTimeoutMillis: connectMs,
    query_timeout: deadlineMs,
    types: asNumbers,
  });
  // A dropped connection emits `error` on the client; unhandled, it would end the process.
  client.on("error", () => {});
  let timer: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new PgTimeout("deadline")), deadlineMs);
  });
  try {
    return await Promise.race([work(client, sql), deadline]);
  } finally {
    clearTimeout(timer);
    client.end().catch(() => {});
  }
}

async function work(client: Client, sql: string): Promise<PgRun> {
  await client.connect();
  const started = performance.now();
  const res = await client.query({ text: sql, rowMode: "array" });
  return { columns: res.fields.map((f) => f.name), rows: res.rows as PgCell[][], ms: performance.now() - started };
}

// `57014` is query_canceled, what the role's statement_timeout raises.
export const isTimeout = (e: unknown): boolean =>
  e instanceof PgTimeout ||
  (e as { code?: string } | null)?.code === "57014" ||
  /timeout/i.test(String((e as Error | null)?.message));
