import { createEngine } from "../duckdb/engine";
import { registry, viewSql, WAREHOUSE } from "../warehouse/registry";
import scoutingJson from "../../public/data/scouting.json";

// The engine of /warehouse/scouting (task 135): one instance of the shared engine
// (`lib/duckdb/engine.ts`) with only the parquet extension, over the six wide tables of
// `scouting.json` (the long `fact` table is left out: it is sorted by metric, so two players
// would touch all its row groups). Nothing is fetched until the first query.

export { ROW_LIMIT, type EngineSnapshot, type QueryResult } from "../duckdb/engine";

const SCOUTING_TABLES = scoutingJson.tables.map((t) => t.table);

const scouting = createEngine({
  name: "scouting",
  tables: SCOUTING_TABLES,
  open: (origin) => {
    const files = registry(WAREHOUSE, origin).filter((f) => SCOUTING_TABLES.includes(f.table));
    return { files, views: files.map((f) => ({ table: f.table, sql: viewSql(f) })) };
  },
  extensions: ["parquet"],
});

export const useScoutingEngine = scouting.useSnapshot;
export const { run, cancel, dispose, snapshot } = scouting;
