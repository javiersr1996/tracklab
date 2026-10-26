import { factOf } from "../Fact";

// Lesson 8 of /sql. Every number comes from `sqlcourse/scouting/facts.sql` through `f`.
const f = factOf("scouting");

export function ScoutingProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          A scouting question crosses tables: fast within the position, from <code>fb_physical</code>, and
          accurate within the position, from <code>fb_passing</code>. Each half is a pool with its own filter and
          its own percentile, and a CTE, <code>WITH name AS (...)</code>, gives each half a name that the final
          query joins as if it were a table. The speed pool has {f("speed_pool_rows")} rows and the passing pool{" "}
          {f("passing_pool_rows")}; {f("rows_in_both_pools")} rows are in both.
        </p>
      </section>

      <section aria-labelledby="together-h">
        <h2 id="together-h">Putting it together</h2>
        <p>
          The order of the previous lessons is the order of the query. Filter inside each CTE before the
          percentile, because the pool decides the percentile. Join the two on the full key of lesson five,{" "}
          <code>player_id</code>, <code>team_id</code> and <code>position_group</code>. Filter on the percentiles after
          the join, in the final <code>WHERE</code>. In the top thirty percent for speed (<code>speed_pct &gt;=
          70</code>) are {f("speed_only_70")} rows and for passing {f("passing_only_70")}; both at once,{" "}
          {f("shortlist_rows")}, of which {f("full_back_shortlist_rows")} are full backs: the worked example.
        </p>
        <p>
          Two habits that keep a report honest. Round only in the <code>SELECT</code>, never in the{" "}
          <code>WHERE</code>: a rate rounded before the filter lets a value just below the threshold through.
          And divide with a decimal, <code>total_points * 1.0 / games_played</code>, so that a rate of points per
          game is not cut to a whole number before it is compared.
        </p>
      </section>
    </>
  );
}
