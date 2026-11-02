import type { Metadata } from "next";
import {
  FreshnessStrip,
  QualityTable,
  QualityTimeline,
  selectLabel,
  StepStrips,
  StepTable,
} from "../../../components/platform/HistoryCharts";
import { Band, PageHead } from "../../../components/site/Band";
import { freshnessRows, HISTORY, MIN_EARLIER, modeSummary, runLabel, seriesOf, stepMode } from "../../../lib/history";
import { PLATFORM } from "../../../lib/platform";

export const metadata: Metadata = { title: "Build history | Track Lab" };

const s1 = (v: number) => v.toFixed(1);
const day = (id: string) => runLabel(id).slice(0, 10);

function Legend() {
  const dot = (cls: string, r = 3.5) => (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <circle className={cls} cx="7" cy="7" r={r} />
    </svg>
  );
  const tick = (cls: string) => (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <line className={cls} x1="7" x2="7" y1="0" y2="14" />
    </svg>
  );
  return (
    <ul className="history-legend" data-legend>
      <li>{dot("strip-dot")} an earlier run, same mode as the last</li>
      <li>{dot("strip-other")} an earlier run, another mode</li>
      <li>{dot("strip-last", 5)} the last run</li>
      <li>{tick("strip-median")} median of the earlier runs, same mode</li>
      <li>{tick("strip-threshold")} threshold: that median plus their spread</li>
    </ul>
  );
}

export default function HistoryPage() {
  const entries = [...HISTORY.entries].sort((a, b) => a.id.localeCompare(b.id));
  const series = seriesOf(entries);
  const charted = series.filter((s) => s.runs.length >= 2);
  const once = series.filter((s) => s.runs.length === 1);

  // P16 in numbers: the selection whose silver step ran in all three modes.
  const p16 = series.find((s) => {
    const silver = s.steps.find((x) => x.step_key === "silver");
    return silver && ["full", "skip", "incremental"].every((m) => silver.points.some((p) => p.mode === m));
  });
  const modes = p16 ? modeSummary(p16, ["silver", "gold"]) : [];
  const mode = (step: string, m: string) => modes.find((x) => x.step_key === step && x.mode === m);
  // How many of how many matches the incremental runs rewrote, when they all rewrote as many.
  const incSplits = [
    ...new Set(
      (p16?.runs ?? []).flatMap((e) =>
        e.steps
          .filter((x) => x.step_key === "silver" && stepMode(x) === "incremental" && x.partitions)
          .map((x) => `${x.partitions!.written}/${(x.partitions!.written ?? 0) + (x.partitions!.skipped ?? 0)}`),
      ),
    ),
  ];
  const incSplit = incSplits.length === 1 ? incSplits[0].split("/").map(Number) : null;

  const complete = series.find((s) => s.select === null);
  const lastComplete = complete?.runs[complete.runs.length - 1];
  const lastSteps = lastComplete?.steps.filter((x) => x.duration_ms !== null) ?? [];
  const longest = lastSteps.reduce<(typeof lastSteps)[number] | null>(
    (m, x) => (m === null || x.duration_ms! > m.duration_ms! ? x : m),
    null,
  );
  const stepOf = (k: string) => lastSteps.find((x) => x.step_key === k);

  const ran = entries.filter((e) => e.quality.contracts.executed === true);
  const noDbt = entries.filter((e) => e.quality.dbt.tests === null);

  const fresh = freshnessRows();
  const runStart = new Date(PLATFORM.run.started_utc).getTime();
  const dirs = PLATFORM.freshness.partitions;
  const before = dirs.filter((p) => new Date(p.written_utc).getTime() < runStart).length;
  const platformEntry = entries.find((e) => e.started_utc.slice(0, 19) === PLATFORM.run.started_utc.slice(0, 19));
  const modeIn = (k: string) => {
    const st = platformEntry?.steps.find((x) => x.step_key === k);
    return st ? stepMode(st) : null;
  };

  return (
    <main className="page">
      <PageHead eyebrow="Every build, kept">
        <h1>Build history</h1>
        <p className="lede" data-history-lede>
          {entries.length} <code>tracklab build</code> records, from {day(entries[0].id)} to{" "}
          {day(entries[entries.length - 1].id)}, as <code>tracklab publish history</code> copied them
          into <a href="/data/history.json">history.json</a>, which only ever adds entries. A run is
          compared only with runs of the same selection: a partial build never sits next to a complete
          one.
        </p>
      </PageHead>
      <Band dark>
        <h2>Step time, run by run</h2>
        <p>
          One strip per step, each run a dot on a logarithmic seconds axis. The last run of a step is
          judged against the earlier runs of the same selection and the same mode (the record&apos;s{" "}
          <code>incremental.mode</code>: full, incremental or skip; none where the record keeps
          none): the threshold is their median plus their spread, the slowest minus the fastest. A
          last run above it is flagged; with fewer than {MIN_EARLIER} such runs there is no threshold.
          The records keep no measure of the machine&apos;s load, so a flag says a run was slower
          than every spread so far allowed, not why.
        </p>
        <Legend />
        {p16 && mode("silver", "full") && mode("silver", "skip") && mode("silver", "incremental") && (
          <p data-p16>
            What P16&apos;s incremental silver changed, in the {p16.runs.length} runs of{" "}
            <code>{p16.select}</code>: silver took a median of{" "}
            <span data-field="silver.full">{s1(mode("silver", "full")!.median)}</span>{"\u00a0"}s rebuilding every
            match ({mode("silver", "full")!.runs} runs) and{" "}
            <span data-field="silver.skip">{s1(mode("silver", "skip")!.median)}</span>{"\u00a0"}s when no input had
            changed ({mode("silver", "skip")!.runs} runs, dbt not run). With{" "}
            {incSplit ? `${incSplit[0]} of ${incSplit[1]} matches` : "some matches"} rewritten it took a
            median of <span data-field="silver.incremental">{s1(mode("silver", "incremental")!.median)}</span>
            {"\u00a0"}s ({mode("silver", "incremental")!.runs} runs, {s1(mode("silver", "incremental")!.min)} to{" "}
            {s1(mode("silver", "incremental")!.max)}{"\u00a0"}s)
            {incSplit && incSplit[0] === 1 && (
              <>, far from 1/{incSplit[1]} of a full rebuild</>
            )}
            : its dbt still ran all {mode("silver", "incremental")!.tests ?? "its"} silver tests, as many as
            a full run.
            {longest && lastComplete && stepOf("silver") && stepOf("gold") && (
              <>
                {" "}
                The complete build is not faster for it: its last run, {runLabel(lastComplete.id)}, took{" "}
                <span data-field="complete.wall">{s1(lastComplete.wall_seconds)}</span>{"\u00a0"}s of wall clock
                with silver at {s1(stepOf("silver")!.duration_ms! / 1000)} s and gold at{" "}
                {s1(stepOf("gold")!.duration_ms! / 1000)}{"\u00a0"}s ({stepMode(stepOf("silver")!)} and{" "}
                {stepMode(stepOf("gold")!)}), while its longest step, <code>{longest.step_key}</code>,
                took <span data-field="complete.longest">{s1(longest.duration_ms! / 1000)}</span>{"\u00a0"}s on its
                own.
              </>
            )}
          </p>
        )}
        {charted.map((s, i) => {
          const judged = s.steps.filter((x) => x.verdict !== "too few");
          const above = judged.filter((x) => x.verdict === "above");
          const reasons = s.steps.filter((x) => x.lastStep.incremental);
          const id = s.select ?? "complete";
          return (
            <section key={id} className="history-series" data-series={id} data-runs={s.runs.length}>
              <h3>
                {selectLabel(s.select)} · {s.runs.length} runs, {day(s.runs[0].id)} to{" "}
                {day(s.runs[s.runs.length - 1].id)}
              </h3>
              <p data-verdicts>
                In its last run, {above.length} of the {judged.length} steps with a threshold are above
                it
                {above.length > 0 && (
                  <>
                    {" "}
                    ({above.map((x) => x.step_key).join(", ")})
                  </>
                )}
                ; {s.steps.length - judged.length} of {s.steps.length} have too few earlier runs in their
                mode.
              </p>
              <StepStrips series={s} id={`series-${i}`} />
              <p data-reasons>
                {reasons.length > 0 ? (
                  <>
                    The last run&apos;s reason, from its record:{" "}
                    {reasons.map((x, k) => (
                      <span key={x.step_key} data-reason={x.step_key}>
                        {k > 0 ? "; " : ""}
                        <code>{x.step_key}</code> ({x.lastStep.incremental!.mode}): {x.lastStep.incremental!.reason}
                      </span>
                    ))}
                    . The other {s.steps.length - reasons.length} steps keep no reason: no data.
                  </>
                ) : (
                  <>No step of the last run keeps a reason: no data.</>
                )}
              </p>
              <StepTable series={s} />
            </section>
          );
        })}
        {once.length > 0 && (
          <>
            <p>
              {once.length} selections ran once, so none of their steps has an earlier run to be
              judged against:
            </p>
            <div className="table-scroll">
              <table data-once>
                <thead>
                  <tr>
                    <th scope="col">selection</th>
                    <th scope="col">run</th>
                    <th scope="col">steps</th>
                    <th scope="col">wall seconds</th>
                  </tr>
                </thead>
                <tbody>
                  {once.map((s) => (
                    <tr key={s.select} data-run={s.runs[0].id}>
                      <td>{selectLabel(s.select)}</td>
                      <td>{runLabel(s.runs[0].id)}</td>
                      <td>{s.runs[0].steps.length}</td>
                      <td>{s1(s.runs[0].wall_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Band>
      <Band>
        <h2>Quality, run by run</h2>
        <p>
          The dbt tests each run&apos;s steps ran (summed from a v2 record, or for a v1 from the{" "}
          <code>run_results.json</code> inside its window) and its contract tests, oldest first.{" "}
          <q>no data</q> is a value the record does not hold, never 0: a v1 record kept the number of
          contract files at its commit, not a run of them, and a partial build does not run them.{" "}
          {pluralRuns(ran.length)} of {entries.length} ran the contracts; {noDbt.length} ran no dbt
          test the record or a <code>run_results.json</code> can show.
        </p>
        <QualityTimeline entries={entries} />
        <QualityTable entries={entries} />
      </Band>
      <Band dark>
        <h2>Freshness</h2>
        <p data-freshness-note>
          How old the data was when <a href="/data/platform.json">platform.json</a> was published, at{" "}
          <span data-field="published">{fresh.published_utc.replace("T", " ").replace("+00:00", " UTC")}</span>: for each silver partition and
          table and each gold table, the newest modification time of its Parquet files, read from the
          disk by <code>tracklab publish platform</code> at that instant; for its run, when the run
          finished.
          {modeIn("silver") && modeIn("gold") && (
            <>
              {" "}
              That run ({runLabel(platformEntry!.id)}) ran silver in mode {modeIn("silver")} and gold in
              mode {modeIn("gold")}, and {before} of the {dirs.length} silver and gold directories were
              last written before it began.
            </>
          )}
        </p>
        <FreshnessStrip rows={fresh.rows} />
        <p>
          The run itself, step by step, is the Gantt of <a href="/engineering">/engineering</a>.
        </p>
      </Band>
    </main>
  );
}

const pluralRuns = (n: number) => (n === 1 ? "1 run" : `${n} runs`);
