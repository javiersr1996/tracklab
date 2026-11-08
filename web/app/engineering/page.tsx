import { Flow } from "../../components/platform/Flow";
import { Lineage } from "../../components/platform/Lineage";
import { StepGantt } from "../../components/platform/StepGantt";
import { Band, PageHead } from "../../components/site/Band";
import { pluralize } from "../../lib/format";
import { LEAGUE } from "../../lib/euroleague/data";
import { firstBeforeBars, firstEvents, LINEAGE, PLATFORM, poseShare, silverModelRows } from "../../lib/platform";
import { DATA_SOURCES, EUROLEAGUE } from "../../lib/sections";
import pgJson from "../../public/data/warehouse_pg.json";
import { sectionMetadata } from "../../lib/page-metadata";

export const metadata = sectionMetadata("/engineering");

// `raw_sources[].source_id` (the manifest's) to the name `DATA_SOURCES` gives the same repository.
const skillcorner = (id: string) =>
  DATA_SOURCES.find((s) => s.name === (id === "opendata-football" ? "SkillCorner/opendata" : `SkillCorner/${id}`));

const PG = pgJson as {
  measured_at: string;
  source: { version: string; where: string; where_id: string };
  database_bytes: number;
  tables: { table: string; rows: number }[];
};
const n = (v: number) => v.toLocaleString("en-US");

const MATCH_FIELDS = [
  "sport",
  "match_id",
  "raw_bytes",
  "raw_bytes_read",
  "bronze_tracking_rows",
  "silver_frames_rows",
  "silver_events_rows",
  "published_possessions",
  "published_bytes",
] as const;

// `match_id` is an identifier, not a quantity: no thousands separator, same
// as `sport`. Every other field is a count or a byte figure, formatted like
// the rest of the site (`lib/format.ts`, `Flow.tsx`'s own `formatCount`).
function formatMatchField(field: (typeof MATCH_FIELDS)[number], value: string | number): string {
  if (field === "sport" || field === "match_id") return String(value);
  return (value as number).toLocaleString("en-US");
}

export default function PlatformPage() {
  const { run, matches, season_files: seasonFiles, guarantees: g } = PLATFORM;
  const pose = poseShare();
  const stepSeconds = PLATFORM.steps.reduce((s, st) => s + st.duration_ms / 1000, 0);
  const first = firstEvents();
  const modelRows = silverModelRows();
  const seedCount = modelRows.filter((r) => r.key.startsWith("seed_")).length;
  const viewCount = modelRows.filter((r) => r.rows === null && !r.key.startsWith("seed_")).length;

  return (
    <main className="page">
      <PageHead eyebrow="How this was built">
        <h1>{PLATFORM.title}</h1>
        <p className="platform-subtitle lede" data-subtitle>
          {PLATFORM.subtitle}
        </p>
        <p>
          One pipeline run, {PLATFORM.layers.length} layers: raw, bronze, silver, gold, quality,
          publish. Each layer&apos;s
          counters are the figures <code>tracklab build</code> and <code>tracklab publish
          platform</code> measured on this run, read from{" "}
          <a href="/data/platform.json">platform.json</a>, never typed by hand.
        </p>
        <ul className="platform-stack" data-stack>
          {Object.entries(run.versions).map(([tool, version]) => (
            <li key={tool} data-tool={tool}>
              {tool} <span>{version}</span>
            </li>
          ))}
          <li>Parquet</li>
          <li data-tool="postgres">Postgres <span>{PG.source.version}</span></li>
        </ul>
        {pose && (
          <p data-pose-share>
            Of the {(pose.bytes + pose.otherBytes).toLocaleString("en-US")} raw bytes,{" "}
            {pose.bytes.toLocaleString("en-US")} come from the{" "}
            {pluralize(pose.files, "body-pose zip")} of opendata-bodypose that P6 added (see{" "}
            <a href="/tracking/pose">/tracking/pose</a>); the other sources account for{" "}
            {pose.otherBytes.toLocaleString("en-US")}.
          </p>
        )}
      </PageHead>
      <Band dark>
        <Flow layers={PLATFORM.layers} />
        <footer className="platform-footer">
          <p>
            Run {run.git_sha} on {run.started_utc.slice(0, 10)}, {run.host.system},{" "}
            {run.host.cpus} CPUs, {run.host.ram_gb} GiB RAM, wall clock {run.wall_seconds}s: one run
            on one machine; steps ran in parallel, so per-step seconds do not add up to the wall
            clock.
          </p>
        </footer>
        <h2>Time, per step</h2>
        {first ? (
          <p data-gantt-note data-placed="end">
            The {PLATFORM.steps.length} steps of the run, grouped by layer, from{" "}
            <code>platform.json</code>; the axis ends at the run&apos;s {run.wall_seconds} s wall
            clock. Each bar ends at the step&apos;s last event in Dagster&apos;s event log and is as
            long as the step&apos;s own <code>duration_ms</code>, so it sits where the step ran. The
            log&apos;s first event is not used as a start
            {firstBeforeBars(first) ? (
              <>
                : for every step it falls {first.min.toFixed(1)} to {first.max.toFixed(1)} s into the
                run, before the first bar begins at {first.firstStart.toFixed(1)} s, so that span would
                start all the bars at once
              </>
            ) : null}
            . The bars add
            up to {stepSeconds.toFixed(1)} s because steps ran in parallel. Each run of every build
            is on <a href="/engineering/history">/engineering/history</a>.
          </p>
        ) : (
          <p data-gantt-note data-placed="zero">
            The {PLATFORM.steps.length} steps of the run, grouped by layer, each bar its duration in
            seconds from <code>platform.json</code>; the axis ends at the run&apos;s {run.wall_seconds}{" "}
            s wall clock. The bars add up to {stepSeconds.toFixed(1)} s because steps ran in parallel.
            The record keeps how long each step took, not when it started, so every bar starts at 0.
          </p>
        )}
        <StepGantt platform={PLATFORM} />
      </Band>
      <Band>
        <h2>Sources</h2>
        <p>
          Two kinds of ingest. SkillCorner is a pinned commit with a sha256 per file; EuroLeague is
          a public API pulled incrementally at a limited rate, with only aggregates published.
          The last line of each card says whether its bytes are in the <q>out</q> of the title.
        </p>
        <ul className="platform-sources" data-sources>
          {PLATFORM.raw_sources.map((src) => {
            const meta = skillcorner(src.source_id);
            return (
              <li key={src.source_id} data-source={src.source_id}>
                <h3>{meta ? <a href={meta.href}>{meta.name}</a> : src.source_id}</h3>
                <dl>
                  <dt>ingest</dt>
                  <dd>pinned commit, sha256 per file, idempotent download</dd>
                  <dt>in</dt>
                  <dd>
                    {meta?.what}: <span data-field="files">{src.files}</span> files,{" "}
                    <span data-field="bytes">{src.bytes.toLocaleString("en-US")}</span> bytes
                  </dd>
                  <dt>license</dt>
                  <dd>{meta?.license}</dd>
                  <dt>counts in out</dt>
                  <dd data-counts-in-out="yes">yes</dd>
                </dl>
              </li>
            );
          })}
          <li data-source="euroleague">
            <h3>
              <a href={EUROLEAGUE.href}>{EUROLEAGUE.name}</a>
            </h3>
            <dl>
              <dt>ingest</dt>
              <dd>public API, incremental by manifest, rate-limited</dd>
              <dt>in</dt>
              <dd>
                {EUROLEAGUE.what}:{" "}
                {LEAGUE.seasons.map((s, i) => (
                  <span key={s.season} data-season={s.season}>
                    {i > 0 ? "; " : ""}
                    <span data-field="games">{s.games_played}</span> games to{" "}
                    <span data-field="cutoff">{s.cutoff}</span>
                  </span>
                ))}
              </dd>
              <dt>license</dt>
              <dd>
                no open license: aggregates only, at least <span data-field="k">{LEAGUE.hex.k}</span>{" "}
                shots per hexagon
              </dd>
              <dt>counts in out</dt>
              <dd data-counts-in-out="no">no (another source, another license)</dd>
            </dl>
          </li>
        </ul>
      </Band>
      <Band dark>
        <h2>Guarantees</h2>
        <p>
          What stops a wrong number from reaching this site, counted by{" "}
          <code>tracklab publish platform</code> in the dbt manifest, the contract test folder and
          the command line itself; its <code>--check</code> fails if any count changes.
        </p>
        <ul className="platform-cards platform-guarantees" data-guarantees>
          <li data-guarantee="dbt">
            <h3>
              <span data-field="dbt.total">{g.dbt.total}</span> dbt tests
            </h3>
            <p>
              <span data-field="dbt.generic">{g.dbt.generic}</span> generic, on each model&apos;s
              columns:{" "}
              {Object.entries(g.dbt.by_kind)
                .map(([kind, count]) => `${count} ${kind}`)
                .join(", ")}
              . <span data-field="dbt.singular">{g.dbt.singular.length}</span> singular, for rules a
              column test cannot say, like <code>{g.dbt.singular[0]}</code>.
            </p>
            <details>
              <summary>The singular tests</summary>
              <ul data-list="dbt.singular">
                {g.dbt.singular.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </details>
          </li>
          <li data-guarantee="contracts">
            <h3>
              <span data-field="contracts.files">{g.contracts.files}</span> contract tests
            </h3>
            <p>
              Each file reads the Parquet built from the real bundles and asserts what the next
              layer relies on. <code>test_frames</code> rebuilds the row count of every match from
              bronze with its own SQL and compares it with silver.
            </p>
            <details>
              <summary>The contract files</summary>
              <ul data-list="contracts.names">
                {g.contracts.names.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </details>
          </li>
          <li data-guarantee="checks">
            <h3>
              <span data-field="checks.count">{g.checks.count}</span> <code>--check</code> commands
            </h3>
            <p>
              Each recomputes a published file and compares it with the versioned one, writing
              nothing. <code>publish platform --check</code> recounts rows by table and by match
              against an independent <code>stats.json</code>.
            </p>
            <details>
              <summary>The commands</summary>
              <ul data-list="checks.commands">
                {g.checks.commands.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
            </details>
          </li>
        </ul>
      </Band>
      <Band>
        <h2>Postgres</h2>
        <p data-postgres>
          Gold also loads into Postgres, the second path next to the Parquet the browser reads,
          with <code>tracklab load postgres</code>. Each row carries a 16-byte sha256 fingerprint;
          one transaction compares the gold with the tables by key and fingerprint, inserts the new
          keys, updates the changed rows and deletes the missing ones, so loading the same gold twice
          writes no row.
        </p>
        <dl className="platform-pg" data-pg>
          <dt>holds</dt>
          <dd>
            {PG.tables.map((t, i) => (
              <span key={t.table} data-pg-table={t.table}>
                {i > 0 ? ", " : ""}
                {t.table} <span data-field="rows">{n(t.rows)}</span>
              </span>
            ))}{" "}
            rows
          </dd>
          <dt>measured on</dt>
          <dd>
            <span data-field="where">{PG.source.where}</span>, {PG.measured_at.slice(0, 10)},{" "}
            <span data-field="bytes">{n(PG.database_bytes)}</span> bytes
          </dd>
          <dt>not shown</dt>
          <dd>
            The load is a command, not a Dagster asset, so it is not in the lineage graph below;
            adding a node for it would draw something the orchestrator does not run.
          </dd>
        </dl>
        <details data-pg-proof>
          <summary>What proves it</summary>
          <p>
            pytest <code>test_a_second_load_of_the_same_gold_writes_no_row</code> in{" "}
            <code>tests/postgres/test_load_postgres.py</code>, which loads twice and compares the
            row counts. The e2e <code>warehouse-pg</code>{" "}
            proves /warehouse falls back to the snapshot when the database does not answer; its live
            case needs a database URL{PG.source.where_id === "neon" ? "." : " and has not run against Neon."}
          </p>
        </details>
      </Band>
      <Band dark>
        <h2>Lineage</h2>
        <p>
          The Dagster asset graph (<a href="/data/lineage.json">lineage.json</a>), {LINEAGE.nodes.length}{" "}
          nodes and {LINEAGE.edges.length} edges, exported by <code>tracklab publish lineage</code>{" "}
          and checked against the graph by <code>tracklab publish lineage --check</code>. Hover or click a node to trace its upstream and downstream dependencies.
        </p>
        <Lineage lineage={LINEAGE} />
      </Band>
      <Band>
        <h2>Bytes and rows, per match</h2>
        <p>
          The {matches.length} matches behind every figure above, read from{" "}
          <a href="/data/platform.json">platform.json</a>&apos;s own <code>matches[]</code>; the
          season-level files (aggregates, <code>matches.json</code>, player aliases, the body-pose
          sample) are not attributed to any one match and are totalled separately below.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {MATCH_FIELDS.map((field) => (
                  <th scope="col" key={field}>
                    {field}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => (
                <tr key={m.match_id}>
                  {MATCH_FIELDS.map((field) => (
                    <td key={field} data-match={m.match_id} data-field={field}>
                      {formatMatchField(field, m[field])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Season files: {seasonFiles.files} files, {seasonFiles.bytes.toLocaleString("en-US")} bytes,
          not part of any match above.
        </p>

        <h2>Silver models</h2>
        <p>
          The {modelRows.length} dbt-owned nodes of the silver group ({modelRows.length - seedCount}{" "}
          models, {seedCount} seeds): tests and columns from{" "}
          <a href="/data/lineage.json">lineage.json</a>&apos;s own read of{" "}
          <code>dbt/target/manifest.json</code>, rows and bytes from{" "}
          <a href="/data/platform.json">platform.json</a>&apos;s <code>tables[]</code> where the
          model writes an actual Parquet file ({pluralize(viewCount, "view")} and{" "}
          {pluralize(seedCount, "seed")} don&apos;t, so those cells stay blank rather than showing an
          invented 0).
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">model</th>
                <th scope="col">dbt columns</th>
                <th scope="col">dbt tests</th>
                <th scope="col">rows</th>
                <th scope="col">bytes</th>
                <th scope="col">dbt seconds</th>
              </tr>
            </thead>
            <tbody>
              {modelRows.map((row) => (
                <tr key={row.key}>
                  <td data-model={row.key} data-field="key">
                    {row.key}
                  </td>
                  <td data-model={row.key} data-field="dbt_columns">
                    {row.dbt_columns.length}
                  </td>
                  <td data-model={row.key} data-field="dbt_tests">
                    {row.dbt_tests}
                  </td>
                  <td data-model={row.key} data-field="rows">
                    {row.rows === null ? "" : row.rows.toLocaleString("en-US")}
                  </td>
                  <td data-model={row.key} data-field="bytes">
                    {row.bytes === null ? "" : row.bytes.toLocaleString("en-US")}
                  </td>
                  <td data-model={row.key} data-field="dbt_seconds">
                    {row.dbt_seconds === null ? "" : row.dbt_seconds.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Band>
    </main>
  );
}
