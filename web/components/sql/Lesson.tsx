import Link from "next/link";
import { Band, PageHead } from "../site/Band";
import { courseLesson, exampleCell, SQL_LESSONS, type SqlSlug, sqlHref, sqlLessonMeta } from "../../lib/sql/course";
import { Exercises } from "./Exercises";
import { QueryPanel } from "./QueryPanel";
import { PROSE } from "./lessons";

// A lesson of /sql: the head, the prose (its numbers from the lesson's facts), the worked
// example with its result as `tracklab sql course` ran it, the exercises, and the way on.
export function Lesson({ slug }: { slug: SqlSlug }) {
  const meta = sqlLessonMeta(slug);
  const lesson = courseLesson(slug);
  const Prose = PROSE[slug];
  const prev = SQL_LESSONS.find((l) => l.n === meta.n - 1);
  const next = SQL_LESSONS.find((l) => l.n === meta.n + 1);
  // The head panel's answer: the first and the last cell of the example's first row, as the table
  // below prints them.
  const { columns, rows } = lesson.example;
  const first = rows[0];
  const answer = `${exampleCell(first[0])} · ${exampleCell(first[first.length - 1])}`;
  const note = `${columns[0]} · ${columns[columns.length - 1]}, row 1 of ${rows.length.toLocaleString("en-US")}`;
  return (
    <main id="main" className={`page lesson sql-lesson sql-${slug}`}>
      <PageHead eyebrow="Learn SQL" aside={<QueryPanel sql={lesson.example.sql} answer={answer} note={note} />}>
        <p className="lesson-meta">
          Lesson <span data-series-n={meta.n}>{meta.n}</span> of {SQL_LESSONS.length} · {meta.concept}
        </p>
        <h1>{meta.title}</h1>
        <p className="lede">{meta.about}</p>
      </PageHead>
      <Band>
        <Prose />

        <section aria-labelledby="example-h">
          <h2 id="example-h">Worked example</h2>
          <p>
            The query and its result, as the build ran it on the warehouse. The result tables in this
            course scroll sideways on a phone.
          </p>
          <pre>
            <code data-example-sql>{lesson.example.sql}</code>
          </pre>
          <div className="table-scroll">
            <table data-example>
              <thead>
                <tr>
                  {lesson.example.columns.map((c, i) => (
                    <th scope="col" key={i}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lesson.example.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j}>{exampleCell(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            {lesson.example.rows.length.toLocaleString("en-US")} {lesson.example.rows.length === 1 ? "row" : "rows"}.
          </p>
        </section>

        <Exercises exercises={lesson.exercises} />

        <nav className="sql-pager" aria-label="Lessons">
          <p>
            {prev ? (
              <Link href={sqlHref(prev.slug)} rel="prev">
                Previous: {prev.title}
              </Link>
            ) : null}
            {prev ? " · " : ""}
            <Link href="/sql">All lessons</Link>
            {next ? " · " : ""}
            {next ? (
              <Link href={sqlHref(next.slug)} rel="next">
                Next: {next.title}
              </Link>
            ) : null}
          </p>
        </nav>
      </Band>
    </main>
  );
}
