import type { Metadata } from "next";
import { Atlas } from "../../components/euroleague/Atlas";
import { LeaguePanel } from "../../components/euroleague/LeaguePanel";
import { Band, PageHead } from "../../components/site/Band";
import { LEAGUE, RUNS, teamsSummary } from "../../lib/euroleague/data";
import { EUROLEAGUE, SECTIONS, TAKEDOWN_CONTACT } from "../../lib/sections";
import "./euroleague.css";

const SECTION = SECTIONS.find((s) => s.href === "/euroleague")!;

export const metadata: Metadata = {
  title: SECTION.title,
  description: SECTION.about,
  openGraph: { type: "website", title: SECTION.title, description: SECTION.about, url: SECTION.href },
  twitter: { card: "summary_large_image", title: SECTION.title, description: SECTION.about },
};

// /euroleague (P14, task 116): the shot atlas. Every figure comes from web/public/data/euroleague/,
// the aggregates `tracklab euroleague publish` writes: league.json at build time, a team's file
// when it is chosen. No request leaves for euroleague.net.
export default function EuroleaguePage() {
  const summary = teamsSummary();
  const k = LEAGUE.hex.k;
  return (
    <main id="main" className="page euroleague">
      <PageHead eyebrow="EuroLeague" aside={<LeaguePanel league={LEAGUE} />}>
        <h1>{SECTION.title}</h1>
        <p className="lede">
          The EuroLeague&apos;s field goals, binned into hexagons with sides of {LEAGUE.hex.side_m} m on a FIBA half
          court: how often each spot is tried, and how often it goes in compared with the rest of the league.
        </p>
        <p>
          The league comes first. Pick a team to see where it beats the league and where it falls short, then one
          of its players, in the season just finished or the one under way.
        </p>
      </PageHead>
      <Atlas league={LEAGUE} runs={RUNS} {...summary} />
      <Band dark className="el-attribution">
        <section aria-labelledby="el-source-title">
          <h2 id="el-source-title">The data</h2>
          <p data-attribution="source">
            Data: <a href={EUROLEAGUE.href}>{LEAGUE.source}</a>, the game feed the shots are counted from.
          </p>
          <p data-attribution="affiliation">Not affiliated with EuroLeague.</p>
          <p data-attribution="aggregates">
            The feed has no open license, so this page publishes aggregates only: a count of shots, makes and points
            per hexagon, never a shot, and a hexagon with fewer than {k} shots is dropped. Your browser asks nothing
            of euroleague.net; the files it reads are this site&apos;s own.
          </p>
          <p data-attribution="removal">
            Removal requests:{" "}
            {TAKEDOWN_CONTACT ? (
              <a href={TAKEDOWN_CONTACT.includes("@") ? `mailto:${TAKEDOWN_CONTACT}` : TAKEDOWN_CONTACT}>
                {TAKEDOWN_CONTACT}
              </a>
            ) : (
              "contact pending"
            )}
            .
          </p>
        </section>
      </Band>
    </main>
  );
}
