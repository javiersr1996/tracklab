import { Count } from "../components/home/Count";
import { Findings } from "../components/home/Findings";
import { Hero } from "../components/home/Hero";
import { HOME_LESSONS, Questions } from "../components/home/Questions";
import { Architecture } from "../components/platform/Architecture";
import { Band } from "../components/site/Band";
import { SectionCards } from "../components/site/SectionCards";
import { POSSESSIONS, rowsOf, SPORTS } from "../lib/data";
import { AUTHOR, BUILT, EXPLORE, sectionAt } from "../lib/sections";
import { SQL_LESSONS } from "../lib/sql/course";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  description:
    "Replay football and basketball tracking data, follow lessons that each start from one question, and run SQL on the season statistics, all in your browser.",
};

// One possession of each sport, alternating: the first published of each.
const SHOWCASE = SPORTS.map((sport) => POSSESSIONS.find((p) => p.sport === sport)!);

const LEARN = sectionAt("/learn");
const SQL = sectionAt("/sql");

// P23: what a visitor can watch and learn comes first (the lessons, then the pages to explore),
// what the site found next, and how it is built at the end.
export default function HomePage() {
  return (
    <main id="main" className="home surface-neon">
      {/* The replay fills the first screen, the header over its top and the headline over its
          foot, with the two actions (task 108); the pause button is the player's own. */}
      <Hero entries={SHOWCASE}>
        <p className="eyebrow">Open tracking data</p>
        <h1 id="hero-title">
          Watch a possession, <span className="accent">then ask it a question</span>
        </h1>
        <p className="lede">
          Replay football and basketball tracking data, follow lessons that each start from one question,
          and run SQL on the season statistics, all in your browser.
        </p>
        <p className="hero-detail">
          The data is SkillCorner&apos;s open tracking and event data: where the players and the ball
          are, frame by frame. How the site is built comes at the end of this page.
        </p>
        <p className="hero-byline">
          <Link href="/about" prefetch={false}>
            A personal learning project by {AUTHOR.name}
          </Link>
        </p>
      </Hero>

      {/* The lessons, each a question with its drawing; the count is the list's. */}
      <Band>
        <h2 className="eyebrow">Start with a question</h2>
        <p>
          <span data-lesson-count>{HOME_LESSONS.length}</span> lessons, each starting from one question about the
          data and ending with its figures and the query or script that reproduces them.
        </p>
        <Questions />
        <p>
          <Link href="/learn">{LEARN.title}</Link>: the lessons by level, each with a line on what it works
          through. New to SQL? <Link href="/sql">{SQL.title}</Link>: <span data-sql-count>{SQL_LESSONS.length}</span>{" "}
          lessons from your first <code>SELECT</code> to window functions and CTEs, with exercises checked in the
          browser.
        </p>
      </Band>

      <Band dark className="home-explore">
        <h2 className="eyebrow">Explore</h2>
        <SectionCards sections={EXPLORE.map(sectionAt)} />
      </Band>

      {/* P20, task 175: what the site found, each figure from a published file. */}
      <Band>
        <h2 className="eyebrow">Findings</h2>
        <Findings />
      </Band>

      {/* The architecture (P20, task 173) and the figures (task 106), which count up as they scroll
          into view; every number is from stats.json or platform.json, never typed here. */}
      <Band dark className="home-built">
        <h2 className="eyebrow">How it is built</h2>
        <Architecture />
        <section className="figures" aria-labelledby="figures-title">
          <h3 id="figures-title" className="eyebrow">
            By the numbers
          </h3>
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
        </section>
        <SectionCards sections={BUILT.map(sectionAt)} />
      </Band>
    </main>
  );
}
