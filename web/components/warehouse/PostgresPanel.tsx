import { formatBytes } from "../../lib/format";
import type { QueryResult } from "../../lib/warehouse/engine";
import { CLIENT_LIMIT_MS, type PgAnswer } from "../../lib/warehouse/pg-client";
import type { PgCell, PgSnapshotExample, PgSnapshotSummary } from "../../lib/warehouse/pg-types";

// The Postgres half of /warehouse (task 45), beside the Parquet panel of the same example.
// `backend` is what `figure.warehouse[data-backend]` says: `running` while the route is asked,
// then `live` (Postgres answered the route), `snapshot` (it did not, in time) or `absent` (this
// deployment has no database configured: the console does not draw this panel). The buffers, the indexes and the execution time of the
// plan are always the snapshot's, measured when the data was loaded; only the rows and the
// milliseconds of the route are live.

export type PgState = { id: string; backend: "running" } | ({ id: string } & PgAnswer);

const stamp = (iso: string) => `${iso.slice(0, 16).replace("T", " ")} UTC`;
const text = (cell: PgCell) => (cell === null ? "" : String(cell));
const num = (n: number) => n.toLocaleString("en-US");

const WHY: Record<string, string> = {
  timeout: "Postgres did not answer in time",
  unavailable: "Postgres could not be reached",
  unreachable: "The page's own route could not be reached",
};

export function PostgresPanel({
  pg,
  summary,
  example,
  parquet,
}: {
  pg: PgState;
  summary: PgSnapshotSummary;
  example: PgSnapshotExample;
  parquet: QueryResult | null;
}) {
  const live = pg.backend === "live";
  const columns = live ? pg.columns : example.columns;
  const rows = live ? pg.rows : example.rows;
  const { source } = summary;
  const snapshotLine = `Snapshot of ${stamp(summary.measured_at)}: ${source.engine} ${source.version}, ${source.where} (warehouse_pg.json).`;
  // Where the plan was measured, also when the rows above are live from another Postgres.
  const planSource = `EXPLAIN (ANALYZE, BUFFERS) in warehouse_pg.json, ${stamp(summary.measured_at)}, ${source.where}`;
  return (
    <section data-pg-panel data-pg-source={live ? "live" : "snapshot"}>
      <h3>Postgres</h3>
      {pg.backend === "running" ? <p>Asking Postgres, for up to {CLIENT_LIMIT_MS / 1000} seconds.</p> : null}
      {pg.backend === "live" ? (
        <p>
          Live: Postgres answered this page&apos;s own route in {pg.ms.toFixed(1)} ms (the query alone, as the
          route measured it; the connection is not in it).
        </p>
      ) : null}
      {pg.backend === "snapshot" ? (
        <p data-pg-why>
          {WHY[pg.reason]}: the backend may be asleep, down or not configured, so the table below is the
          snapshot. {snapshotLine}
        </p>
      ) : null}

      {pg.backend === "running" ? null : (
        <div className="table-scroll">
          <table data-pg-result>
            <thead>
              <tr>
                {columns.map((c, i) => (
                  <th scope="col" key={i}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{text(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {parquet !== null && pg.backend !== "running" ? (
        <>
          <h4>Side by side</h4>
          <p>
            Two engines on two models of the same data (wide Parquet files, a dimensional schema), so these are
            figures to read, not a ranking.
          </p>
          <div className="table-scroll">
            <table data-pg-compare>
              <thead>
                <tr>
                  <th scope="col">side</th>
                  <th scope="col">figure</th>
                  <th scope="col">value</th>
                  <th scope="col">source</th>
                </tr>
              </thead>
              <tbody>
                {parquet.files.map((f) => (
                  <tr key={f.file} data-side="parquet" data-figure="bytes">
                    <td>Parquet</td>
                    <td>{f.table}: bytes fetched, row groups with fetched bytes</td>
                    <td>
                      {formatBytes(f.distinctBytes)} of {formatBytes(f.fileBytes)}; {f.rowGroups.read} of{" "}
                      {f.rowGroups.total}
                    </td>
                    <td>DuckDB-WASM, this visit; row groups from warehouse.json</td>
                  </tr>
                ))}
                <tr data-side="parquet" data-figure="ms">
                  <td>Parquet</td>
                  <td>time in the browser</td>
                  <td>{Math.round(parquet.ms)} ms</td>
                  <td>DuckDB-WASM, this visit</td>
                </tr>
                <tr data-side="postgres" data-figure="buffers">
                  <td>Postgres</td>
                  <td>shared buffers, hit and read ({num(source.block_size)} B blocks)</td>
                  <td>
                    {num(example.shared_hit_blocks)} and {num(example.shared_read_blocks)}
                  </td>
                  <td>{planSource}</td>
                </tr>
                <tr data-side="postgres" data-figure="indexes">
                  <td>Postgres</td>
                  <td>indexes used; tables read in full</td>
                  <td>
                    {example.indexes.length > 0 ? example.indexes.join(", ") : "none"};{" "}
                    {example.seq_scans.length > 0 ? example.seq_scans.join(", ") : "none"}
                  </td>
                  <td>{planSource}</td>
                </tr>
                <tr data-side="postgres" data-figure="ms">
                  <td>Postgres</td>
                  <td>execution time of the plan</td>
                  <td>{example.execution_ms} ms</td>
                  <td>{planSource}</td>
                </tr>
                {live ? (
                  <tr data-side="postgres" data-figure="live-ms">
                    <td>Postgres</td>
                    <td>time of this answer</td>
                    <td>{pg.ms.toFixed(1)} ms</td>
                    <td>the route, this visit</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}
