import type { Metadata } from "next";
import Link from "next/link";
import { Band, PageHead } from "../../components/site/Band";
import { SketchPanel } from "../../components/site/SketchPanel";
import { learnMetadata } from "../../lib/learn/metadata";
import { LESSONS, LEVELS, lessonHref } from "../../lib/learn/series";

export const metadata: Metadata = learnMetadata;

// The lesson on the EuroLeague's counts, named by its place in the catalog.
const EURO = LESSONS.find((l) => l.slug === "expected-points");

export default function LearnPage() {
  return (
    <main id="main" className="page">
      <PageHead eyebrow="Learn" aside={<SketchPanel href="/learn" label="A flight of the ball" />}>
        <h1>Learn from the tracking data</h1>
        <p className="lede">
          Each lesson starts from one question about SkillCorner&apos;s open tracking data, or, in lesson {EURO?.n}, about
          the EuroLeague&apos;s published shot counts, works the idea on the published data, and ends with its figures
          and the query or script that reproduces them. The lessons are grouped by level, and each names the sport
          whose data it uses.
        </p>
        <p>
          The lessons end in SQL. If you have not written any, <Link href="/sql">Learn SQL on the warehouse</Link>{" "}
          starts from <code>SELECT</code> and ends with window functions and CTEs, with exercises checked in the
          browser.
        </p>
      </PageHead>
      <Band>
        {LEVELS.map((level) => {
          const lessons = LESSONS.filter((l) => l.level === level);
          return lessons.length === 0 ? null : (
            <section key={level} className="lesson-group" aria-labelledby={`level-${level}`}>
              <h2 id={`level-${level}`} className="lesson-level">
                {level}
              </h2>
              <ol className="lessons">
                {lessons.map((l) => (
                  <li key={l.slug} data-lesson={l.slug} data-status={l.status}>
                    <p className="lesson-meta">
                      Lesson <span data-series-n={l.n}>{l.n}</span> · {l.sport}
                    </p>
                    <h3>{l.status === "published" ? <Link href={lessonHref(l)}>{l.title}</Link> : l.title}</h3>
                    <p>{l.about}</p>
                    {l.status === "published" ? null : <p className="lesson-status">In preparation</p>}
                  </li>
                ))}
              </ol>
            </section>
          );
        })}
      </Band>
    </main>
  );
}
