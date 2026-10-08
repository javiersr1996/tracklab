import { sqlOf } from "../../../../lib/warehouse/pg";
import { isTimeout, runExample } from "../../../../lib/warehouse/pg-run";
import type { PgRouteAnswer } from "../../../../lib/warehouse/pg-types";

// Task 45. GET /api/warehouse/pg?id=<example>: runs the SQL of one example from
// `warehouse_pg.json`, the one place the SQL comes from. The request carries an id and nothing
// else: any other parameter, or a missing or unknown id, is a 400 before anything touches the
// database, and there is no POST. The connection is `DATABASE_URL` (the `warehouse_reader` role,
// which can read the warehouse schema and write none of it), a server variable that no client file
// reads; each query runs in a read-only transaction with its own statement_timeout (pg-run.ts).
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const NO_STORE = { "Cache-Control": "no-store" };

const answer = (body: PgRouteAnswer) => Response.json(body, { headers: NO_STORE });

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const id = params.get("id");
  const sql = [...params.keys()].length === 1 && id !== null ? sqlOf(id) : null;
  if (sql === null || id === null) {
    return Response.json({ error: "Ask with ?id=<example id> and nothing else." }, { status: 400, headers: NO_STORE });
  }
  // Without a database, say so without trying to connect.
  const dsn = process.env.DATABASE_URL;
  if (!dsn) return answer({ status: "absent" });
  try {
    return answer({ status: "live", id, ...(await runExample(dsn, sql)) });
  } catch (e) {
    // One line for the server log: the error's code or class, never its message, which can quote
    // the host, the user or a malformed piece of the connection string (review V of P4, B2).
    const { code, name } = (e ?? {}) as { code?: unknown; name?: unknown };
    console.error(`warehouse pg route: ${typeof code === "string" ? code : String(name ?? "error")}`);
    return answer({ status: isTimeout(e) ? "timeout" : "unavailable" });
  }
}
