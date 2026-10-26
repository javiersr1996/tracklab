import { factOf } from "../Fact";

// Lesson 7 of /sql. Every number and name comes from `sqlcourse/windows/facts.sql` through `f`.
const f = factOf("windows");

export function WindowsProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          The warehouse prints a player&apos;s speed as a percentile within his position: where he sits among the
          players of the same position group with enough matches. A window function computes that without
          collapsing the rows the way <code>GROUP BY</code> does: <code>rank() OVER (PARTITION BY position_group
          ORDER BY psv99 DESC)</code> gives each row its rank inside its group and keeps the row.{" "}
          <code>PARTITION BY</code> says which rows form a group, <code>ORDER BY</code> inside the window says what
          the rank is of. The pool is the {f("football_pool_rows")} rows of <code>fb_physical</code> with a{" "}
          <code>psv99</code> and at least five matches; its Midfield group has {f("midfield_pool_rows")} rows,{" "}
          {f("midfield_players")} players with {f("midfield_matches")} matches between them, and{" "}
          {f("fastest_midfielder")} leads it with a <code>psv99</code> of {f("fastest_midfielder_psv99")}.
        </p>
      </section>

      <section aria-labelledby="rank-h">
        <h2 id="rank-h">rank, row_number and percent_rank</h2>
        <p>
          <code>row_number()</code> numbers the rows of a group from one with no ties, in the order of the window;{" "}
          <code>rank()</code> gives tied rows the same rank and skips the numbers after it. In this pool the two
          differ on {f("rank_differs_from_row_number")} rows. <code>percent_rank()</code> is the rank rescaled from
          zero for the lowest value to one for the highest, so <code>100 * percent_rank()</code> rounded to one
          decimal is the percentile the warehouse prints: a midfielder ranked {f("jay_barnett_rank")} with a{" "}
          <code>psv99</code> of {f("jay_barnett_psv99")} is at the {f("jay_barnett_percentile")}th percentile.
          Note the direction: the rank sorts down (<code>DESC</code>, fastest first) and the percentile sorts up,
          so that a high percentile means fast.
        </p>
      </section>

      <section aria-labelledby="filter-h">
        <h2 id="filter-h">Filtering on a window</h2>
        <p>
          A window function cannot go in <code>WHERE</code>: <code>WHERE</code> runs before the window sees the
          rows. Compute it in a subquery and filter outside, as in <code>FROM (SELECT ..., rank() OVER (...) AS r
          FROM ...) AS t WHERE r &lt;= 5</code>, or use DuckDB&apos;s <code>QUALIFY</code>, which filters on a window
          the way <code>HAVING</code> filters groups. The pool matters: the <code>WHERE</code> inside the subquery
          decides who is ranked, and a player removed from it changes everyone&apos;s percentile. The basketball
          version, team rows with at least ten games, has {f("basketball_pool_rows")} rows and no{" "}
          <code>PARTITION BY</code>: one window over the whole pool.
        </p>
      </section>
    </>
  );
}
