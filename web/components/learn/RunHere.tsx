"use client";

import { useEffect, useRef, useState } from "react";
import { formatBytes } from "../../lib/format";
import { learnEngine, type LearnQuery } from "../../lib/learn/engine";
import { expose } from "../../lib/learn/expose";
import { reproduced, type Reproduced } from "../../lib/learn/reproduce";

// "Run it here" (tasks 85 and 86): the lesson's query, run in this browser by DuckDB-WASM on the
// files the page already reads, and each row it returns set against the figure of that name on
// the page. `figure.run-here` carries what the e2e reads: `data-engine`, `data-query`, `data-run`
// (calls to Run, to tell one result from the last), the engine's bytes, the data's bytes and
// requests, the rows, and `data-matched` of `data-figures` once a result is compared. Nothing of
// the engine is fetched until Run. Every value from the engine is shown as text: React escapes it,
// and nothing here sets HTML.

const SHOWN_ROWS = 20;

export function RunHere({ query, views, sql }: { query: LearnQuery; views: string; sql: string }) {
  const [engine] = useState(() => learnEngine(query));
  const s = engine.useSnapshot();
  const [text, setText] = useState(sql);
  const [rows, setRows] = useState<Reproduced[] | null>(null);
  const root = useRef<HTMLElement>(null);
  // The worker lives as long as the lesson that started it.
  useEffect(() => () => engine.dispose(), [engine]);

  // What the page prints for a figure, outside this box.
  const printed = (figure: string) =>
    Array.from(document.querySelectorAll(`[data-fig="${CSS.escape(figure)}"]`))
      .filter((el) => !root.current?.contains(el))
      .map((el) => (el.textContent ?? "").trim());

  async function go() {
    setRows(null);
    await engine.run(text);
    const r = engine.snapshot().result;
    const compared = r ? reproduced(r.columns, r.rows, printed) : null;
    setRows(compared);
    if (compared) expose({ reproduce: { rows: compared, matched: compared.filter((x) => x.matched).length, n: compared.length } });
  }

  const r = s.result;
  const running = s.query === "running";
  const matched = rows?.filter((x) => x.matched).length;
  return (
    <figure
      ref={root}
      className="run-here"
      data-engine={s.engine}
      data-query={s.query}
      data-run={s.runs}
      data-bytes-engine={s.engineBytes ?? undefined}
      data-bytes-data={r?.bytes}
      data-requests={r?.requests}
      data-rows={r?.rowCount}
      data-matched={matched}
      data-figures={rows?.length}
      data-error={s.error ?? undefined}
    >
      <details>
        <summary>The views the query reads</summary>
        <pre>
          <code>{views}</code>
        </pre>
      </details>
      <textarea aria-label="SQL" rows={Math.min(18, text.split("\n").length + 1)} spellCheck={false} value={text} onChange={(event) => setText(event.target.value)} />
      <p>
        <button type="button" className="primary" disabled={running} onClick={go}>
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
          : `Engine: ${formatBytes(s.engineBytes)} (the worker, the WebAssembly and the JSON extension, at their encoded size), fetched once for this lesson.`}
        {r ? ` Data: ${formatBytes(r.bytes)} read from the lesson's files in ${r.requests} requests; ${r.rowCount} ${r.rowCount === 1 ? "row" : "rows"} in ${Math.round(r.ms)} ms.` : ""}
      </p>
      {rows ? (
        <p data-reproduce>
          Matches the figures above: {matched} of {rows.length}.
        </p>
      ) : null}
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
                <tr key={i} data-matched={rows?.[i]?.matched}>
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
