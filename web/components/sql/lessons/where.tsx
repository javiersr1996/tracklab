import { factOf } from "../Fact";

// Lesson 2 of /sql. Every number comes from `sqlcourse/where/facts.sql` through `f`.
const f = factOf("where");

export function WhereProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          <code>fb_physical</code> has {f("rows")} rows: one per football player, team and position group (there
          are {f("position_groups")} position groups), with the physical output of the A-League season per
          match. Which full backs play the longest? <code>WHERE</code> keeps the rows that pass a test:{" "}
          {f("over_98")} rows pass <code>minutes_full_all &gt; 98</code>, and {f("full_backs_over_98")} of them are
          full backs, which is what the worked example lists.
        </p>
      </section>

      <section aria-labelledby="concept-h">
        <h2 id="concept-h">AND, OR and parentheses</h2>
        <p>
          A test compares a column with a value: a number as it is, text in single quotes, as in{" "}
          <code>position_group = &apos;Full Back&apos;</code>. <code>AND</code> requires both tests to pass,{" "}
          <code>OR</code> either one. <code>AND</code> binds before <code>OR</code>, so <code>a OR b AND c</code> means{" "}
          <code>a OR (b AND c)</code>. Asking for the center forwards and wide attackers above a hundred minutes
          gives {f("forwards_and_wide_over_100")} rows with parentheses around the two positions and{" "}
          {f("or_without_parentheses")} without them, because the test on minutes then applies to the wide
          attackers only and every center forward gets through. <code>IN (&apos;Center Forward&apos;, &apos;Wide
          Attacker&apos;)</code> says the same as the <code>OR</code>, shorter.
        </p>
      </section>

      <section aria-labelledby="null-h">
        <h2 id="null-h">NULL</h2>
        <p>
          The column <code>timetohsr_top3</code> is empty in {f("timetohsr_null")} rows and has a value in{" "}
          {f("timetohsr_not_null")}. An empty cell is <code>NULL</code>, and <code>NULL</code> is not a value: it is
          not equal to anything, not even to another <code>NULL</code>, so <code>timetohsr_top3 = NULL</code>{" "}
          matches {f("timetohsr_equals_null")} rows. Test for it with <code>IS NULL</code> and{" "}
          <code>IS NOT NULL</code>. Here the empty cells sit on players with few matches: a row with no value has{" "}
          {f("max_matches_with_null_hsr")} matches at most, and a row with a value at least{" "}
          {f("min_matches_with_hsr")}.
        </p>
      </section>
    </>
  );
}
