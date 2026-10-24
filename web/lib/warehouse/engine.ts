import { createEngine, type EngineSnapshot } from "../duckdb/engine";
import { registry, viewSql, WAREHOUSE } from "./registry";

// Task 42: the DuckDB-WASM engine of /warehouse, over the Parquet files of `warehouse.json` read by
// HTTP range (decision 9: 1.32.0 opened with `forceFullHTTPReads: false`, engine and parquet
// extension served from this deployment). Since task 85 it is one instance of the shared engine
// (`lib/duckdb/engine.ts`), and this module keeps the API the console was written against.
//
// Each view (`bb_shots`, `fact`, ...) is created the first time a query names it, inside that
// query's measurement: creating it reads the file's footer, and creating all seven up front
// would read every footer before any query asked for one.

export {
  ROW_LIMIT,
  type EngineState,
  type FileDetail,
  type QueryResult,
  type QueryState,
} from "../duckdb/engine";
export type WarehouseSnapshot = EngineSnapshot;

export const TABLES = WAREHOUSE.tables.map((t) => t.table);

const warehouse = createEngine({
  name: "warehouse",
  tables: TABLES,
  open: (origin) => {
    const files = registry(WAREHOUSE, origin);
    return { files, views: files.map((f) => ({ table: f.table, sql: viewSql(f) })) };
  },
  extensions: ["parquet"],
});

export const useWarehouse = warehouse.useSnapshot;
export const { run, explain, cancel, dispose } = warehouse;
