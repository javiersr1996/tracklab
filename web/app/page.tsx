import { Count } from "../components/home/Count";
import { Findings } from "../components/home/Findings";
import { Hero } from "../components/home/Hero";
import { Architecture } from "../components/platform/Architecture";
import { Band } from "../components/site/Band";
import { SectionCards } from "../components/site/SectionCards";
import { POSSESSIONS, rowsOf, SPORTS } from "../lib/data";
import { AUTHOR, SECTIONS } from "../lib/sections";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  description:
    "Replays, SQL and data quality for football and basketball tracking, in your browser: SkillCorner's open data conformed into one schema with DuckDB and dbt.",
};

// One possession of each sport, alternating: the first published of each.
const SHOWCASE = SPORTS.map((sport) => POSSESSIONS.find((p) => p.sport === sport)!);

export default function HomePage() {
  return (
    <main id="main" className="home surface-neon">
      {/* The replay fills the first screen, the header over its top and the headline over its
          foot, with the two actions (task 108); the pause button is the player's own. */}
      <Hero entries={SHOWCASE}>
        <p className="eyebrow">Open tracking data</p>
        <h1 id="hero-title">
          One schema, two sports, <span className="accent">one renderer</span>
        </h1>
        <p className="lede">
          Replays, SQL and data quality for football and basketball tracking, in your browser.
        </p>
        <p className="hero-detail">
          Track Lab takes SkillCorner&apos;s open tracking and event data for basketball and
          football and conforms both sports into one silver schema with DuckDB and dbt.
        </p>
        <p className="hero-byline">
          <Link href="/about" prefetch={false}>
            A personal learning project by {AUTHOR.name}
          </Link>
        </p>
      </Hero>

      {/* The architecture (P20, task 173): the six layers' bytes, which were a row of boxes in the
          figures below, are on it. */}
      <Band dark>
        <h2 className="eyebrow">Architecture</h2>
        <Architecture />
      </Band>

      {/* The figures (task 106) count up as they scroll into view; every one is a number from
          stats.json or platform.json, never typed here. */}
      <section className="band figures" aria-labelledby="figures-title">
        <div className="wrap">
          <h2 id="figures-title" className="eyebrow">
            By the numbers
          </h2>
          <ul className="figures-grid">
            {SHOWCASE.map((p) => (
              <li key={p.sport} className="figure">
                <p className="figure-value" data-rows={p.sport}>
                  <Count value={rowsOf("frames", p.sport)} kind="int" />
                </p>
                <p className="figure-label">
                  rows in <code>frames</code> for {p.sport}, at {p.sample_rate_hz} fps
                </p>
              </li>
            ))}
          </ul>
          <pre className="figures-query">
            <code>SELECT * FROM frames WHERE sport = ?</code>
          </pre>
        </div>
      </section>

      {/* P20, task 175: what the site found, each figure from a published file (the build's title,
          which closed the figures above, is one of them). */}
      <Band dark>
        <h2 className="eyebrow">Findings</h2>
        <Findings />
      </Band>

      <Band>
        <h2 className="eyebrow">Sections</h2>
        <SectionCards sections={SECTIONS} />
      </Band>
    </main>
  );
}
