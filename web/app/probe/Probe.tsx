"use client";

import { useSyncExternalStore } from "react";

// Task 38 probe. The page measures what only the engine knows (rows, milliseconds, its
// own file statistics, the row group byte spans of each file) and writes it to data-*
// attributes; the spec adds what only the network knows and writes the report.

// Three ways to load the same engine. `self_defaults` is what a naive integration gets:
// duckdb-wasm's own defaults. `self_ranges` keeps everything on this deployment (engine
// and parquet extension) and turns off forced full HTTP reads. `jsdelivr_ranges` takes
// the engine from jsDelivr and leaves the extension to its default repository.
const VARIANTS = {
  self_defaults: { engine: "self", extensions: "default", filesystem: null },
  self_ranges: { engine: "self", extensions: "self", filesystem: { forceFullHTTPReads: false } },
  jsdelivr_ranges: { engine: "jsdelivr", extensions: "default", filesystem: { forceFullHTTPReads: false } },
} as const;
type Variant = keyof typeof VARIANTS;
type State = "idle" | "running" | "done" | "error";

interface Measure {
  target: string;
  query: string;
  url: string;
  rows: number;
  ms: number;
  resultSha: string;
  firstRow: string;
  stats: string;
}

interface Snapshot {
  state: State;
  variant: Variant | null;
  error: string | null;
  packageVersion: string | null;
  duckdbVersion: string | null;
  bundle: string | null;
  msInstantiate: number | null;
  msExtension: number | null;
  statsShape: string | null;
  measures: Measure[];
  spans: Record<string, (number | string | null)[][]>;
}

const TARGETS = [
  { id: "picks_rg1", path: "/data/probe/picks_rg1.parquet", kind: "picks", key: "team_id" },
  { id: "picks_rg64", path: "/data/probe/picks_rg64.parquet", kind: "picks", key: "team_id" },
  { id: "fact_rg1", path: "/data/probe/fact_rg1.parquet", kind: "fact", key: "metric" },
  { id: "fact_rg10k", path: "/data/probe/fact_rg10k.parquet", kind: "fact", key: "metric" },
  { id: "fact_rg50k", path: "/data/warehouse/fact.00ed21c4.parquet", kind: "fact", key: "metric" },
] as const;

const QUERIES = {
  picks: [
    {
      id: "projection",
      sql: "SELECT player_name, team_name, handler_total_picks FROM read_parquet('{file}') ORDER BY ALL",
    },
    {
      id: "team",
      sql: "SELECT player_name, games_played, handler_total_picks FROM read_parquet('{file}') WHERE team_id = 1331 ORDER BY ALL",
    },
    {
      id: "percentile",
      sql: "SELECT quantile_cont(handler_total_picks, 0.9) AS p90, count(*) AS n FROM read_parquet('{file}') WHERE team_id IS NOT NULL",
    },
  ],
  fact: [
    {
      id: "metric_percentile",
      sql: "SELECT quantile_cont(value, 0.9) AS p90, count(*) AS n FROM read_parquet('{file}') WHERE metric = 'handler_ppp' AND NOT is_season_total",
    },
  ],
} as const;

const INITIAL: Snapshot = {
  state: "idle",
  variant: null,
  error: null,
  packageVersion: null,
  duckdbVersion: null,
  bundle: null,
  msInstantiate: null,
  msExtension: null,
  statsShape: null,
  measures: [],
  spans: {},
};

let snapshot = INITIAL;
const listeners = new Set<() => void>();

function update(patch: Partial<Snapshot>): void {
  snapshot = { ...snapshot, ...patch };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const getSnapshot = () => snapshot;
const getServerSnapshot = () => INITIAL;

const json = (value: unknown) =>
  JSON.stringify(value, (_, v) => (typeof v === "bigint" ? v.toString() : v));

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function run(variant: Variant): Promise<void> {
  const { engine: source, extensions, filesystem } = VARIANTS[variant];
  update({ ...INITIAL, state: "running", variant });
  try {
    const duckdb = await import("@duckdb/duckdb-wasm");
    const self = `${location.origin}/duckdb/${duckdb.PACKAGE_VERSION}`;
    const bundles: import("@duckdb/duckdb-wasm").DuckDBBundles =
      source === "self"
        ? {
            mvp: {
              mainModule: `${self}/duckdb-mvp.wasm`,
              mainWorker: `${self}/duckdb-browser-mvp.worker.js`,
            },
            eh: {
              mainModule: `${self}/duckdb-eh.wasm`,
              mainWorker: `${self}/duckdb-browser-eh.worker.js`,
            },
          }
        : duckdb.getJsDelivrBundles();
    const bundle = await duckdb.selectBundle(bundles);
    // A worker cannot be built from another origin: jsDelivr goes through a blob that
    // imports it, as the duckdb-wasm README does.
    const workerUrl =
      source === "self"
        ? bundle.mainWorker!
        : URL.createObjectURL(
            new Blob([`importScripts(${JSON.stringify(bundle.mainWorker)});`], {
              type: "text/javascript",
            }),
          );
    const started = performance.now();
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(workerUrl));
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    if (filesystem) await db.open({ filesystem });
    const msInstantiate = performance.now() - started;
    if (source === "jsdelivr") URL.revokeObjectURL(workerUrl);
    const conn = await db.connect();
    if (extensions === "self") {
      // duckdb-wasm 1.32.0 autoloads parquet; point it at the copy on this deployment.
      await conn.query(`SET custom_extension_repository = '${location.origin}/duckdb/ext'`);
      await conn.query(`SET autoinstall_extension_repository = '${location.origin}/duckdb/ext'`);
    }
    // Loaded before the first measured query, so its fetch is not counted as a query's.
    const extensionStarted = performance.now();
    await conn.query("LOAD parquet");
    const msExtension = performance.now() - extensionStarted;
    update({
      packageVersion: duckdb.PACKAGE_VERSION,
      duckdbVersion: await db.getVersion(),
      bundle: bundle.mainModule,
      msInstantiate,
      msExtension,
    });

    const measures: Measure[] = [];
    const spans: Record<string, (number | string | null)[][]> = {};
    for (const target of TARGETS) {
      for (const query of QUERIES[target.kind]) {
        // One name and one URL per (file, query): neither DuckDB's metadata cache nor the
        // browser's HTTP cache carries bytes from one measurement into the next, and the
        // spec can tell each query's requests apart by the `m` parameter.
        const name = `${target.id}.${query.id}.parquet`;
        const url = `${location.origin}${target.path}?m=${target.id}.${query.id}`;
        await db.registerFileURL(name, url, duckdb.DuckDBDataProtocol.HTTP, false);
        await db.collectFileStatistics(name, true);
        const t0 = performance.now();
        const table = await conn.query(query.sql.replace("{file}", name));
        const ms = performance.now() - t0;
        // The worker posts a FileStatistics, so it arrives as a structured clone without
        // its methods (getBlockStats is gone): the block counters are decoded here, three
        // bytes per block, the low and high nibbles that getBlockStats reads.
        const stats = await db.exportFileStatistics(name);
        if (!snapshot.statsShape) {
          update({
            statsShape: json({
              keys: Object.keys(stats),
              getBlockStats: typeof (stats as { getBlockStats?: unknown }).getBlockStats,
              blockStatsBytes: stats.blockStats.length,
            }),
          });
        }
        const blocks: number[][] = [];
        for (let i = 0; i < Math.floor(stats.blockStats.length / 3); i++) {
          const [b0, b1] = [stats.blockStats[i * 3], stats.blockStats[i * 3 + 1]];
          const [cold, ahead, cached] = [b0 >> 4, b1 & 15, b1 >> 4];
          if (cold || ahead || cached) blocks.push([i, cold, ahead, cached]);
        }
        const rows = table.toArray().map((row) => row.toJSON());
        measures.push({
          target: target.id,
          query: query.id,
          url,
          rows: rows.length,
          ms,
          resultSha: await sha256(json(rows)),
          firstRow: json(rows[0] ?? null),
          stats: json({
            totalFileReadsCold: stats.totalFileReadsCold,
            totalFileReadsAhead: stats.totalFileReadsAhead,
            totalFileReadsCached: stats.totalFileReadsCached,
            totalPageAccesses: stats.totalPageAccesses,
            totalPageLoads: stats.totalPageLoads,
            blockSize: stats.blockSize,
            blocks,
          }),
        });
        update({ measures: [...measures] });
      }
      // Byte span of each row group, and the min and max of the filtered column, from the
      // footer, under a name and URL of its own so reading it is counted against no query.
      const meta = `${target.id}.meta.parquet`;
      await db.registerFileURL(
        meta,
        `${location.origin}${target.path}?m=${target.id}.meta`,
        duckdb.DuckDBDataProtocol.HTTP,
        false,
      );
      const footer = await conn.query(
        `SELECT row_group_id, min(coalesce(dictionary_page_offset, data_page_offset)) AS start,
                max(coalesce(dictionary_page_offset, data_page_offset) + total_compressed_size) AS stop,
                max(stats_min_value) FILTER (WHERE path_in_schema = '${target.key}') AS key_min,
                max(stats_max_value) FILTER (WHERE path_in_schema = '${target.key}') AS key_max
         FROM parquet_metadata('${meta}') GROUP BY row_group_id ORDER BY row_group_id`,
      );
      spans[target.id] = footer
        .toArray()
        .map((r) => [Number(r.row_group_id), Number(r.start), Number(r.stop), r.key_min, r.key_max]);
    }
    await conn.close();
    update({ state: "done", measures, spans });
  } catch (error) {
    update({ state: "error", error: error instanceof Error ? error.message : String(error) });
  }
}

export function Probe() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const busy = s.state === "running";
  return (
    <figure
      className="probe"
      data-state={s.state}
      data-variant={s.variant ?? undefined}
      data-package-version={s.packageVersion ?? undefined}
      data-duckdb-version={s.duckdbVersion ?? undefined}
      data-bundle={s.bundle ?? undefined}
      data-ms-instantiate={s.msInstantiate ?? undefined}
      data-ms-extension={s.msExtension ?? undefined}
      data-stats-shape={s.statsShape ?? undefined}
      data-spans={s.state === "done" ? json(s.spans) : undefined}
      data-error={s.error ?? undefined}
    >
      <p>
        {(Object.keys(VARIANTS) as Variant[]).map((v) => (
          <button key={v} type="button" data-run={v} disabled={busy} onClick={() => run(v)}>
            Run {v}
          </button>
        ))}
      </p>
      <figcaption>
        {s.state}
        {s.error ? `: ${s.error}` : ""}
      </figcaption>
      <table>
        <thead>
          <tr>
            <th scope="col">file</th>
            <th scope="col">query</th>
            <th scope="col">rows</th>
            <th scope="col">ms</th>
          </tr>
        </thead>
        <tbody>
          {s.measures.map((m) => (
            <tr
              key={`${m.target}.${m.query}`}
              data-target={m.target}
              data-query={m.query}
              data-url={m.url}
              data-rows={m.rows}
              data-ms={m.ms}
              data-result-sha={m.resultSha}
              data-first-row={m.firstRow}
              data-stats={m.stats}
            >
              <td>{m.target}</td>
              <td>{m.query}</td>
              <td>{m.rows}</td>
              <td>{m.ms.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
