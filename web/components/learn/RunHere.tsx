"use client";

import { useEffect, useState } from "react";
import { formatBytes } from "../../lib/format";
import { learnEngine, type LearnQuery } from "../../lib/learn/engine";

// "Run it here" (task 85): the lesson's query, run in this browser by DuckDB-WASM on the files the
// page already reads. `figure.run-here` carries what the e2e reads: `data-engine`, `data-query`,
// `data-run` (calls to Run, to tell one result from the last), the engine's bytes, the data's bytes
// and requests, and the rows. Nothing of the engine is fetched until Run. Every value from the
// engine is shown as text: React escapes it, and nothing here sets HTML.

const SHOWN_ROWS = 20;

export function RunHere({ query, sql }: { query: LearnQuery; sql: string }) {
  const [engine] = useState(() => learnEngine(query));
  const s = engine.useSnapshot();
  const [text, setText] = useState(sql);
  // The worker lives as long as the lesson that started it.
  useEffect(() => () => engine.dispose(), [engine]);

  const r = s.result;
  const running = s.query === "running";
  return (
    <figure
      className="run-here"
      data-engine={s.engine}
      data-query={s.query}
      data-run={s.runs}
      data-bytes-engine={s.engineBytes ?? undefined}
      data-bytes-data={r?.bytes}
      data-requests={r?.requests}
      data-rows={r?.rowCount}
      data-error={s.error ?? undefined}
    >
      <textarea aria-label="SQL" rows={Math.min(18, text.split("\n").length + 1)} spellCheck={false} value={text} onChange={(event) => setText(event.target.value)} />
      <p>
        <button type="button" className="primary" disabled={running} onClick={() => engine.run(text)}>
          Run
        </button>
        {running ? (
          <>
            {" "}
            <button type="button" onClick={() => engine.cancel()}>
              Cancel
            </button>
          </>
        ) : null}
      </p>
      {s.error ? <p role="alert">{s.error}</p> : null}
      <p aria-live="polite">
        {s.engineBytes === null
          ? running
            ? "Loading the engine."
            : "Nothing is downloaded until Run."
          : `Engine: ${formatBytes(s.engineBytes)} (the worker and the WebAssembly, at their encoded size), fetched once for this lesson.`}
        {r ? ` Data: ${formatBytes(r.bytes)} read from the lesson's files in ${r.requests} requests; ${r.rowCount} ${r.rowCount === 1 ? "row" : "rows"} in ${Math.round(r.ms)} ms.` : ""}
      </p>
      {r ? (
        <div className="table-scroll">
          <table data-result>
            <thead>
              <tr>
                {r.columns.map((c, i) => (
                  <th key={i} scope="col">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {r.rows.slice(0, SHOWN_ROWS).map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} data-column={r.columns[j]}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </figure>
  );
}
