import type { Metadata } from "next";
import Link from "next/link";
import { Band, PageHead } from "../../components/site/Band";
import { SketchPanel } from "../../components/site/SketchPanel";
import { SolvedCount } from "../../components/sql/SolvedCount";
import { courseLesson, SQL_LESSONS, sqlHref } from "../../lib/sql/course";
import { sqlMetadata } from "../../lib/sql/metadata";
import { WAREHOUSE } from "../../lib/warehouse/registry";

export const metadata: Metadata = sqlMetadata;

// One line per table of the warehouse; the row and column counts come from warehouse.json.
const TABLES: Record<string, string> = {
  bb_shots: "Basketball shooting per player and team: attempts, makes, threes, points, by zone.",
  bb_drives: "Basketball drives to the basket per player and team.",
  bb_picks: "Basketball pick-and-roll actions per player and team, as handler and as screener.",
  fb_physical: "Football physical output per player, team and position group: minutes, distances, sprints, peak speed.",
  fb_passing: "Football passing per player, team and position group: passes and completion.",
  fb_obr: "Football off-ball runs per player, team and position group.",
  fact: "Every metric of the six tables above as one long table: sport, family, player, team, position, metric, value.",
};

export default function SqlPage() {
  return (
    <main className="page sql-index">
      <PageHead eyebrow="Learn SQL" aside={<SketchPanel href="/sql" label="A query, typed" />}>
        <h1>Learn SQL on the warehouse</h1>
        <p className="lede">
          Eight lessons that take you from your first <code>SELECT</code> to window functions and CTEs. Each
          answers a question about the tables of <Link href="/warehouse">the warehouse</Link>, SkillCorner&apos;s
          season aggregates for basketball and football, and ends with exercises that are checked in your
          browser: DuckDB runs your query here, nothing is sent anywhere, and no account is needed. Written for
          an aspiring football or basketball analyst who has not written SQL yet.
        </p>
      </PageHead>
      <Band>
        <section aria-labelledby="tables-h">
          <h2 id="tables-h">The tables</h2>
          <ul className="sql-tables">
            {WAREHOUSE.tables.map((t) => (
              <li key={t.table} data-table={t.table}>
                <code>{t.table}</code>: {TABLES[t.table] ?? ""} {t.rows.toLocaleString("en-US")} rows,{" "}
                {t.columns.toLocaleString("en-US")} columns.
              </li>
            ))}
          </ul>
          <p>
            Each query in the lessons goes through the same read-only gate as the console of the warehouse: one{" "}
            <code>SELECT</code> or <code>WITH</code> at a time, nothing written, nothing fetched from elsewhere.
          </p>
        </section>

        <section aria-labelledby="lessons-h">
          <h2 id="lessons-h">The lessons</h2>
          <ol className="lessons sql-lessons">
            {SQL_LESSONS.map((l) => {
              const ids = courseLesson(l.slug).exercises.map((e) => e.id);
              return (
                <li key={l.slug} data-lesson={l.slug}>
                  <p className="lesson-meta">
                    Lesson <span data-series-n={l.n}>{l.n}</span> · {l.concept}
                  </p>
                  <h3>
                    <Link href={sqlHref(l.slug)}>{l.title}</Link>
                  </h3>
                  <p>{l.about}</p>
                  <p className="lesson-meta">
                    <SolvedCount ids={ids} />
                  </p>
                </li>
              );
            })}
          </ol>
          <p>
            Progress is kept in this browser only. The lessons of <Link href="/learn">Learn</Link> pick up where
            this course ends: each of them closes with a query you can run.
          </p>
        </section>
      </Band>
    </main>
  );
}
