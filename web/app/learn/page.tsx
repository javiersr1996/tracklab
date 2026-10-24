import Link from "next/link";
import { Band, PageHead } from "../../components/site/Band";
import { LESSONS, lessonHref } from "../../lib/learn/series";

export default function LearnPage() {
  return (
    <main className="page">
      <PageHead eyebrow="Learn">
        <h1>Learn from the tracking data</h1>
        <p className="lede">
          Short lessons that each start from a question about the data, work the idea with the
          published frames, and end with a figure per match and the query that reproduces it.
        </p>
      </PageHead>
      <Band>
        <ol className="lessons">
          {LESSONS.map((l) => (
            <li key={l.slug} data-lesson={l.slug} data-status={l.status}>
              <p className="lesson-meta">
                Lesson <span data-series-n={l.n}>{l.n}</span> · {l.level}
              </p>
              <h2>{l.status === "published" ? <Link href={lessonHref(l)}>{l.title}</Link> : l.title}</h2>
              <p>{l.about}</p>
              {l.status === "published" ? null : <p className="lesson-status">In preparation</p>}
            </li>
          ))}
        </ol>
      </Band>
    </main>
  );
}
