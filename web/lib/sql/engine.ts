import { createEngine } from "../duckdb/engine";
import { registry, viewSql, WAREHOUSE } from "../warehouse/registry";

// The engine of /sql (task 101): one instance of the shared engine (`lib/duckdb/engine.ts`) over
// the seven Parquet files of `warehouse.json`, the same views by the same names as /warehouse,
// plus the json extension the checker's wrapper needs (`json_array`, task 98: /warehouse's own
// instance loads only parquet and does not change). Both extensions are served from this
// deployment (`scripts/copy-engine.mjs`). Nothing is fetched until the first query, and the
// reader's SQL goes through the same read-only gate as /warehouse's.

export { ROW_LIMIT, type EngineSnapshot, type QueryResult } from "../duckdb/engine";

export const TABLES = WAREHOUSE.tables.map((t) => t.table);

const sql = createEngine({
  name: "sql",
  tables: TABLES,
  open: (origin) => {
    const files = registry(WAREHOUSE, origin);
    return { files, views: files.map((f) => ({ table: f.table, sql: viewSql(f) })) };
  },
  extensions: ["parquet", "json"],
});

export const useSqlEngine = sql.useSnapshot;
export const { run, cancel, dispose, snapshot } = sql;
