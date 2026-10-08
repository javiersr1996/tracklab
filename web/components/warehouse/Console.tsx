"use client";

import { useEffect, useState } from "react";
import { formatBytes } from "../../lib/format";
import { dispose, run, useWarehouse } from "../../lib/warehouse/engine";

// Task 42: the engine on the page, driven by state. `figure.warehouse` carries what the e2e
// reads (`data-engine`, `data-query`, `data-run`, `data-bytes-engine`, `data-bytes-query`,
// `data-bytes-distinct`, `data-requests`, `data-rows`), one `li[data-file]` per Parquet file the query touched, and
// nothing of the engine is fetched until "Run" is pressed. Task 43 builds the console around it.

// The percentile query task 38 measured on the long fact: it reads by range and skips row groups.
const DEFAULT_SQL =
  "SELECT quantile_cont(value, 0.9) AS p90, count(*) AS n\nFROM fact\nWHERE metric = 'handler_ppp' AND NOT is_season_total";

const SHOWN_ROWS = 20;

const cell = (value: unknown) => (value === null || value === undefined ? "NULL" : String(value));

export function Warehouse() {
  const s = useWarehouse();
  const [sql, setSql] = useState(DEFAULT_SQL);
  // The worker lives as long as the page that started it.
  useEffect(() => dispose, []);

  const r = s.result;
  return (
    <figure
      className="warehouse"
      data-engine={s.engine}
      data-query={s.query}
      data-run={s.runs}
      data-bytes-engine={s.engineBytes ?? undefined}
      data-bytes-query={r?.bytes}
      data-bytes-distinct={r?.distinctBytes}
      data-requests={r?.requests}
      data-rows={r?.rowCount}
      data-ms={r === null ? undefined : Math.round(r.ms)}
      data-package-version={s.versions?.package}
      data-duckdb-version={s.versions?.duckdb}
      data-error={s.error ?? undefined}
    >
      <textarea
        aria-label="SQL"
        rows={5}
        spellCheck={false}
        value={sql}
        onChange={(event) => setSql(event.target.value)}
      />
      <p>
        <button type="button" disabled={s.query === "running"} onClick={() => run(sql)}>
          Run
        </button>
      </p>
      <figcaption>
        Engine: {s.engine}
        {s.engineBytes === null ? "" : `, ${formatBytes(s.engineBytes)} transferred`}
        {s.versions ? ` (duckdb-wasm ${s.versions.package}, DuckDB ${s.versions.duckdb})` : ""}. Query:{" "}
        {s.query}
        {r
          ? `, ${r.rowCount.toLocaleString("en-US")} rows in ${Math.round(r.ms)} ms, ${formatBytes(r.distinctBytes)} of Parquet read (${formatBytes(r.bytes)} requested) in ${r.requests} requests`
          : ""}
        .
      </figcaption>
      {s.error ? <p role="alert">{s.error}</p> : null}
      {r ? (
        <>
          <ul>
            {r.files.map((f) => (
              <li
                key={f.file}
                data-file={f.file}
                data-table={f.table}
                data-bytes={f.bytes}
                data-bytes-distinct={f.distinctBytes}
                data-requests={f.requests}
                data-file-bytes={f.fileBytes}
              >
                {f.table}: {formatBytes(f.distinctBytes)} of {formatBytes(f.fileBytes)} ({formatBytes(f.bytes)} requested) in{" "}
                {f.requests} requests
              </li>
            ))}
          </ul>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {r.columns.map((c, i) => (
                    <th scope="col" key={i}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {r.rows.slice(0, SHOWN_ROWS).map((row, i) => (
                  <tr key={i}>
                    {row.map((value, j) => (
                      <td key={j}>{cell(value)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </figure>
  );
}
