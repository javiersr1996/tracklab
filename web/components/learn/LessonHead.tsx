import { Fragment, type ReactNode } from "react";
import { LESSONS, type Level } from "../../lib/learn/series";
import { Count } from "../home/Count";
import { PageHead } from "../site/Band";

// One line of a lesson's result panel (task 112): what it is, one value or a range of two, and the
// unit. Each value is one the lesson already prints, from its published JSON; none is typed.
export interface Readout {
  label: string;
  values: readonly number[];
  unit?: string;
}

// The panel beside the head: the lesson's key result, its first line counting up as it comes into
// view (a still number under reduced motion and on the server), and what the lesson teaches, the
// sentence the index prints under its title. A figure, so the lessons' digit checks leave it out.
function ResultPanel({ n, result }: { n: number; result: readonly Readout[] }) {
  const about = LESSONS.find((l) => l.n === n)?.about;
  return (
    <figure className="head-panel" data-head-panel="result">
      <figcaption className="head-panel-label">The result</figcaption>
      <dl className="head-readouts">
        {result.map((r, i) => (
          <div key={r.label} className={i === 0 ? "head-readout head-readout-main" : "head-readout"}>
            <dt>{r.label}</dt>
            <dd data-head-readout={i}>
              {r.values.map((v, j) => (
                <Fragment key={j}>
                  {j > 0 ? <span className="head-to"> to </span> : null}
                  {i === 0 ? <Count value={v} kind="num" /> : <span>{String(v)}</span>}
                </Fragment>
              ))}
              {/* As the lessons print them: a degree sign on the number, any other unit after a space. */}
              {r.unit === "°" ? "°" : r.unit ? <span className="head-unit">{`\u00a0${r.unit}`}</span> : null}
            </dd>
          </div>
        ))}
      </dl>
      {about ? (
        <p className="head-panel-about">
          <span className="head-panel-about-label">What you learn</span> {about}
        </p>
      ) : null}
    </figure>
  );
}

// The head of a lesson: its place in the series, the question as the h1, then the lede.
export function LessonHead({
  n,
  title,
  level,
  result,
  children,
}: {
  n: number;
  title: string;
  level: Level;
  result: readonly Readout[];
  children?: ReactNode;
}) {
  return (
    <PageHead eyebrow="Learn" aside={<ResultPanel n={n} result={result} />}>
      <p className="lesson-meta">
        Lesson <span data-series-n={n}>{n}</span> · {level}
      </p>
      <h1>{title}</h1>
      {children}
    </PageHead>
  );
}
