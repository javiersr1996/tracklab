import { CheckCharts } from "../../../components/quality/CheckCharts";
import { HookAnimation } from "../../../components/quality/Hook";
import { Band, PageHead } from "../../../components/site/Band";
import { cellKey, formatMetric, HOOK, matchRows, tabulatedChecks, TABLE_METRICS } from "../../../lib/quality";
import { sectionMetadata } from "../../../lib/page-metadata";

export const metadata = sectionMetadata("/engineering/quality");

export default function QualityPage() {
  const rows = matchRows();
  return (
    <main id="main" className="page">
      <PageHead eyebrow="One figure per match">
        <h1>Data quality</h1>
        <p className="lede" data-lede>
          Tracking data is never perfect, and this page measures where it is off: how often the ball
          and the players are actually seen, how much their positions jitter, whether a ball in flight
          falls at real gravity. Each check is measured match by match, so you can see how far to trust
          each one.
        </p>
        <p>
          A calibration kit for anyone building on the two bundles: {tabulatedChecks().length} checks, one figure per
          match, read from the same reports as <a href="/engineering/bulletin">the bulletin</a>.
        </p>
      </PageHead>
      <Band dark>
        <HookAnimation hook={HOOK} />
      </Band>
      <Band>
        <h2>Check by check</h2>
        <p>
          One chart per column of the table below: a dot per match, basketball and football on their own rows, a white
          line at each sport&apos;s median. Where a check does not apply to a sport the row says so instead of a dot.
        </p>
        <CheckCharts />
        <details className="qtable" data-quality-table>
          <summary>All {rows.length} matches, as a table</summary>
          <p>
            Rounded for reading; hover or long-press a figure for the value as{" "}
            <a href="/data/quality.json">quality.json</a> writes it. An empty cell is a check that does not apply to
            that sport.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">match</th>
                  <th scope="col">sport</th>
                  {TABLE_METRICS.map((m) => (
                    <th scope="col" key={cellKey(m.check, m.metric)}>
                      {m.label} ({m.unit})
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.match_id}>
                    <td>{row.match_id}</td>
                    <td>{row.sport}</td>
                    {TABLE_METRICS.map((m) => {
                      const key = cellKey(m.check, m.metric);
                      const value = row.cells[key];
                      return (
                        <td
                          key={key}
                          data-check={m.check}
                          data-metric={m.metric}
                          data-match={row.match_id}
                          title={value === undefined ? undefined : String(value)}
                        >
                          {value === undefined ? "" : formatMetric(m, value)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Band>
    </main>
  );
}
