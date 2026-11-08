import type { Metadata } from "next";
import Link from "next/link";
import { ProbePanel, type ProbeView } from "../../../components/scouting/ProbePanel";
import { Scouting } from "../../../components/scouting/Scouting";
import { Band, PageHead } from "../../../components/site/Band";
import { rowsOf } from "../../../lib/data";
import { probeMetrics, SCOUTING, sameKey, sampleNoun, TABLE_LABEL } from "../../../lib/scouting/catalog";
import { BASKETBALL_README, FOOTBALL_README } from "../../../lib/warehouse/readmes";
import "./scouting.css";

export const metadata: Metadata = {
  title: "Scouting | Track Lab",
  description:
    "Every player who passes a sample floor in the season aggregates, sortable by any metric, with percentiles inside their pool and a side-by-side comparison of two players.",
};

// /warehouse/scouting (P17, task 136): the season aggregates of the warehouse as a scouting
// table, sortable by any metric, with each percentile beside its pool, and two players side by
// side. Every figure on the page comes from `scouting.json` or from the engine's results. Its
// links do not prefetch, so the bytes of its load (and of /warehouse's) are its own.

// The head panel: the default pair's first player in the first table, from the JSON's probe.
function probeView(): ProbeView {
  const table = SCOUTING.tables[0];
  const who = SCOUTING.default_pairs[table.sport][0];
  const probe = table.probes.find((p) => sameKey(p, who));
  const pool = table.pools.find((p) => p.group === (who.position_group ?? null));
  if (!probe?.values || !pool) throw new Error("scouting.json has no probe for the head panel");
  return {
    name: who.player_name,
    team: who.team_name,
    group: pool.group ?? "the league",
    age: who.age ?? null,
    ageReference: SCOUTING.age_reference,
    table: TABLE_LABEL[table.table] ?? table.table,
    pool: { players: pool.players, sample: pool.sample_total, noun: sampleNoun(table, pool.sample_total) },
    metrics: probeMetrics(table, probe),
  };
}

export default function ScoutingPage() {
  return (
    <main className="page scouting-page">
      <PageHead eyebrow="Season aggregates" aside={<ProbePanel probe={probeView()} />}>
        <h1>Scouting</h1>
        <p>
          Every player who passes a table&apos;s sample floor, from the two season aggregates, in one table you can sort by
          any metric; the page says how many rows of the table fall under the floor and are left out. Each value comes with
          its percentile inside its pool: the players who pass the table&apos;s sample floor, within their position
          group in football and across the league in basketball, counted at the head of each group. Pick two
          players, A and B, and their percentiles in every table of their sport stand side by side.
        </p>
        <p>
          DuckDB runs the queries in this browser on the warehouse&apos;s Parquet files, and nothing of the engine
          is downloaded until you load the table. The percentiles are the window functions of{" "}
          <Link href="/sql/windows" prefetch={false}>
            lesson 7
          </Link>{" "}
          and{" "}
          <Link href="/sql/scouting" prefetch={false}>
            lesson 8
          </Link>{" "}
          of the SQL course;{" "}
          <Link href="/warehouse" prefetch={false}>
            the console
          </Link>{" "}
          runs any other query.
        </p>
      </PageHead>

      <Band dark className="scout-band">
        <ul className="scout-legend" aria-label="How to read the cells and the bars">
          <li>
            <span className="scout-legend-label">Percentile in the pool</span>
            <span className="scout-steps">
              <span data-step="0">0 to 20</span>
              <span data-step="1">20 to 40</span>
              <span data-step="2">40 to 60</span>
              <span data-step="3">60 to 80</span>
              <span data-step="4">80 to 100</span>
            </span>
          </li>
          <li>
            <span className="scout-legend-label">Compared</span>
            <span className="scout-swatch" data-slot="a" aria-hidden="true" /> A
            <span className="scout-swatch" data-slot="b" aria-hidden="true" /> B
          </li>
        </ul>
        <Scouting />
      </Band>

      <Band>
        <h2>What the table holds, and what it does not</h2>
        <ul>
          <li>
            Holds: the season aggregates the providers publish. <a href={BASKETBALL_README}>The basketball README</a>{" "}
            says its aggregates cover 293 of the 327 games of the Liga ACB 2025-2026 (regular season and playoffs);{" "}
            <a href={`${FOOTBALL_README}#L30`}>the football one</a> says its are the A-League 2024-2025 season,{" "}
            <a href={`${FOOTBALL_README}#L75`}>filtered for performances above 60 minutes</a>.
          </li>
          <li>
            Pools: a row enters a pool when it passes its table&apos;s sample floor. Football pools are position
            groups; basketball has no position, so its pool is the league. A metric&apos;s pool also leaves out the
            rows with no value for it, and where that makes it smaller the group&apos;s head prints its{" "}
            <code>n</code>.
            <ul className="scout-floors">
              {SCOUTING.tables.map((t) => (
                <li key={t.table} data-floor={t.table}>
                  {TABLE_LABEL[t.table]}: <code>{t.floor}</code>
                </li>
              ))}
            </ul>
          </li>
          <li>
            Percentiles: <code>percent_rank()</code> in ascending order, times 100, rounded half up to one decimal,
            which is the share of the pool&apos;s other players with a lower value. A high percentile is a high value,
            not a verdict: a high share of drives that end in a turnover is a high percentile too.
          </li>
          <li>
            Does not hold: rankings from the tracking. The bundles carry {rowsOf("dim_match", "basketball")}{" "}
            basketball matches and {rowsOf("dim_match", "football")} football matches of tracking (
            <a href="/data/stats.json">stats.json</a>, <code>dim_match</code>); no table here ranks players from them.
          </li>
          <li>
            Age: whole years completed at {SCOUTING.age_reference}, the <code>player_age</code> column of the football
            files. No date of birth is published anywhere on this site. Basketball has no age.
          </li>
          <li data-aliases={SCOUTING.aliases.length}>
            Aliases: the provider changed {SCOUTING.aliases.length} basketball player ids during the season and lists
            them in an alias file. A row tagged <em>old id</em> carries one of the replaced ids and a row tagged{" "}
            <em>new id</em> its replacement on the same team: one person in two rows, kept apart because shares and
            rates do not add.{" "}
            <Link href="/warehouse" prefetch={false}>
              The warehouse
            </Link>{" "}
            shows what folding them does to one percentile.
          </li>
        </ul>
        <p>
          The catalog, the floors, the pools and the expected answers for the default pair are in{" "}
          <a href="/data/scouting.json">scouting.json</a>, computed in Python from the same Parquet files.
        </p>
      </Band>
    </main>
  );
}
