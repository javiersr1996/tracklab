import type { Metadata } from "next";
import Link from "next/link";
import { Stack } from "../../components/platform/Stack";
import { Band, PageHead } from "../../components/site/Band";
import { AUTHOR, REPO, TAKEDOWN_CONTACT } from "../../lib/sections";

export const metadata: Metadata = {
  title: "About | Track Lab",
  description: `Track Lab is a personal, non-commercial learning project in data engineering on open sports tracking data, by ${AUTHOR.name}.`,
};

// What the project shows, each with the page that shows it. The lines say what the pages and the
// code say (Flow.tsx's layer lines, the sections' own text); no figure.
const SHOWS = [
  {
    title: "Ingest with pinned hashes",
    text: "Each SkillCorner file comes from a pinned commit with its sha256; a file already on disk with the right hash is verified, not downloaded again.",
    href: "/engineering#sources",
  },
  {
    title: "Bronze, silver and gold with DuckDB and dbt",
    text: "One typed Parquet per match in bronze, then dbt on DuckDB conforms football and basketball into one silver schema, and gold is a dimensional model.",
    href: "/engineering",
  },
  {
    title: "Orchestration with Dagster",
    text: "The layers are assets of one Dagster graph, raw to publish, with the numbers the latest build produced.",
    href: "/engineering#lineage",
  },
  {
    title: "Data quality",
    text: "dbt tests, contract tests on the built Parquet and --check commands that recompute each published file, plus a calibration kit for the two bundles.",
    href: "/engineering/quality",
  },
  {
    title: "A warehouse in your browser",
    text: "A dimensional warehouse queried by DuckDB-WASM in this browser, on Parquet files read by HTTP range.",
    href: "/warehouse",
  },
  {
    title: "A Canvas renderer",
    text: "One renderer for both sports replays curated possessions in the browser.",
    href: "/tracking/replay",
  },
  {
    title: "Lessons",
    text: "Short lessons that start from a question about the tracking data and end with a query you can run, and an SQL course on the warehouse.",
    href: "/learn",
  },
] as const;

const mailto = (address: string) => `mailto:${address}`;

export default function AboutPage() {
  return (
    <main id="main" className="page about">
      <PageHead
        eyebrow="About"
        aside={
          <aside className="head-panel about-author" data-about-author>
            <p className="head-panel-label">Made by</p>
            <p className="about-author-name">{AUTHOR.name}</p>
            <ul className="about-author-links">
              <li>
                <a href={AUTHOR.linkedin}>LinkedIn</a>
              </li>
              <li>
                <a href={REPO}>GitHub repository</a>
              </li>
              <li>
                <a href={mailto(AUTHOR.email)}>{AUTHOR.email}</a>
              </li>
            </ul>
          </aside>
        }
      >
        <h1>A personal learning project</h1>
        <p className="lede">
          Track Lab is a project {AUTHOR.name} built to learn data engineering end to end, on open sports tracking
          data, and to show what he learned.
        </p>
        <p>
          It takes SkillCorner&apos;s open tracking and event data for basketball and football and conforms both
          sports into one silver schema with DuckDB and dbt; everything after that, from the replays to the
          lessons, reads what that pipeline published.
        </p>
      </PageHead>
      <Band dark>
        <h2>What it demonstrates</h2>
        <ul className="about-cards">
          {SHOWS.map((s) => (
            <li key={s.title}>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
              <Link href={s.href} prefetch={false}>
                {s.href}
              </Link>
            </li>
          ))}
        </ul>
      </Band>
      <Band>
        <h2>Stack</h2>
        <p>The pipeline&apos;s tools, with the versions the latest build recorded:</p>
        <Stack />
        <p className="about-web">
          On the web: Next.js, React and TypeScript, with DuckDB-WASM and the Canvas 2D API in the browser.
        </p>
      </Band>
      <Band dark>
        <section aria-labelledby="disclaimer-title" data-disclaimer>
          <h2 id="disclaimer-title">Disclaimer</h2>
          <p>
            Track Lab is a personal, non-commercial project built for learning. It is not affiliated with, endorsed
            by or sponsored by SkillCorner, EuroLeague Basketball or any league, club or player named on this site.
            All trademarks, names and data belong to their respective owners.
          </p>
          <p>
            SkillCorner&apos;s open data is used under its MIT license; of EuroLeague game data only aggregates are
            shown.
          </p>
          <p>
            The figures here are produced for educational purposes, may contain errors, and are not professional
            advice nor an assessment of any player or team.
          </p>
          <p>
            If you hold rights in anything shown here and want it corrected or removed, write to{" "}
            <a href={mailto(TAKEDOWN_CONTACT)}>{TAKEDOWN_CONTACT}</a> and it will be taken down.
          </p>
        </section>
      </Band>
    </main>
  );
}
