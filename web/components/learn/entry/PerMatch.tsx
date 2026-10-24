import { display } from "../../../lib/learn/display";
import { ENTRY_METRICS, entryFig, type EntryMatch } from "../../../lib/learn/entry-data";
import { Fig } from "../Fig";

// One row per basketball match: the entry-angle check of the quality page (P3), as quality.json
// publishes it. Nothing is computed or typed here.
const cell = (m: EntryMatch, key: keyof typeof ENTRY_METRICS) => <Fig name={entryFig(m.match_id, ENTRY_METRICS[key])}>{String(m[key])}</Fig>;

export function PerMatch({ matches }: { matches: readonly EntryMatch[] }) {
  return (
    <figure className="learn-fig surface-dark" data-figure="per-match">
      <div className="table-scroll">
        <table className="learn-matches">
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">split</th>
              <th scope="col">made shots kept</th>
              <th scope="col">reported angle, median (°)</th>
              <th scope="col">required angle, median (°)</th>
              <th scope="col">gap, median (°)</th>
              <th scope="col">pairs in a different order (%)</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{display(m.match_id, "match_id")}</td>
                <td>{m.calibration ? "calibration" : "control"}</td>
                <td>{cell(m, "shots")}</td>
                <td>{cell(m, "reported")}</td>
                <td>{cell(m, "required")}</td>
                <td>{cell(m, "gap")}</td>
                <td>{cell(m, "reordered")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        Every made, unblocked shot the check keeps. The gap is the median of each shot&apos;s required angle minus its reported
        one; the last column is the share of pairs of shots that the two angles put in a different order. The split is the one the
        quality checks made.
      </figcaption>
    </figure>
  );
}
