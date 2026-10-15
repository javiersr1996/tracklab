// Shapes shared by the page, the route and the client that asks it. Types only: nothing here
// pulls the snapshot or the driver into the browser's bundle.

export type PgCell = string | number | null;

export interface PgSnapshotExample {
  id: string;
  columns: string[];
  rows: PgCell[][];
  execution_ms: number;
  shared_hit_blocks: number;
  shared_read_blocks: number;
  indexes: string[];
  seq_scans: string[];
}

export interface PgSnapshotSummary {
  measured_at: string;
  source: { engine: string; version: string; where: string; where_id: string; block_size: number };
  examples: PgSnapshotExample[];
}

// What the route answers to a well-formed request. Only a malformed one gets an error status
// (400): a browser logs every other non-2xx response as a console error, and a deployment
// without a database is a normal state, not a failure.
export type PgRouteAnswer =
  | { status: "live"; id: string; columns: string[]; rows: PgCell[][]; ms: number }
  | { status: "absent" | "timeout" | "unavailable" };
