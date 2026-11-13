import type { Metadata } from "next";
import Link from "next/link";
import { Band, PageHead } from "../../../components/site/Band";
import { Legend, OccupancyCells, SmallMultiples } from "../../../components/occupancy/Maps";
import { Occupancy, type PickGroup } from "../../../components/occupancy/Occupancy";
import { LANES, occupancyView, pct, THIRDS } from "../../../lib/occupancy/data";
import { pitchPath } from "../../../lib/warehouse/positions";
import "./occupancy.css";

export const metadata: Metadata = {
  title: "Where football positions play | Pitch & Parquet",
  description:
    "A heat map of where the players of each football position group were, from every tracked frame of the provider's open matches outside the Analytics Cup fence, every team turned to attack the same way.",
};

// /tracking/occupancy (task 184b): occupancy.json, written by `tracklab publish occupancy` from the
// silver frames. Every figure is read or summed from it in lib/occupancy/data.ts; nothing is typed.
export default function OccupancyPage() {
  const view = occupancyView();
  const n = (v: number) => v.toLocaleString("en-US");
  const lines = pitchPath(view.grid.length_m, view.grid.width_m);
  const pick: PickGroup[] = view.groups.map((g) => ({
    group: g.group,
    slug: g.slug,
    player_frames: n(g.player_frames),
    player_matches: n(g.player_matches),
    matches: n(g.matches),
    label: `Heat map of the ${g.group.toLowerCase()} group, attacking to the right: busiest in the ${g.third.name}, ${pct(g.third.share)} of its player-frames, and on the ${g.lane.name}, ${pct(g.lane.share)}.`,
  }));
  return (
    <main id="main" className="page occupancy-page">
      <PageHead eyebrow="Open tracking data">
        <h1>Where football positions play</h1>
        <p className="lede" data-lede>
          Where the players of each position group were during <span data-matches>{view.matches}</span> football matches,
          drawn as a heat map: the brighter a square of the pitch, the more of the group&apos;s time was spent there. Every
          team is turned to attack the same way, from left to right.
        </p>
        <p>
          The tracking places every player <span data-hz>{view.hz}</span> times a second. Over{" "}
          <span data-frames>{n(view.frames)}</span> frames (about <span data-hours>{view.hours.toFixed(1)}</span> hours of
          play in the {view.competition} {view.season}) that is <span data-outfield>{n(view.outfieldFrames)}</span>{" "}
          player-frames of outfield players, each one player in one frame; the goalkeepers&apos;{" "}
          <span data-goalkeepers>{n(view.goalkeeperFrames)}</span> are left out. This page shows where they are;{" "}
          <Link href="/warehouse/positions" prefetch={false}>
            how football positions differ physically
          </Link>{" "}
          shows how much they run.
        </p>
      </PageHead>

      <Band dark>
        <OccupancyCells view={view} />
        <Occupancy groups={pick} lines={lines} length={view.grid.length_m} width={view.grid.width_m} />
        <Legend view={view} />
        <h2 className="occ-multiples-title">Every group side by side</h2>
        <SmallMultiples view={view} lines={lines} />
      </Band>

      <Band>
        <h2>Where each group spends most of its time</h2>
        <p>
          The pitch cut into three thirds along its length, <span data-third-m>{(view.grid.length_m / 3).toFixed(1)}</span> m
          each, and five lanes across it, <span data-lane-m>{(view.grid.width_m / LANES.length).toFixed(1)}</span> m each;
          left and right are the team&apos;s, facing the goal it attacks. A group pools its players of both sides, so a
          group that plays on both flanks splits its time between two lanes.
        </p>
        <div className="table-scroll">
          <table className="occ-table" data-table="busiest">
            <caption>The busiest third and lane of each group</caption>
            <thead>
              <tr>
                <th scope="col">position group</th>
                <th scope="col">busiest third</th>
                <th scope="col">busiest lane</th>
                <th scope="col">player-frames</th>
                <th scope="col">player-matches</th>
                <th scope="col">off the pitch</th>
              </tr>
            </thead>
            <tbody>
              {view.groups.map((g) => (
                <tr key={g.slug} data-group={g.slug}>
                  <th scope="row">{g.group}</th>
                  <td data-field="third">
                    {g.third.name}, <span data-share>{pct(g.third.share)}</span>
                  </td>
                  <td data-field="lane">
                    {g.lane.name}, <span data-share>{pct(g.lane.share)}</span>
                  </td>
                  <td data-field="player_frames">{n(g.player_frames)}</td>
                  <td data-field="player_matches">{n(g.player_matches)}</td>
                  <td data-field="off_pitch">{n(g.off_pitch)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-scroll">
          <table className="occ-table" data-table="regions">
            <caption>Each group&apos;s share of its player-frames in every third and lane</caption>
            <thead>
              <tr>
                <th scope="col">position group</th>
                {[...THIRDS, ...LANES].map((name) => (
                  <th scope="col" key={name}>
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {view.groups.map((g) => (
                <tr key={g.slug} data-group={g.slug}>
                  <th scope="row">{g.group}</th>
                  {[...g.thirds, ...g.lanes].map((s, i) => (
                    <td key={i} data-share>
                      {pct(s)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Off the pitch: a position outside the lines of its own pitch, counted here and left off the maps; that is{" "}
          <span data-off-pitch>{pct(view.offPitch)}</span> of the outfield player-frames.
        </p>

        <h2>What this does and does not say</h2>
        <ul className="occ-limits">
          <li>
            <span data-matches>{view.matches}</span> matches of one league and season, the {view.competition}{" "}
            {view.season}, from the provider&apos;s open data, leaving out the matches the site holds back while a
            competition built on them runs. That is a small sample of one season.
          </li>
          <li>
            Positions as the provider&apos;s tracking gives them, every frame it tracked; a frame it did not track is not
            in the data. A position outside the lines of its pitch is counted in the table and left off the map.
          </li>
          <li>
            A position group is the provider&apos;s label for a player in that match, so a player can count in two
            groups over two matches. Pitches of slightly different lengths are stretched onto one.
          </li>
          <li>
            Descriptive: where players were, not where they should be. It makes no claim about any team or player, and
            no player or team is shown on its own.
          </li>
        </ul>
        <p>
          The numbers come from <a href="/data/occupancy.json">occupancy.json</a>, computed from the tracking one match at
          a time.
        </p>
      </Band>
    </main>
  );
}
