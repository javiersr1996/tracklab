"use client";

import { useEffect } from "react";
import { formatBytes } from "../../lib/format";
import type { Exercise } from "../../lib/sql/course";
import { dispose, useSqlEngine } from "../../lib/sql/engine";
import { ExerciseBox } from "./ExerciseBox";

// The exercises of a lesson around the one engine of /sql: a line on the engine (nothing is
// fetched until the first Run; the worker lives as long as the lesson that started it) and one
// box per exercise.
export function Exercises({ exercises }: { exercises: Exercise[] }) {
  const s = useSqlEngine();
  useEffect(() => () => dispose(), []);
  return (
    <section className="sql-exercises" aria-labelledby="exercises-h" data-engine={s.engine}>
      <h2 id="exercises-h">Exercises</h2>
      <p>
        Write each query in its box and press Run: your SQL runs in this browser, in DuckDB compiled to
        WebAssembly, on the Parquet files of the warehouse, and the checker compares the shape and the
        values of your result with the reference. Nothing is sent anywhere.{" "}
        {s.engineBytes === null
          ? "Nothing is downloaded until the first Run."
          : `Engine: ${formatBytes(s.engineBytes)}, fetched once for this lesson.`}
      </p>
      {exercises.map((e, i) => (
        <ExerciseBox key={e.id} exercise={e} n={i + 1} />
      ))}
    </section>
  );
}
