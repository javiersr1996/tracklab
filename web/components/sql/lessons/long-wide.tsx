import { factOf } from "../Fact";

// Lesson 6 of /sql. Every number comes from `sqlcourse/long-wide/facts.sql` through `f`.
const f = factOf("long-wide");

export function LongWideProse() {
  return (
    <>
      <section aria-labelledby="question-h">
        <h2 id="question-h">The question</h2>
        <p>
          The six wide tables have a column per metric. The seventh, <code>fact</code>, has one row per player,
          team, position and metric, with the metric&apos;s name in <code>metric</code> and its value in{" "}
          <code>value</code>: {f("fact_rows")} rows. That is the long shape. <code>fb_physical</code> holds{" "}
          {f("football_physical_metrics")} metrics in {f("fb_physical_rows")} rows; in <code>fact</code> the same
          numbers are at most {f("physical_rows_per_metric_max")} rows per metric, because an empty cell has no
          row there: <code>psv99</code> has {f("psv99_rows")} rows and <code>timetohsr_top3</code>{" "}
          {f("timetohsr_top3_rows")}, and <code>value</code> is never <code>NULL</code> ({f("null_values_in_fact")}{" "}
          empty values in the whole table).
        </p>
      </section>

      <section aria-labelledby="why-h">
        <h2 id="why-h">Why long</h2>
        <p>
          A long table takes a new metric without a new column, and a question over all metrics is one{" "}
          <code>GROUP BY</code>: how many metrics each family has ({f("football_passing_metrics")} for passing,{" "}
          {f("football_obr_metrics")} for off-ball runs, {f("basketball_shots_metrics")} for basketball shots) is a{" "}
          <code>count(DISTINCT metric)</code>. A question that compares two metrics of one player wants them side
          by side in one row: that is wide, and the wide tables are there for it. Knowing how to go from one
          shape to the other is the skill.
        </p>
      </section>

      <section aria-labelledby="pivot-h">
        <h2 id="pivot-h">PIVOT and the CASE equivalent</h2>
        <p>
          <code>PIVOT ... ON metric IN (...) USING max(value)</code> turns the metric names into columns.{" "}
          <code>PIVOT</code> is DuckDB&apos;s own syntax, and on this page it has to sit inside a <code>FROM</code>,
          as <code>SELECT * FROM (PIVOT ...)</code>, because the read-only gate only runs a statement that starts
          with <code>SELECT</code> or <code>WITH</code>. The portable way is conditional aggregation:{" "}
          <code>GROUP BY player_id</code> and one <code>max(CASE WHEN metric = &apos;psv99&apos; THEN value END) AS
          psv99</code> per column, which runs in any database; DuckDB also writes it as{" "}
          <code>max(value) FILTER (WHERE metric = &apos;psv99&apos;)</code>. The worked example takes{" "}
          {f("long_rows_of_example")} long rows of {f("example_players")} players and returns{" "}
          {f("example_players")} wide rows; the checker accepts any of the three ways, since it compares values,
          not syntax.
        </p>
      </section>
    </>
  );
}
