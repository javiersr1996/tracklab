// The Postgres side of /warehouse (task 45): `warehouse_pg.json` (task 44), which holds the SQL
// of each example on the dimensional model and what Postgres answered and measured when the
// data was loaded. The route imports this file for the SQL and never takes SQL from a request;
// the page gets `summary()`, the same file without the SQL and the plans, as props.
import snapshotJson from "../../public/data/warehouse_pg.json";
import type { PgSnapshotExample, PgSnapshotSummary } from "./pg-types";

interface PgSnapshotFile {
  measured_at: string;
  source: PgSnapshotSummary["source"];
  database_bytes: number;
  examples: (PgSnapshotExample & { sql: string; planning_ms: number; plan: unknown })[];
}

const SNAPSHOT = snapshotJson as unknown as PgSnapshotFile;

// A Map, so an id like `constructor` or `__proto__` is not found.
const SQL_BY_ID = new Map(SNAPSHOT.examples.map((e) => [e.id, e.sql]));

export const exampleIds = (): string[] => [...SQL_BY_ID.keys()];

// The SQL the route runs for an id, or null when the id is not an example.
export const sqlOf = (id: string): string | null => SQL_BY_ID.get(id) ?? null;

export function summary(): PgSnapshotSummary {
  const { measured_at, source } = SNAPSHOT;
  return {
    measured_at,
    source,
    examples: SNAPSHOT.examples.map(
      ({ id, columns, rows, execution_ms, shared_hit_blocks, shared_read_blocks, indexes, seq_scans }) => ({
        id,
        columns,
        rows,
        execution_ms,
        shared_hit_blocks,
        shared_read_blocks,
        indexes,
        seq_scans,
      }),
    ),
  };
}
