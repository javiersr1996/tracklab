import { HookAnimation } from "../../components/quality/Hook";
import { cellKey, HOOK, matchRows, TABLE_METRICS } from "../../lib/quality";

export default function QualityPage() {
  const rows = matchRows();
  return (
    <main className="page">
      <h1>Data quality</h1>
      <p>
        A calibration kit for anyone building on the two bundles: five checks, one figure per
        match, read from the same reports as <a href="/bulletin">the bulletin</a>.
      </p>
      <HookAnimation hook={HOOK} />
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
    </main>
  );
}
