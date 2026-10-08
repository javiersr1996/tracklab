// `web/public/data/warehouse.json` (task 41), imported at build time like `lib/platform.ts`: the
// Parquet files the engine registers, the short names it gives them (`bb_shots`, `fact`, ...)
// and their sizes, so no file name or byte count is typed anywhere else.
import warehouseJson from "../../public/data/warehouse.json";

export interface WarehouseRowGroup {
  rows: number;
  min: string | number | null;
  max: string | number | null;
}

export interface WarehouseTable {
  table: string;
  sport: string;
  file: string;
  rows: number;
  columns: number;
  order_by: string[];
  row_groups: WarehouseRowGroup[];
  bytes: number;
  sha256: string;
}

export interface WarehouseManifest {
  schema_version: number;
  writer: Record<string, string | number>;
  tables: WarehouseTable[];
}

export const WAREHOUSE = warehouseJson as WarehouseManifest;

// One Parquet file as the engine sees it: `file` is the name it is registered under (and the
// only path the engine may open), `url` where it is served, `table` the view over it.
export interface RegisteredFile {
  table: string;
  file: string;
  url: string;
  bytes: number;
}

// Both names end up inside SQL (`CREATE VIEW <table> ... read_parquet('<file>')`), so they are
// checked here rather than quoted there: a short lowercase name, and `<table>.<sha8>.parquet`.
const TABLE_NAME = /^[a-z][a-z0-9_]*$/;
const FILE_NAME = /^([a-z][a-z0-9_]*)\.[0-9a-f]{8}\.parquet$/;

export function registry(manifest: WarehouseManifest, origin: string): RegisteredFile[] {
  const seen = new Set<string>();
  return manifest.tables.map(({ table, file, bytes }) => {
    if (!TABLE_NAME.test(table)) throw new Error(`warehouse.json: table name ${JSON.stringify(table)}`);
    if (seen.has(table)) throw new Error(`warehouse.json: table ${table} listed twice`);
    if (FILE_NAME.exec(file)?.[1] !== table) {
      throw new Error(`warehouse.json: file ${JSON.stringify(file)} for table ${table}`);
    }
    seen.add(table);
    return { table, file, url: `${origin}/data/warehouse/${file}`, bytes };
  });
}

export function viewSql({ table, file }: RegisteredFile): string {
  return `CREATE VIEW ${table} AS SELECT * FROM read_parquet('${file}')`;
}

// One HTTP request the engine's worker made, as recorded inside the worker (engine.ts).
export interface Read {
  url: string;
  method: string;
  range: string | null;
  status: number;
  bytes: number;
}

export interface FileReads {
  table: string;
  file: string;
  fileBytes: number;
  bytes: number;
  requests: number;
  ranges: (string | null)[];
}

export interface ReadSummary {
  files: FileReads[];
  bytes: number;
  requests: number;
  // Requests to anything that is not a registered file (none is expected once the engine is
  // ready; kept so a stray one is counted, not dropped).
  other: Read[];
}

// The requests of one query, per registered file, in registry order; files it did not touch
// are left out.
export function readsByFile(reads: Read[], files: RegisteredFile[]): ReadSummary {
  const byUrl = new Map(files.map((f) => [f.url, f]));
  const touched = new Map<string, FileReads>();
  const other: Read[] = [];
  for (const read of reads) {
    const file = byUrl.get(read.url);
    if (!file) {
      other.push(read);
      continue;
    }
    const entry = touched.get(file.url) ?? {
      table: file.table,
      file: file.file,
      fileBytes: file.bytes,
      bytes: 0,
      requests: 0,
      ranges: [],
    };
    entry.bytes += read.bytes;
    entry.requests += 1;
    entry.ranges.push(read.range);
    touched.set(file.url, entry);
  }
  const summary = files.flatMap((f) => touched.get(f.url) ?? []);
  return {
    files: summary,
    bytes: summary.reduce((total, f) => total + f.bytes, 0),
    requests: summary.reduce((total, f) => total + f.requests, 0),
    other,
  };
}
