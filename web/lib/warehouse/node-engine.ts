// DuckDB in Node, at build time, over the warehouse's Parquet files as /warehouse publishes them
// (task 184a): the same engine the console runs in the browser (`@duckdb/duckdb-wasm`, its blocking
// Node build), the same views (`CREATE VIEW <table> AS SELECT * FROM read_parquet(...)`) and the
// parquet extension pinned by scripts/copy-engine.mjs, so a page can draw what a query of the
// console returns without publishing anything new. Only a server component or a test imports this.
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import type * as Blocking from "@duckdb/duckdb-wasm/blocking";
import { WAREHOUSE } from "./registry";

export type Row = Record<string, string | number | boolean | null>;

const WEB = process.cwd();
const slash = (path: string) => path.split("\\").join("/");

// duckdb-wasm in Node fetches an extension it has not cached in ~/.duckdb with fetch() on a worker
// thread, which cannot read a local file and then never returns; where XMLHttpRequest exists it asks
// that instead, synchronously. For the one LOAD, a stand-in serves the pinned file under the
// extension repository and nothing else, and is removed before anything else can run.
function loadParquet(conn: Blocking.DuckDBConnection, repository: string): void {
  const scope = globalThis as { XMLHttpRequest?: unknown };
  const before = scope.XMLHttpRequest;
  class DiskRequest {
    status = 0;
    response: ArrayBuffer | null = null;
    responseType = "";
    private url = "";
    open(_method: string, url: string) {
      this.url = url;
    }
    setRequestHeader() {}
    send() {
      if (!this.url.startsWith(`${repository}/`) || !existsSync(this.url)) {
        this.status = 404;
        return;
      }
      const bytes = readFileSync(this.url);
      this.response = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
      this.status = 200;
    }
  }
  scope.XMLHttpRequest = DiskRequest;
  try {
    conn.query("LOAD parquet");
  } finally {
    if (before === undefined) delete scope.XMLHttpRequest;
    else scope.XMLHttpRequest = before;
  }
}

async function open(): Promise<(sql: string) => Row[]> {
  const require = createRequire(join(WEB, "package.json"));
  const duckdb = require("@duckdb/duckdb-wasm/blocking") as typeof Blocking;
  const bundles = {
    mvp: { mainModule: require.resolve("@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm"), mainWorker: "" },
    eh: { mainModule: require.resolve("@duckdb/duckdb-wasm/dist/duckdb-eh.wasm"), mainWorker: "" },
  };
  const db = await duckdb.createDuckDB(bundles, new duckdb.VoidLogger(), duckdb.NODE_RUNTIME);
  await db.instantiate(() => {});
  const conn = db.connect();
  // Nothing is fetched: an extension the engine does not have fails instead of downloading.
  conn.query("SET autoinstall_known_extensions = false");
  conn.query("SET autoload_known_extensions = false");
  const repository = slash(join(WEB, "public", "duckdb", "ext"));
  const platform = (await duckdb.getPlatformFeatures()).wasmExceptions ? "wasm_eh" : "wasm_mvp";
  const extension = `${repository}/${db.getVersion()}/${platform}/parquet.duckdb_extension.wasm`;
  if (!existsSync(extension)) throw new Error(`${extension} is missing: scripts/copy-engine.mjs writes it before a build`);
  conn.query(`SET custom_extension_repository = '${repository}'`);
  loadParquet(conn, repository);
  for (const t of WAREHOUSE.tables) {
    // The names go into SQL: checked as registry.ts checks them for the browser.
    if (!/^[a-z][a-z0-9_]*$/.test(t.table) || t.file !== `${t.table}.${t.sha256.slice(0, 8)}.parquet`) throw new Error(`warehouse.json: ${t.table}`);
    conn.query(`CREATE VIEW ${t.table} AS SELECT * FROM read_parquet('${slash(join(WEB, "public", "data", "warehouse", t.file))}')`);
  }
  // BIGINT comes back as a bigint; every count here fits a number.
  return (sql) =>
    conn
      .query(sql)
      .toArray()
      .map((r) =>
        Object.fromEntries(Object.entries(r.toJSON() as Record<string, unknown>).map(([k, v]) => [k, typeof v === "bigint" ? Number(v) : (v as Row[string])])),
      );
}

let engine: Promise<(sql: string) => Row[]> | null = null;

// The rows a query of the warehouse returns; the engine opens once per process.
export async function queryWarehouse(sql: string): Promise<Row[]> {
  engine ??= open();
  return (await engine)(sql);
}
