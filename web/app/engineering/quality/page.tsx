import { HookAnimation } from "../../../components/quality/Hook";
import { Band, PageHead } from "../../../components/site/Band";
import { cellKey, HOOK, matchRows, TABLE_METRICS } from "../../../lib/quality";
import { sectionMetadata } from "../../../lib/page-metadata";

export const metadata = sectionMetadata("/engineering/quality");

export default function QualityPage() {
  const rows = matchRows();
  return (
    <main id="main" className="page">
      <PageHead eyebrow="One figure per match">
        <h1>Data quality</h1>
        <p className="lede">
          A calibration kit for anyone building on the two bundles: five checks, one figure per
          match, read from the same reports as <a href="/engineering/bulletin">the bulletin</a>.
        </p>
      </PageHead>
      <Band dark>
        <HookAnimation hook={HOOK} />
      </Band>
      <Band>
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
                      <td key={key} data-check={m.check} data-metric={m.metric} data-match={row.match_id}>
                        {value === undefined ? "" : value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p data-check="entry_angle">
          Entry angle gap: part of the distance between the reported and the required angle comes
          from the method itself, and would remain even with a perfect flight. The{" "}
          <a href="/learn/entry">entry lesson</a> explains where.
        </p>
      </Band>
    </main>
  );
}
