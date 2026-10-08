import type { Metadata } from "next";
import Link from "next/link";
import { Console } from "../../components/warehouse/Console";
import { rowsOf } from "../../lib/data";
import { EXAMPLES_FILE } from "../../lib/warehouse/examples";
import { WAREHOUSE } from "../../lib/warehouse/registry";
import { formatBytes } from "../../lib/format";

export const metadata: Metadata = { title: "Warehouse | Track Lab" };

const BASKETBALL_README = "https://github.com/SkillCorner/opendata-basketball";
const FOOTBALL_README = "https://github.com/SkillCorner/opendata";

const fixed = (value: number) => value.toFixed(1);

export default function WarehousePage() {
  const { aliases, params } = EXAMPLES_FILE;
  const shooting = aliases.basketball_percentile;
  const total = WAREHOUSE.tables.reduce((sum, t) => sum + t.bytes, 0);
  return (
    <main className="page warehouse-page">
      <h1>Warehouse</h1>
      <p>
        SQL over the season aggregates of both bundles, run by DuckDB in this browser on Parquet
        files that are read by HTTP range. Nothing of the engine is downloaded until you run a
        query, and the panel under the editor counts the engine&apos;s bytes and the data&apos;s
        separately.
      </p>

      <Console />

      <h2>What the data holds, and what it does not</h2>
      <ul>
        <li>
          Holds: the season aggregates the providers publish.{" "}
          <a href={BASKETBALL_README}>The basketball README</a> says its aggregates cover 293 of
          the 327 games of the Liga ACB 2025-2026 (regular season and playoffs);{" "}
          <a href={FOOTBALL_README}>the football one</a> says its are the A-League 2024-2025
          season, filtered for performances above 60 minutes. Profiles and percentiles are read
          from these, and each percentile in the examples is printed with its denominator
          (players, matches or games).
        </li>
        <li>
          Does not hold: rankings from the tracking. The bundles carry {rowsOf("dim_match", "basketball")}{" "}
          basketball matches and {rowsOf("dim_match", "football")} football matches of tracking
          (<a href="/data/stats.json">stats.json</a>, <code>dim_match</code>); no query here ranks
          players from them.
        </li>
      </ul>

      <h2>Reading the numbers</h2>
      <ul>
        <li>
          A basketball player traded mid-season has one row per team and an extra row whose team
          is <code>total</code> (<code>is_season_total</code>). The examples filter it out;
          adding it to the team rows would count that player twice.
        </li>
        <li>
          Basketball metrics that are shares run from 0 to 1 and football ones from 0 to 100, and
          the distance metrics mix per-match averages with season totals. No example combines
          columns across those scales.
        </li>
        <li data-aliases>
          The provider changed {aliases.alias_ids} basketball player ids during the season and
          lists them in an alias file. Gold keeps the provider&apos;s id, and for{" "}
          {aliases.bb_shots_alias_rows_in_a_team_with_their_canonical_id} of them the old and the
          new id both appear on the same team in <code>bb_shots</code>, so one person is two rows.
          Of the examples only the basketball percentile ranks players: its pool has{" "}
          {shooting.pool_rows_naive} rows, {shooting.pool_rows_merged} with the alias rows folded
          into their canonical ids, and {params.basketball_player} sits at the{" "}
          {fixed(shooting.percentile_naive)}th percentile in the first and the{" "}
          {fixed(shooting.percentile_merged)}th in the second. The player profile
          {aliases.profile_player_has_an_alias ? " has" : " has no"} an alias; team totals are
          sums by team and do not depend on the id. Football has no alias file.
        </li>
      </ul>

      <h2>The files</h2>
      <p>
        The seven Parquet files behind the views, read from{" "}
        <a href="/data/warehouse.json">warehouse.json</a>: {formatBytes(total)} in all, written
        with {String(WAREHOUSE.writer.library)} {String(WAREHOUSE.writer.version)}. The wide tables
        have one row group; the long table <code>fact</code> is sorted by metric and cut into
        several, which is what a range read can skip. The expected answers of the examples are in{" "}
        <a href="/data/warehouse_examples.json">warehouse_examples.json</a>.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">table</th>
              <th scope="col">sport</th>
              <th scope="col">rows</th>
              <th scope="col">columns</th>
              <th scope="col">sorted by</th>
              <th scope="col">row groups</th>
              <th scope="col">bytes</th>
            </tr>
          </thead>
          <tbody>
            {WAREHOUSE.tables.map((t) => (
              <tr key={t.table} data-table={t.table}>
                <td>{t.table}</td>
                <td>{t.sport}</td>
                <td>{t.rows.toLocaleString("en-US")}</td>
                <td>{t.columns.toLocaleString("en-US")}</td>
                <td>{t.order_by.join(", ")}</td>
                <td>{t.row_groups.length}</td>
                <td>{t.bytes.toLocaleString("en-US")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p>
        <Link href="/">Track Lab</Link>
      </p>
    </main>
  );
}
