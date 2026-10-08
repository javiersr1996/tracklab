"use client";

import { useEffect, useState } from "react";
import { formatBytes } from "../../lib/format";
import { dispose, explain, run, useWarehouse } from "../../lib/warehouse/engine";
import { EXAMPLES } from "../../lib/warehouse/examples";
import { WAREHOUSE } from "../../lib/warehouse/registry";

// The console of /warehouse (task 43) around the engine of task 42. `figure.warehouse` carries
// what the e2e reads: `data-engine`, `data-query`, `data-run` (calls to `run`, to tell one
// result from the last), `data-example` (the example whose SQL was run, empty once the text is
// edited), the byte and request counts, one `li[data-file]` per Parquet file the query touched.
// Nothing of the engine is fetched until a query is run, by "Run", an example or a column list.
// Every value from the engine is shown as text: React escapes it, and nothing here sets HTML.

const SHOWN_ROWS = 20;

export function Console() {
  const s = useWarehouse();
  const [sql, setSql] = useState(EXAMPLES.find((e) => e.id === "fact")!.sql);
  const [example, setExample] = useState("");
  // The worker lives as long as the page that started it.
  useEffect(() => dispose, []);

  const r = s.result;
  const current = EXAMPLES.find((e) => e.id === example);
  const noRead = r !== null && r.requests === 0;
  const listing = r !== null && r.rowCount === 0;
  return (
    <figure
      className="warehouse"
      data-engine={s.engine}
      data-query={s.query}
      data-run={s.runs}
      data-example={example}
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
      <div className="warehouse-buttons" role="group" aria-label="Example queries">
        {EXAMPLES.map((e) => (
          <button
            type="button"
            key={e.id}
            data-example-button={e.id}
            disabled={s.query === "running"}
            onClick={() => {
              setSql(e.sql);
              setExample(e.id);
              run(e.sql);
            }}
          >
            {e.label}
          </button>
        ))}
      </div>
      <p>{current ? current.about : "Pick an example, or write a SELECT of your own."}</p>
      <textarea
        aria-label="SQL"
        rows={9}
        spellCheck={false}
        value={sql}
        onChange={(event) => {
          setSql(event.target.value);
          setExample("");
        }}
      />
      <p>
        <button type="button" disabled={s.query === "running"} onClick={() => run(sql)}>
          Run
        </button>
      </p>
      <div className="warehouse-buttons" role="group" aria-label="List the columns of a table">
        <span>Columns of</span>
        {WAREHOUSE.tables.map((t) => (
          <button
            type="button"
            key={t.table}
            data-columns-button={t.table}
            disabled={s.query === "running"}
            onClick={() => {
              const text = `SELECT * FROM ${t.table} LIMIT 0`;
              setSql(text);
              setExample("");
              run(text);
            }}
          >
            {t.table}
          </button>
        ))}
      </div>

      {s.error ? <p role="alert">{s.error}</p> : null}

      <h3>Engine</h3>
      <p>
        {s.engineBytes === null
          ? "Not loaded: nothing of the engine is downloaded until a query runs."
          : `${formatBytes(s.engineBytes)} transferred once for this visit (the worker, the WebAssembly and the Parquet extension), before the first query and not counted in any query below.`}
        {s.versions ? ` duckdb-wasm ${s.versions.package}, DuckDB ${s.versions.duckdb}.` : ""}
      </p>

      <h3>Data</h3>
      {r === null ? (
        <p>Run a query to see what it fetched from the Parquet files.</p>
      ) : (
        <>
          <p>Query that ran:</p>
          <div className="warehouse-scroll">
            <pre data-sql>{r.sql}</pre>
          </div>
          {noRead ? (
            <p data-cached>
              This query fetched nothing from the network: the engine already held every byte it
              needed from an earlier query in this visit, so 0 B here is not what it costs cold.
              Reload the page to measure it from empty.
            </p>
          ) : (
            <p>
              {formatBytes(r.distinctBytes)} of Parquet fetched ({formatBytes(r.bytes)} requested,
              the engine asks twice for some bytes) in {r.requests.toLocaleString("en-US")} requests,
              {" "}
              {r.rowCount.toLocaleString("en-US")} {r.rowCount === 1 ? "row" : "rows"} in{" "}
              {Math.round(r.ms)} ms. This browser, this visit: a repeat of the same query reads
              less.
            </p>
          )}
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
                data-warm={f.warm}
                data-row-groups-read={f.rowGroups.read}
                data-row-groups-total={f.rowGroups.total}
              >
                {f.table}: {formatBytes(f.distinctBytes)} of {formatBytes(f.fileBytes)} (
                {formatBytes(f.bytes)} requested) in {f.requests} requests; row groups with fetched
                bytes: {f.rowGroups.read} of {f.rowGroups.total}
                {f.warm ? "; an earlier query had already read this file, so some bytes were held" : ""}
              </li>
            ))}
          </ul>
          <p>
            <button
              type="button"
              data-explain
              disabled={s.query === "running" || /^\s*explain\b/i.test(r.sql)}
              onClick={() => explain()}
            >
              EXPLAIN ANALYZE
            </button>
          </p>
          {s.plan ? (
            <div className="warehouse-scroll">
              <pre data-plan>{s.plan}</pre>
            </div>
          ) : null}
          {listing ? (
            <p data-columns>
              {r.columns.length.toLocaleString("en-US")} columns: {r.columns.join(", ")}
            </p>
          ) : (
            <>
              <h3>Result</h3>
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
                          <td key={j}>{value}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {r.rowCount > SHOWN_ROWS ? (
                <p>
                  First {SHOWN_ROWS} of {r.rowCount.toLocaleString("en-US")} rows.
                </p>
              ) : null}
            </>
          )}
        </>
      )}
    </figure>
  );
}
