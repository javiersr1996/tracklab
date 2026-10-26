import { factOf } from "../Fact";

// Lesson 4 of /sql. Every number and name comes from `sqlcourse/group-by/facts.sql` through `f`.
const f = factOf("group-by");

export function GroupByProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          Which team scored the most? A team total is a sum over its players. <code>GROUP BY team_name</code>{" "}
          folds the rows of each team into one, and the aggregates (<code>count</code>, <code>sum</code>,{" "}
          <code>avg</code>, <code>min</code>, <code>max</code>) are computed inside each group. <code>bb_shots</code>{" "}
          has {f("teams")} teams, and {f("top_team")} tops them with {f("top_team_points")} points. Every column
          in the <code>SELECT</code> of a grouped query is either grouped by or aggregated: a plain{" "}
          <code>player_name</code> there has no single value per team.
        </p>
      </section>

      <section aria-labelledby="having-h">
        <h2 id="having-h">Filter before, filter after</h2>
        <p>
          <code>WHERE</code> runs before the groups exist and <code>HAVING</code> after: a condition on a row goes
          in <code>WHERE</code>, a condition on an aggregate in <code>HAVING</code>. The season-total rows of
          traded players are a row condition: summing attempts over every row of <code>bb_shots</code> gives{" "}
          {f("attempts_all_rows")}, over the team rows {f("attempts_team_rows")}, because a total row repeats
          what its team rows already hold. Of the {f("football_teams")} football teams in{" "}
          <code>fb_physical</code>, {f("football_teams_250_matches")} add up to two hundred and fifty matches or
          more over their players, a condition on a sum: <code>HAVING sum(count_match) &gt;= 250</code>.
        </p>
      </section>

      <section aria-labelledby="count-h">
        <h2 id="count-h">count(*) and count(column)</h2>
        <p>
          <code>count(*)</code> counts rows; <code>count(column)</code> counts the rows where that column is not{" "}
          <code>NULL</code>. On <code>fb_physical</code> they give {f("count_star_hsr")} and{" "}
          {f("count_column_hsr")} for <code>timetohsr_top3</code>. The other aggregates skip <code>NULL</code> too,
          and the average of a group with nothing but <code>NULL</code> is <code>NULL</code>:{" "}
          {f("avg_of_empty_group_is_null")}.
        </p>
      </section>
    </>
  );
}
