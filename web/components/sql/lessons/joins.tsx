import { factOf } from "../Fact";

// Lesson 5 of /sql. Every number and name comes from `sqlcourse/joins/facts.sql` through `f`:
// the row of 406 against 407 is 21 and 22 unmatched rows on (player_id, team_id, position_group).
const f = factOf("joins");

export function JoinsProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          <code>fb_physical</code> has {f("physical_rows")} rows and <code>fb_passing</code> {f("passing_rows")}:
          the same season, the same teams, one row apart. A <code>JOIN</code> puts a row of one table beside its
          row in the other, and the extra row is the lesson, because it is not one row. The two tables differ on{" "}
          {f("physical_only_rows")} rows of the first and {f("passing_only_rows")} rows of the second that have no
          partner, and the difference between those two counts is the one row you see.
        </p>
      </section>

      <section aria-labelledby="key-h">
        <h2 id="key-h">The key</h2>
        <p>
          A join needs a key: the columns that identify the same row in both tables. <code>player_id</code> alone
          is not it here. A player has one row per position group he played, so {f("players_with_two_or_more_rows")}{" "}
          of the {f("physical_players")} players of <code>fb_physical</code> have two rows or more, and joining on{" "}
          <code>player_id</code> alone pairs every row of a player with every row of the same player:{" "}
          {f("join_on_player_id")} rows instead of {f("physical_rows")}. Adding <code>team_id</code> gives{" "}
          {f("join_on_player_and_team")}. It takes <code>player_id</code>, <code>team_id</code> and{" "}
          <code>position_group</code> together, three equalities joined by <code>AND</code> in the{" "}
          <code>ON</code> clause, to pair each row with at most one: {f("matched_rows")} pairs.
        </p>
        <p>
          Names are not keys. Joining on <code>player_name</code> instead of <code>player_id</code> (with team and
          position) gives {f("join_on_name_team_position")} rows: {f("name_with_two_ids")} appears under two ids
          at {f("name_with_two_ids_team")}, so his rows pair with each other as well. Ids identify; names label.
        </p>
      </section>

      <section aria-labelledby="left-h">
        <h2 id="left-h">LEFT JOIN and the rows with no pair</h2>
        <p>
          <code>JOIN</code> (an inner join) keeps the pairs only. <code>LEFT JOIN</code> keeps every row of the
          left table and fills the right table&apos;s columns with <code>NULL</code> where there is no pair:{" "}
          {f("left_join_rows")} rows from <code>fb_physical</code>, every one of them. Filtering those on a key of
          the right side <code>IS NULL</code> lists the rows with no pair. <code>fb_physical</code> has{" "}
          {f("physical_only_rows")}: for {f("physical_only_other_position_in_passing")} of them the player is in{" "}
          <code>fb_passing</code> under another position group, and {f("physical_only_not_in_passing_at_all")}{" "}
          are not in <code>fb_passing</code> with that team at all. <code>fb_passing</code> has{" "}
          {f("passing_only_rows")}, and all of them are goalkeepers: <code>fb_passing</code> holds{" "}
          {f("passing_only_goalkeepers")} goalkeepers and <code>fb_physical</code> {f("physical_goalkeepers")}.
          Swap the tables and the same query lists the other side. The last two exercises are those two lists.
        </p>
      </section>
    </>
  );
}
