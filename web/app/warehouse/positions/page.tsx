import type { Metadata } from "next";
import Link from "next/link";
import { Band, PageHead } from "../../../components/site/Band";
import { Positions } from "../../../components/warehouse/Positions";
import { pitchPath } from "../../../lib/warehouse/positions";
import { positionsView } from "../../../lib/warehouse/positions-data";
import { FOOTBALL_README } from "../../../lib/warehouse/readmes";
import "./positions.css";

export const metadata: Metadata = {
  title: "How football positions differ physically | Pitch & Parquet",
  description:
    "Distance per minute, high-speed and sprint distance and peak speed by football position group, from the season aggregates of the warehouse: each group's median, middle half and every player, on a pitch and on one axis.",
};

// /warehouse/positions (task 184a): the football physical aggregates of /warehouse/scouting's pools,
// by position group. Every figure is computed at build time from the published Parquet file
// (lib/warehouse/positions-data.ts) or read from scouting.json; nothing is typed.
export default async function PositionsPage() {
  const view = await positionsView();
  const pools = view.metrics[0].groups;
  const sizes = pools.map((g) => g.n);
  return (
    <main id="main" className="page positions-page">
      <PageHead eyebrow="Season aggregates">
        <h1>How football positions differ physically</h1>
        <p className="lede" data-lede>
          How far and how fast the players of each position group run, in the provider&apos;s season aggregates for{" "}
          <span data-competition>{view.competition}</span>, <span data-season>{view.season}</span>: each group drawn where
          it plays, with its median, its middle half and every player in it.
        </p>
        <p>
          The pools are the ones <Link href="/warehouse/scouting" prefetch={false}>the scouting table</Link> ranks players
          in: the rows of <code>fb_physical</code> that pass its sample floor, <code data-floor>{view.floor}</code> (at least{" "}
          {view.floorMin} matches), {pools.length} position groups of {Math.min(...sizes)} to {Math.max(...sizes)} players.
          Pick a metric; the pitch and the ranking beside it follow. This page shows how much they run;{" "}
          <Link href="/tracking/occupancy" prefetch={false}>
            where football positions play
          </Link>{" "}
          shows where they are, from the tracking.
        </p>
      </PageHead>

      <Band dark>
        <Positions view={view} pitch={pitchPath(view.pitch.length, view.pitch.width)} />
      </Band>

      <Band>
        <h2>Every group and metric, as a table</h2>
        <div className="table-scroll">
          <table className="pos-table">
            <caption>Median, and the middle half (first to third quartile), by position group</caption>
            <thead>
              <tr>
                <th scope="col">position group</th>
                <th scope="col">players</th>
                {view.metrics.map((m) => (
                  <th scope="col" key={m.id}>
                    {m.label} ({m.scale})
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pools.map((g) => (
                <tr key={g.group} data-group={g.group}>
                  <th scope="row">{g.group}</th>
                  <td data-n>{g.n}</td>
                  {view.metrics.map((m) => {
                    const s = m.groups.find((x) => x.group === g.group)!;
                    return (
                      <td key={m.id} data-metric={m.id}>
                        <span data-median>{s.text.median}</span> ({s.text.q1} to {s.text.q3})
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2>What this does and does not say</h2>
        <ul className="pos-limits">
          <li>
            One season: the aggregates the provider publishes for {view.competition}, {view.season}, one row per player,
            team and position group, which{" "}
            <a href={`${FOOTBALL_README}#L75`}>the football README says are filtered for performances above 60 minutes</a>.
            Nothing here is measured from the tracking.
          </li>
          <li>
            A floor and small pools: a row counts only past <code>{view.floor}</code>, and the groups hold{" "}
            {Math.min(...sizes)} to {Math.max(...sizes)} players, so a few players can move a median. The bars show how
            wide each group&apos;s middle half is.
          </li>
          <li>
            Descriptive: a difference between two groups describes these players in this season. It does not say what a
            position demands, and team, role inside a group and the matches each player played all sit inside it.
          </li>
        </ul>
        <p>
          <Link href="/warehouse/scouting" prefetch={false}>
            The scouting table
          </Link>{" "}
          lists the players behind each group, with their percentiles in it.
        </p>
      </Band>
    </main>
  );
}
