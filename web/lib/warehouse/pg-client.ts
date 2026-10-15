// The browser's side of task 45: ask the page's own route for an example, and give up after
// CLIENT_LIMIT_MS. The route's limits (connect 2 s, deadline 3 s) sit inside this one, so a
// Postgres that is asleep or down turns into the snapshot instead of a spinner. Every way of not
// getting a live answer, including a blocked or never-answered request, ends as a value.
import type { PgCell, PgRouteAnswer } from "./pg-types";

export const CLIENT_LIMIT_MS = 4000;

export type PgAnswer =
  | { backend: "live"; columns: string[]; rows: PgCell[][]; ms: number }
  | { backend: "absent" }
  | { backend: "snapshot"; reason: "timeout" | "unavailable" | "unreachable" };

export async function askPostgres(id: string, signal: AbortSignal): Promise<PgAnswer> {
  try {
    const res = await fetch(`/api/warehouse/pg?id=${encodeURIComponent(id)}`, {
      signal: AbortSignal.any([signal, AbortSignal.timeout(CLIENT_LIMIT_MS)]),
      cache: "no-store",
    });
    if (!res.ok) return { backend: "snapshot", reason: "unreachable" };
    const body = (await res.json()) as PgRouteAnswer;
    if (body.status === "live") return { backend: "live", columns: body.columns, rows: body.rows, ms: body.ms };
    if (body.status === "absent") return { backend: "absent" };
    return { backend: "snapshot", reason: body.status };
  } catch (e) {
    // The caller's own abort (a newer question) is theirs to tell apart.
    if (signal.aborted) throw e;
    return { backend: "snapshot", reason: (e as Error).name === "TimeoutError" ? "timeout" : "unreachable" };
  }
}
