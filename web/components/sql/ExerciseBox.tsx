"use client";

import { useState } from "react";
import { check, shapeVerdict, type Verdict, verdictText } from "../../lib/sql/check";
import type { Exercise } from "../../lib/sql/course";
import { cancel, type QueryResult, run, snapshot, useSqlEngine } from "../../lib/sql/engine";
import { wrap } from "../../lib/sql/normalize";
import { markSolved, useSolved } from "../../lib/sql/progress";

// One exercise of /sql (task 101). Run sends the reader's SQL through the read-only gate and the
// engine, shows the result as the console of /warehouse does (first 20 rows, every value as
// text) and, when its shape is the reference's, runs the wrapped query and compares the SHA-256
// of the normalized rows with course.json's. The expected rows are never shown. The hints come
// one at a time; "Show solution" prints the reference SQL, and the reader can still run it.
// `data-exercise` and `data-state` (idle, running, then the verdict or error) are what the e2e
// reads; the textarea is the textbox "SQL" and the button "Run".

const SHOWN_ROWS = 20;

type BoxState = "idle" | "running" | "error" | Verdict;

export function ExerciseBox({ exercise, n }: { exercise: Exercise; n: number }) {
  const s = useSqlEngine();
  const solved = useSolved().includes(exercise.id);
  const [sql, setSql] = useState("");
  const [state, setState] = useState<BoxState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [hintsShown, setHintsShown] = useState(0);
  const [solutionShown, setSolutionShown] = useState(false);

  // The engine holds one result at a time: the box keeps its own copy, and a run that another
  // box started first (the engine refuses a second) leaves this box as it was.
  async function go() {
    setState("running");
    setMessage(null);
    setResult(null);
    const before = snapshot().runs;
    await run(sql);
    const first = snapshot();
    if (first.runs !== before + 1) {
      setState("idle");
      return;
    }
    if (first.query !== "done" || !first.result) {
      setState("error");
      setMessage(first.error ?? "The query did not run.");
      return;
    }
    const display = first.result;
    setResult(display);
    const shape = { columns: display.columns.length, rowCount: display.rowCount };
    let verdict = shapeVerdict(exercise, shape);
    if (verdict === null) {
      await run(wrap(sql));
      const second = snapshot();
      if (second.query !== "done" || !second.result) {
        setState("error");
        setMessage(second.error ?? "The check did not run.");
        return;
      }
      verdict = await check(
        exercise,
        shape,
        second.result.rows.map((row) => row[0]),
      );
    }
    setState(verdict);
    setMessage(verdictText(verdict, exercise, shape));
    if (verdict === "correct") markSolved(exercise.id);
  }

  const running = s.query === "running";
  const mine = state === "running";
  return (
    <section
      className="sql-exercise"
      data-exercise={exercise.id}
      data-state={state}
      data-solved={solved}
      aria-labelledby={`${exercise.id}-h`}
    >
      <h3 id={`${exercise.id}-h`}>
        Exercise {n}
        {solved ? <span className="sql-solved"> · Solved</span> : null}
      </h3>
      <p>{exercise.prompt}</p>
      <textarea
        aria-label="SQL"
        rows={6}
        spellCheck={false}
        placeholder="Write your query here."
        value={sql}
        onChange={(event) => setSql(event.target.value)}
      />
      <p className="sql-exercise-buttons">
        <button type="button" className="primary" disabled={running} onClick={go}>
          Run
        </button>
        {mine && running ? (
          <button type="button" onClick={() => cancel()}>
            Cancel
          </button>
        ) : null}
        {hintsShown < exercise.hints.length ? (
          <button type="button" data-hint-button onClick={() => setHintsShown(hintsShown + 1)}>
            Show hint ({hintsShown + 1} of {exercise.hints.length})
          </button>
        ) : null}
        {solutionShown ? null : (
          <button type="button" data-solution-button onClick={() => setSolutionShown(true)}>
            Show solution
          </button>
        )}
      </p>
      {state === "error" ? (
        <p role="alert" data-message>
          {message}
        </p>
      ) : (
        <p role="status" aria-live="polite" data-message>
          {mine ? (s.engine === "ready" ? "Running." : "Loading the engine, then running.") : (message ?? "")}
        </p>
      )}
      {hintsShown > 0 ? (
        <ol className="sql-hints" data-hints>
          {exercise.hints.slice(0, hintsShown).map((hint, i) => (
            <li key={i}>{hint}</li>
          ))}
        </ol>
      ) : null}
      {solutionShown ? (
        <div data-solution>
          <pre>
            <code>{exercise.solution}</code>
          </pre>
          <p>
            <button type="button" data-use-solution onClick={() => setSql(exercise.solution)}>
              Put it in the editor
            </button>
          </p>
        </div>
      ) : null}
      {result ? (
        <>
          <div className="table-scroll">
            <table data-result>
              <thead>
                <tr>
                  {result.columns.map((c, i) => (
                    <th scope="col" key={i}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.slice(0, SHOWN_ROWS).map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p data-rows={result.rowCount}>
            {result.rowCount > SHOWN_ROWS
              ? `First ${SHOWN_ROWS} of ${result.rowCount.toLocaleString("en-US")} rows.`
              : `${result.rowCount.toLocaleString("en-US")} ${result.rowCount === 1 ? "row" : "rows"}.`}
          </p>
        </>
      ) : null}
    </section>
  );
}
