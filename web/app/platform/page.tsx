import { Flow } from "../../components/platform/Flow";
import { Lineage } from "../../components/platform/Lineage";
import { LINEAGE, PLATFORM, silverModelRows } from "../../lib/platform";

const REPO = "https://github.com/javiersr1996/tracklab";

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
  const { run, matches, season_files: seasonFiles } = PLATFORM;
  const modelRows = silverModelRows();
  const seedCount = modelRows.filter((r) => r.key.startsWith("seed_")).length;

  return (
    <main className="page">
      <h1>{PLATFORM.title}</h1>
      <p>
        One pipeline run, five layers: raw, bronze, silver, quality, publish. Each layer&apos;s
        counters are the figures <code>tracklab build</code> and <code>tracklab publish
        platform</code> measured on this run, read from{" "}
        <a href="/data/platform.json">platform.json</a>, never typed by hand.
      </p>
      <Flow layers={PLATFORM.layers} />
      <footer className="platform-footer">
        <p>
          Run {run.git_sha} on {run.started_utc.slice(0, 10)}, {run.host.system},{" "}
          {run.host.cpus} CPUs, {run.host.ram_gb} GB RAM, wall clock {run.wall_seconds}s: one run
          on one machine; steps ran in parallel, so per-step seconds do not add up to the wall
          clock.
        </p>
      </footer>

      <h2>Lineage</h2>
      <p>
        The Dagster asset graph (<a href="/data/lineage.json">lineage.json</a>), {LINEAGE.nodes.length}{" "}
        nodes and {LINEAGE.edges.length} edges, exported once per push and checked byte for byte in
        CI. Hover or click a node to trace its upstream and downstream dependencies.
      </p>
      <Lineage lineage={LINEAGE} />

      <h2>Bytes and rows, per match</h2>
      <p>
        The 30 matches behind every figure above, read from{" "}
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
        model writes an actual Parquet file (two views and both seeds don&apos;t, so those cells
        stay blank rather than showing an invented 0). Column types and names are documented in{" "}
        <a href={`${REPO}/blob/main/docs/schema.md`}>docs/schema.md</a> (private repository).
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
    </main>
  );
}
