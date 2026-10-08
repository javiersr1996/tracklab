// Runs one example's SQL on Postgres for the route of task 45 (server only: the driver is `pg`,
// node-postgres 8.23.1, which Next keeps out of the client bundle).
//
// Driver: `pg`, because it speaks the plain wire protocol to Neon over TCP in the Node runtime,
// is the most used Node driver, and takes a hard `query_timeout`. Neon's serverless driver
// (WebSocket or HTTP) buys nothing for a Node function, and `postgres` adds nothing `pg` lacks
// for five fixed queries.
//
// Limits, innermost first: the transaction's own, READ ONLY and `SET LOCAL statement_timeout`
// (STATEMENT_TIMEOUT_MS, the 2 s of decision 7), the connection timeout, and a deadline over
// connect and query together, after which the connection is closed. The role's defaults (read
// only, 2 s, task 44) are not relied on: any role can change its own (review V of P4, M1). `SET
// LOCAL` lives inside the transaction, so it holds through a pooler in transaction mode.
import { Client, types } from "pg";
import type { PgCell } from "./pg-types";

export const STATEMENT_TIMEOUT_MS = 2000;
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
  // One round trip for both. No COMMIT: the transaction ends when `runExample` closes the connection.
  await client.query(`BEGIN READ ONLY; SET LOCAL statement_timeout = ${STATEMENT_TIMEOUT_MS}`);
  const started = performance.now();
  const res = await client.query({ text: sql, rowMode: "array" });
  return { columns: res.fields.map((f) => f.name), rows: res.rows as PgCell[][], ms: performance.now() - started };
}

// `57014` is query_canceled, what the statement_timeout raises.
export const isTimeout = (e: unknown): boolean =>
  e instanceof PgTimeout ||
  (e as { code?: string } | null)?.code === "57014" ||
  /timeout/i.test(String((e as Error | null)?.message));
