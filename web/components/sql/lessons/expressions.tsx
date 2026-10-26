import { factOf } from "../Fact";

// Lesson 3 of /sql. Every number comes from `sqlcourse/expressions/facts.sql` through `f`.
const f = factOf("expressions");

export function ExpressionsProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          A field-goal percentage is not stored, it is made: <code>100 * mades / attempts</code>. A computed column
          is any expression in the <code>SELECT</code> list, with <code>AS</code> to give it a name. The worked
          example computes it three ways for the players with the most attempts, on the team rows of{" "}
          <code>bb_shots</code> ({f("team_rows")} rows once the {f("total_rows_excluded")} season-total rows are
          left out with <code>WHERE NOT is_season_total</code>).
        </p>
      </section>

      <section aria-labelledby="division-h">
        <h2 id="division-h">Two divisions</h2>
        <p>
          In DuckDB <code>/</code> divides with decimals and <code>{"//"}</code> is whole division: <code>7 / 2</code> is{" "}
          {f("seven_over_two")} and <code>{"7 // 2"}</code> is {f("seven_whole_over_two")}. So{" "}
          <code>{"mades // attempts"}</code> is zero for {f("whole_division_zero")} of the players and one for{" "}
          {f("whole_division_one")}, the ones who made every attempt. Use <code>{"//"}</code> when you want the
          decimals cut off, and <code>round(x, 1)</code> when you want them rounded. Other databases differ here:
          in Postgres <code>7 / 2</code> on two integers is already whole division.
        </p>
      </section>

      <section aria-labelledby="zero-h">
        <h2 id="zero-h">Dividing by zero</h2>
        <p>
          Among the team rows, {f("zero_attempts")} players have no attempts, {f("zero_three_attempts")} have no
          three-point attempts and {f("zero_games")} has no games. DuckDB does not fail on a division by zero, it
          returns a value that is not a number:
        </p>
        <ul>
          <li>
            <code>1 / 0</code> is infinity: {f("one_over_zero_is_inf")}
          </li>
          <li>
            <code>0.0 / 0</code> is <code>NaN</code>: {f("zero_over_zero_is_nan")}
          </li>
          <li>
            <code>1 / NULLIF(0, 0)</code> is <code>NULL</code>: {f("one_over_nullif_zero_is_null")}
          </li>
        </ul>
        <p>
          Neither infinity nor <code>NaN</code> is a percentage, and the checker of this course refuses a result
          that holds one. <code>NULLIF(attempts, 0)</code> turns a zero into <code>NULL</code>, and anything divided
          by <code>NULL</code> is <code>NULL</code>, which is the honest value for a player with no attempts:{" "}
          <code>round(100.0 * mades / NULLIF(attempts, 0), 1)</code>.
        </p>
      </section>

      <section aria-labelledby="case-h">
        <h2 id="case-h">CASE</h2>
        <p>
          <code>CASE WHEN ... THEN ... ELSE ... END</code> picks a value by conditions, tried from the top: the
          first true branch wins and the rest are not looked at, so order the tests from the strictest down and
          let <code>ELSE</code> catch what is left. The second exercise bands the {f("midfield_20_matches")}{" "}
          midfielders with twenty matches or more by <code>psv99</code>, the provider&apos;s peak sprint velocity,
          and rates their sprints per ninety minutes from <code>sprint_count_full_all</code> and{" "}
          <code>minutes_full_all</code>.
        </p>
      </section>
    </>
  );
}
