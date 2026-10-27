import { factOf } from "../Fact";

// Lesson 1 of /sql. Every number and name comes from `sqlcourse/select/facts.sql` through `f`.
const f = factOf("select");

export function SelectProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          Who took the most shots in the Liga ACB season? The table <code>bb_shots</code> has one row per
          player and team: {f("rows")} rows for {f("players")} players, because a player traded mid-season has
          a row per team plus a row whose <code>is_season_total</code> is true. The answer is {f("top_shooter")}{" "}
          with {f("top_attempts")} attempts, and the worked example below is the query that gives it.
        </p>
      </section>

      <section aria-labelledby="concept-h">
        <h2 id="concept-h">SELECT, FROM, ORDER BY, LIMIT</h2>
        <p>
          A query names the columns it wants (<code>SELECT</code>), the table they come from (<code>FROM</code>),
          the order of the rows (<code>ORDER BY</code>, with <code>DESC</code> for the largest first) and how many
          rows to keep (<code>LIMIT</code>). The clauses go in that order, and the result is a table again: the
          columns you named, in the order you named them. Column names are written as they are, without
          quotes; text values, as you will see in the next lesson, go in single quotes.
        </p>
        <p>
          Without <code>ORDER BY</code> the rows come in whatever order the engine reads them, and a{" "}
          <code>LIMIT</code> then keeps an arbitrary handful. A question with &quot;most&quot; or &quot;first&quot; in it always
          needs a sort.
        </p>
      </section>

      <section aria-labelledby="ties-h">
        <h2 id="ties-h">Ties</h2>
        <p>
          Two rows can share the value you sort by, and then the engine decides their order, not you, and not
          the same way every time. In <code>bb_shots</code> the eleventh-highest number of attempts is{" "}
          {f("eleventh_attempts")}, and {f("tied_with_eleventh")} players have it: a <code>LIMIT 11</code> sorted
          by attempts alone can end with either of them. A second column settles it: <code>ORDER BY attempts
          DESC, player_name</code> sorts by attempts and, among rows with the same attempts, by name. The
          checker of the first exercise compares rows in order, so the tie-break is part of the answer.
        </p>
      </section>
    </>
  );
}
