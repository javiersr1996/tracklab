import { describe, expect, it } from "vitest";
import {
  readsByFile,
  registry,
  viewSql,
  WAREHOUSE,
  type Read,
  type WarehouseManifest,
} from "../lib/warehouse/registry";

// The registry of task 42 (`lib/warehouse/registry.ts`): what the engine registers from
// `warehouse.json`, the views it creates, and how one query's requests add up per file.
//
// Mutations checked by hand (each restored byte for byte):
// - dropping the `FILE_NAME` check lets `x.parquet' ...` through, failing `refuses a name ...`;
// - charging a request to an unregistered URL to the first file (`?? files[0]`) fails
//   `keeps a request to anything else apart ...`;
// - summing spans without clipping the overlap (`total += b - a`) fails `counts a byte the
//   engine asked for twice once ...`.

const ORIGIN = "https://example.test";

const manifest = (tables: { table: string; file: string; bytes?: number }[]): WarehouseManifest => ({
  schema_version: 1,
  writer: {},
  tables: tables.map(({ table, file, bytes = 10 }) => ({
    table,
    sport: "both",
    file,
    rows: 1,
    columns: 1,
    order_by: [],
    row_groups: [],
    bytes,
    sha256: "",
  })),
});

describe("registry", () => {
  it("registers every table of warehouse.json under its file name, served from /data/warehouse", () => {
    const files = registry(WAREHOUSE, ORIGIN);
    expect(files.map((f) => f.table)).toEqual(WAREHOUSE.tables.map((t) => t.table));
    for (const [i, f] of files.entries()) {
      const t = WAREHOUSE.tables[i];
      expect(f).toEqual({ table: t.table, file: t.file, url: `${ORIGIN}/data/warehouse/${t.file}`, bytes: t.bytes });
    }
    expect(files.map((f) => f.table)).toEqual(
      expect.arrayContaining(["bb_shots", "bb_picks", "bb_drives", "fb_obr", "fb_passing", "fb_physical", "fact"]),
    );
  });

  it("writes one view per table over its registered file", () => {
    const [shots] = registry(manifest([{ table: "bb_shots", file: "bb_shots.38163f30.parquet" }]), ORIGIN);
    expect(viewSql(shots)).toBe("CREATE VIEW bb_shots AS SELECT * FROM read_parquet('bb_shots.38163f30.parquet')");
  });

  it("refuses a name that could break out of the SQL it is written into", () => {
    for (const bad of [
      { table: "bb_shots", file: "x.parquet') ; INSTALL httpfs; --" },
      { table: "bb_shots", file: "bb_shots.parquet" },
      { table: "bb_shots", file: "fact.00ed21c4.parquet" },
      { table: "bb shots", file: "bb shots.38163f30.parquet" },
      { table: "Fact", file: "Fact.00ed21c4.parquet" },
    ]) {
      expect(() => registry(manifest([bad]), ORIGIN), JSON.stringify(bad)).toThrow(/warehouse\.json/);
    }
    expect(() =>
      registry(
        manifest([
          { table: "fact", file: "fact.00ed21c4.parquet" },
          { table: "fact", file: "fact.00ed21c5.parquet" },
        ]),
        ORIGIN,
      ),
    ).toThrow(/listed twice/);
  });
});

describe("readsByFile", () => {
  const files = registry(
    manifest([
      { table: "bb_shots", file: "bb_shots.38163f30.parquet", bytes: 317195 },
      { table: "fact", file: "fact.00ed21c4.parquet", bytes: 745465 },
      { table: "fb_obr", file: "fb_obr.417337cd.parquet", bytes: 153775 },
    ]),
    ORIGIN,
  );
  const read = (file: string, range: string | null, bytes: number, method = "GET"): Read => ({
    url: `${ORIGIN}/data/warehouse/${file}`,
    method,
    range,
    status: 206,
    bytes,
  });

  it("adds up one query's requests per file, in registry order, leaving untouched files out", () => {
    const summary = readsByFile(
      [
        read("fact.00ed21c4.parquet", "bytes=0-0", 1),
        read("fact.00ed21c4.parquet", "bytes=0-", 0, "HEAD"),
        read("bb_shots.38163f30.parquet", "bytes=311296-317194", 5899),
        read("fact.00ed21c4.parquet", "bytes=737280-745464", 8185),
      ],
      files,
    );
    expect(summary.files).toEqual([
      {
        table: "bb_shots",
        file: "bb_shots.38163f30.parquet",
        fileBytes: 317195,
        bytes: 5899,
        distinctBytes: 5899,
        requests: 1,
        ranges: ["bytes=311296-317194"],
      },
      {
        table: "fact",
        file: "fact.00ed21c4.parquet",
        fileBytes: 745465,
        bytes: 8186,
        distinctBytes: 8186,
        requests: 3,
        ranges: ["bytes=0-0", "bytes=0-", "bytes=737280-745464"],
      },
    ]);
    expect([summary.bytes, summary.distinctBytes, summary.requests, summary.other]).toEqual([14085, 14085, 4, []]);
  });

  it("counts a byte the engine asked for twice once in distinctBytes, never past the file", () => {
    // The sequence measured on `SELECT * FROM bb_picks` (task 42): the footer read when the view
    // is created, then the scan asking again for ranges that overlap it.
    const picks = registry(manifest([{ table: "bb_picks", file: "bb_picks.89cc2992.parquet", bytes: 490408 }]), ORIGIN);
    const f = "bb_picks.89cc2992.parquet";
    const summary = readsByFile(
      [
        read(f, "bytes=0-0", 1),
        read(f, "bytes=0-", 0, "HEAD"),
        read(f, "bytes=475136-490407", 15272),
        read(f, "bytes=294912-311295", 16384),
        read(f, "bytes=311296-376831", 65536),
        read(f, "bytes=376832-490407", 113576),
        read(f, "bytes=0-16383", 16384),
        read(f, "bytes=16384-81919", 65536),
        read(f, "bytes=81920-344063", 262144),
      ],
      picks,
    );
    expect([summary.bytes, summary.distinctBytes, summary.requests]).toEqual([554833, 490408, 9]);
    // A whole-file GET (no Range) covers the file from its first byte.
    expect(readsByFile([read(f, null, 490408)], picks).distinctBytes).toBe(490408);
  });

  it("keeps a request to anything else apart instead of dropping it", () => {
    const stray: Read = { url: `${ORIGIN}/duckdb/ext/x.wasm`, method: "GET", range: null, status: 200, bytes: 99 };
    const summary = readsByFile([stray], files);
    expect([summary.files, summary.bytes, summary.requests, summary.other]).toEqual([[], 0, 0, [stray]]);
  });
});
