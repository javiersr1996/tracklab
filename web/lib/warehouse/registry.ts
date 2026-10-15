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
  // Body bytes the engine received, summed over its requests.
  bytes: number;
  // Bytes of the file those requests covered, each counted once: no more than `fileBytes`.
  // The engine can ask twice for the same bytes in one query (the footer when a view is
  // created and again when it is scanned), so `bytes` can exceed the file.
  distinctBytes: number;
  requests: number;
  ranges: (string | null)[];
}

export interface ReadSummary {
  files: FileReads[];
  bytes: number;
  distinctBytes: number;
  requests: number;
  // Requests to anything that is not a registered file, kept apart from the files' figures.
  // None is expected once the engine is locked; the page does not show them, and
  // e2e/warehouse.spec.ts watches the network itself for a request to another origin.
  other: Read[];
}

// Where in the file a read's body sits: its Range from the first byte, or the start of the file
// when it had none (a whole-file GET). Bodiless reads (the HEAD) cover nothing.
function span(read: Read): [number, number] | null {
  if (read.bytes === 0) return null;
  const start = Number(read.range?.match(/^bytes=(\d+)-/)?.[1] ?? 0);
  return [start, start + read.bytes];
}

// Where each row group of a file sits in it: `start` to `end` is the byte span of its column
// chunks, read from the file's own footer (`parquet_metadata`, engine.ts).
export interface RowGroupSpan {
  start: number;
  end: number;
}

// How many row groups have bytes among those the engine fetched for `url`. Fetches come in
// whole blocks, so a group next to the one a query needs can overlap by the block's edge: this
// counts overlap, not decoding.
export function rowGroupsRead(groups: RowGroupSpan[], reads: Read[], url: string): number {
  const spans = reads
    .filter((r) => r.url === url)
    .map(span)
    .filter((s): s is [number, number] => s !== null);
  return groups.filter((g) => spans.some(([a, b]) => a < g.end && b > g.start)).length;
}

function covered(spans: [number, number][]): number {
  let total = 0;
  let end = 0;
  for (const [a, b] of [...spans].sort((x, y) => x[0] - y[0])) {
    if (b > end) {
      total += b - Math.max(a, end);
      end = b;
    }
  }
  return total;
}

// The requests of one query, per registered file, in registry order; files it did not touch
// are left out.
export function readsByFile(reads: Read[], files: RegisteredFile[]): ReadSummary {
  const byUrl = new Map(files.map((f) => [f.url, f]));
  const touched = new Map<string, FileReads>();
  const spans = new Map<string, [number, number][]>();
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
      distinctBytes: 0,
      requests: 0,
      ranges: [],
    };
    entry.bytes += read.bytes;
    entry.requests += 1;
    entry.ranges.push(read.range);
    touched.set(file.url, entry);
    const s = span(read);
    if (s) spans.set(file.url, [...(spans.get(file.url) ?? []), s]);
  }
  const summary = files.flatMap((f) => {
    const entry = touched.get(f.url);
    return entry ? [{ ...entry, distinctBytes: covered(spans.get(f.url) ?? []) }] : [];
  });
  const total = (key: "bytes" | "distinctBytes" | "requests") => summary.reduce((t, f) => t + f[key], 0);
  return {
    files: summary,
    bytes: total("bytes"),
    distinctBytes: total("distinctBytes"),
    requests: total("requests"),
    other,
  };
}
