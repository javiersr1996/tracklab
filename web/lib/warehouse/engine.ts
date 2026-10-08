import { useSyncExternalStore } from "react";
import type { AsyncDuckDB, AsyncDuckDBConnection } from "@duckdb/duckdb-wasm";
import { cellText } from "./cell";
import {
  readsByFile,
  registry,
  rowGroupsRead,
  viewSql,
  WAREHOUSE,
  type FileReads,
  type Read,
  type RegisteredFile,
  type RowGroupSpan,
} from "./registry";
import { checkSql } from "./sql";

// Task 42: one DuckDB-WASM instance per page, loaded only when a query is run (decision 5),
// over the Parquet files of `warehouse.json` read by HTTP range (decision 9: 1.32.0 opened with
// `forceFullHTTPReads: false`, engine and parquet extension served from this deployment).
//
// The page reads it through `useWarehouse()` (a `useSyncExternalStore` snapshot) and drives it
// with `run(sql)` and `dispose()`. Bytes and requests per query are counted inside the engine's
// own worker: a few lines run before DuckDB's worker script and record every request its
// XMLHttpRequest makes (URL, Range, status, body bytes). DuckDB's file statistics, the other
// candidate in decision 6, count 16 KiB blocks and no requests (task 38). The e2e checks these
// figures against the browser's Resource Timing inside the same worker, a separate path.
//
// Two caches sit between a query and the network, and the figures report what got through:
// the engine keeps in memory what it has read, so a query repeated on the same file can read 0
// bytes (it is duckdb-wasm's own file layer, not DuckDB's external file cache: with
// `enable_external_file_cache = false` the repeat still read 0 bytes when this was written);
// and Chrome's HTTP cache can serve part of a range it already holds, which Resource Timing then
// leaves out (e2e/warehouse.spec.ts).
//
// Each view (`bb_shots`, `fact`, ...) is created the first time a query names it, inside that
// query's measurement: creating it reads the file's footer, and creating all seven up front
// would read every footer before any query asked for one.

export type EngineState = "idle" | "loading" | "ready" | "error";
export type QueryState = "idle" | "running" | "done" | "error";

// Rows kept from a result; `rowCount` is the full count.
export const ROW_LIMIT = 1000;

export interface QueryResult {
  sql: string;
  columns: string[];
  // Each value as the text the table shows (`cellText`).
  rows: string[][];
  rowCount: number;
  // From the start of the query (views it needed included) to its result.
  ms: number;
  // Body bytes and requests to the registered Parquet files, all files together and per file;
  // `distinctBytes` counts each byte of a file once (`FileReads` in registry.ts).
  bytes: number;
  distinctBytes: number;
  requests: number;
  files: FileDetail[];
}

// A file's reads plus two things the panel has to say beside them: whether an earlier query of
// this visit had already touched the file (the engine keeps what it read, so these bytes are not
// a cold read), and how many of its row groups had bytes fetched.
export interface FileDetail extends FileReads {
  warm: boolean;
  rowGroups: { read: number; total: number };
}

export interface WarehouseSnapshot {
  engine: EngineState;
  query: QueryState;
  // Calls to `run` so far, rejected ones included: tells one run's outcome from the last one's.
  runs: number;
  // Encoded body bytes (Resource Timing) of the engine's worker script, .wasm and parquet
  // extension, once the engine is ready.
  engineBytes: number | null;
  versions: { package: string; duckdb: string } | null;
  result: QueryResult | null;
  error: string | null;
  // `EXPLAIN ANALYZE` of the last result's query, once asked for (`explain()`).
  plan: string | null;
}

const INITIAL: WarehouseSnapshot = {
  engine: "idle",
  query: "idle",
  runs: 0,
  engineBytes: null,
  versions: null,
  result: null,
  error: null,
  plan: null,
};

let snapshot = INITIAL;
const listeners = new Set<() => void>();

function update(patch: Partial<WarehouseSnapshot>): void {
  snapshot = { ...snapshot, ...patch };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const getSnapshot = () => snapshot;
const getServerSnapshot = () => INITIAL;

export function useWarehouse(): WarehouseSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export const TABLES = WAREHOUSE.tables.map((t) => t.table);

interface Report {
  reads: Read[];
  engine: { url: string; bytes: number }[];
}

interface Engine {
  conn: AsyncDuckDBConnection;
  files: RegisteredFile[];
  views: Set<string>;
  // Files an earlier query of this visit has read from.
  touched: Set<string>;
  report: () => Promise<Report>;
  serial: Serial;
}

type Serial = <T>(work: () => Promise<T>) => Promise<T>;

// One piece of work on the engine at a time. A query and an EXPLAIN each empty the request log
// when they start and read it when they end: two that overlapped (EXPLAIN ANALYZE and an example
// clicked together) took each other's requests, and the query showed a fraction of its reads.
function serializer(): Serial {
  let tail: Promise<unknown> = Promise.resolve();
  return (work) => {
    const next = tail.then(work);
    tail = next.catch(() => undefined);
    return next;
  };
}

// Runs inside the worker before DuckDB's own script. DuckDB reads files and loads extensions
// there with synchronous XMLHttpRequests (range reads, the GET and HEAD that open a file, the
// parquet extension; the .wasm itself comes through fetch); each one is logged when it ends. On "report" it hands the log over (and empties it) together with the
// Resource Timing of the engine files, which only this worker's timeline has.
function workerPrelude(channel: string, engineBase: string, workerUrl: string): string {
  return `
const reads = [];
const channel = new BroadcastChannel(${JSON.stringify(channel)});
channel.onmessage = (event) => {
  if (!event.data || event.data.type !== "report") return;
  const engine = performance.getEntriesByType("resource")
    .filter((e) => e.name.startsWith(${JSON.stringify(engineBase)}))
    .map((e) => ({ url: e.name, bytes: e.encodedBodySize }));
  channel.postMessage({ type: "reads", id: event.data.id, reads: reads.splice(0), engine });
};
const { open, setRequestHeader, send } = XMLHttpRequest.prototype;
XMLHttpRequest.prototype.open = function (method, url, ...rest) {
  this.__read = { url: String(url), method: String(method).toUpperCase(), range: null };
  return open.call(this, method, url, ...rest);
};
XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
  if (this.__read && String(name).toLowerCase() === "range") this.__read.range = String(value);
  return setRequestHeader.call(this, name, value);
};
XMLHttpRequest.prototype.send = function (body) {
  const read = this.__read;
  if (read) {
    this.addEventListener("loadend", () => {
      const r = this.response;
      const bytes = r instanceof ArrayBuffer ? r.byteLength : typeof r === "string" ? r.length : 0;
      reads.push({ ...read, status: this.status, bytes });
    }, { once: true });
  }
  return send.call(this, body);
};
importScripts(${JSON.stringify(workerUrl)});
`;
}

function reporter(channel: BroadcastChannel): () => Promise<Report> {
  let next = 0;
  const waiting = new Map<number, (report: Report) => void>();
  channel.onmessage = (event: MessageEvent) => {
    const { type, id, reads, engine } = event.data ?? {};
    if (type !== "reads") return;
    waiting.get(id)?.({ reads, engine });
    waiting.delete(id);
  };
  return () =>
    new Promise((resolve) => {
      const id = next++;
      waiting.set(id, resolve);
      channel.postMessage({ type: "report", id });
    });
}

// What `dispose()` has to stop, kept from the moment it exists (even mid-load).
let live: { worker: Worker; channel: BroadcastChannel } | null = null;
let engine: Promise<Engine> | null = null;
// Bumped by `dispose()`: work started before it no longer writes to the snapshot.
let generation = 0;

async function start(gen: number): Promise<Engine> {
  const duckdb = await import("@duckdb/duckdb-wasm");
  const origin = location.origin;
  const engineBase = `${origin}/duckdb/`;
  const dist = `${engineBase}${duckdb.PACKAGE_VERSION}`;
  const bundle = await duckdb.selectBundle({
    mvp: { mainModule: `${dist}/duckdb-mvp.wasm`, mainWorker: `${dist}/duckdb-browser-mvp.worker.js` },
    eh: { mainModule: `${dist}/duckdb-eh.wasm`, mainWorker: `${dist}/duckdb-browser-eh.worker.js` },
  });
  if (gen !== generation) throw new Error("disposed");

  const channelName = `tracklab-warehouse-${Math.random().toString(36).slice(2)}`;
  const script = URL.createObjectURL(
    new Blob([workerPrelude(channelName, engineBase, bundle.mainWorker!)], { type: "text/javascript" }),
  );
  const worker = new Worker(script);
  const channel = new BroadcastChannel(channelName);
  live = { worker, channel };
  const report = reporter(channel);

  const db: AsyncDuckDB = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(script);
  // Task 38: with the library's defaults every query downloads the whole file.
  await db.open({ filesystem: { forceFullHTTPReads: false } });
  const conn = await db.connect();
  // Task 38: parquet is not inside the .wasm; without its own repository the engine fetches
  // it from extensions.duckdb.org. scripts/copy-engine.mjs puts it on this deployment.
  await conn.query(`SET custom_extension_repository = '${engineBase}ext'`);
  await conn.query(`SET autoinstall_extension_repository = '${engineBase}ext'`);
  await conn.query("LOAD parquet");

  const files = registry(WAREHOUSE, origin);
  for (const f of files) await db.registerFileURL(f.file, f.url, duckdb.DuckDBDataProtocol.HTTP, false);
  // Locked from here on: the registered files are the only paths the engine may open (no
  // other URL, no extension, no attach, no copy), and no setting can be changed back.
  await conn.query(`SET allowed_paths = [${files.map((f) => `'${f.file}'`).join(", ")}]`);
  await conn.query("SET enable_external_access = false");
  await conn.query("SET lock_configuration = true");

  const { engine: engineFiles } = await report();
  if (gen !== generation) throw new Error("disposed");
  update({
    engine: "ready",
    engineBytes: engineFiles.reduce((total, f) => total + f.bytes, 0),
    versions: { package: duckdb.PACKAGE_VERSION, duckdb: await db.getVersion() },
  });
  return { conn, files, views: new Set(), touched: new Set(), report, serial: serializer() };
}

function ensureEngine(gen: number): Promise<Engine> {
  if (!engine) {
    update({ engine: "loading" });
    engine = start(gen);
    engine.catch(() => {
      if (gen !== generation) return;
      stop();
      update({ engine: "error" });
    });
  }
  return engine;
}

function stop(): void {
  live?.worker.terminate();
  live?.channel.close();
  live = null;
  engine = null;
}

const message = (error: unknown) => (error instanceof Error ? error.message : String(error));

// Runs one read-only statement. Rejected statements never load the engine.
export async function run(sql: string): Promise<void> {
  if (snapshot.query === "running") return;
  const runs = snapshot.runs + 1;
  const check = checkSql(sql, TABLES);
  if (!check.ok) {
    update({ query: "error", runs, error: check.reason, result: null, plan: null });
    return;
  }
  const gen = generation;
  update({ query: "running", runs, error: null, result: null, plan: null });
  try {
    const e = await ensureEngine(gen);
    const result = await e.serial(() => measure(e, sql, check.tables));
    if (gen !== generation) return;
    update({ query: "done", plan: null, result });
  } catch (error) {
    if (gen !== generation) return;
    update({ query: "error", error: message(error) });
  }
}

// One query, from an empty request log to its result and what it fetched per file.
async function measure(e: Engine, sql: string, tables: string[]): Promise<QueryResult> {
  await e.report(); // empties the log: what follows is this query's
  const started = performance.now();
  const table = await execute(e, sql, tables);
  const ms = performance.now() - started;
  const { reads } = await e.report();
  const { fields } = table.schema;
  const columns = fields.map((field) => field.name);
  const vectors = fields.map((_, i) => table.getChildAt(i)!);
  const kept = Math.min(table.numRows, ROW_LIMIT);
  const rows = Array.from({ length: kept }, (_, r) => vectors.map((v, i) => cellText(v.get(r), fields[i].type)));
  const summary = readsByFile(reads, e.files);
  const files: FileDetail[] = [];
  for (const f of summary.files) {
    const registered = e.files.find((r) => r.file === f.file)!;
    const groups = await rowGroupSpans(e, f.file);
    files.push({
      ...f,
      warm: e.touched.has(f.file),
      rowGroups: { read: rowGroupsRead(groups, reads, registered.url), total: groups.length },
    });
  }
  for (const f of files) e.touched.add(f.file);
  const { bytes, distinctBytes, requests } = summary;
  return { sql, columns, rows, rowCount: table.numRows, ms, bytes, distinctBytes, requests, files };
}

// Creates the views a query names and runs it. A query that fails can still have read a file
// (the footer its view reads, part of a scan), and the engine keeps those bytes: its files count
// as touched, so the next query on them is not presented as cold.
async function execute(e: Engine, sql: string, tables: string[]) {
  try {
    for (const f of e.files) {
      if (!tables.includes(f.table) || e.views.has(f.table)) continue;
      await e.conn.query(viewSql(f));
      e.views.add(f.table);
    }
    return await e.conn.query(sql);
  } catch (error) {
    const { reads } = await e.report();
    for (const f of readsByFile(reads, e.files).files) e.touched.add(f.file);
    throw error;
  }
}

// The byte span of every row group of a file, from its footer. The footer is already in the
// engine's memory (the query that just ran read it), and whatever this asks of the network is
// dropped from the log, so it does not count toward any query.
async function rowGroupSpans(e: Engine, file: string): Promise<RowGroupSpan[]> {
  const table = await e.conn.query(
    `SELECT min(coalesce(dictionary_page_offset, data_page_offset))::DOUBLE AS start,
            max(coalesce(dictionary_page_offset, data_page_offset) + total_compressed_size)::DOUBLE AS "end"
     FROM parquet_metadata('${file}') GROUP BY row_group_id ORDER BY row_group_id`,
  );
  await e.report();
  return Array.from({ length: table.numRows }, (_, i) => ({
    start: Number(table.getChildAt(0)!.get(i)),
    end: Number(table.getChildAt(1)!.get(i)),
  }));
}

// `EXPLAIN ANALYZE` of the last result's query, run once more on the same connection. The
// plan is DuckDB's own text; it describes this second execution, which the engine mostly serves
// from what it already holds.
export async function explain(): Promise<void> {
  const sql = snapshot.result?.sql;
  if (!sql || !engine || snapshot.query === "running") return;
  // The plan belongs to the result on screen: a query started meanwhile replaces both.
  const gen = generation;
  const runs = snapshot.runs;
  const current = () => gen === generation && runs === snapshot.runs;
  try {
    const e = await engine;
    const table = await e.serial(async () => {
      await e.report();
      const plan = await e.conn.query(`EXPLAIN ANALYZE ${sql}`);
      await e.report();
      return plan;
    });
    if (!current()) return;
    const last = table.numRows - 1;
    update({ plan: String(table.getChildAt(table.numCols - 1)!.get(last)) });
  } catch (error) {
    if (!current()) return;
    update({ plan: `EXPLAIN ANALYZE failed: ${message(error)}` });
  }
}

// Terminates the worker and forgets the engine: the page calls it when it unmounts.
export function dispose(): void {
  generation += 1;
  stop();
  snapshot = INITIAL;
  listeners.forEach((listener) => listener());
}
