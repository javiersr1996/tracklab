import { speedFig, type SpeedMatch } from "../../../lib/learn/speed-data";
import { qualityFigure } from "../../../lib/learn/gravity-data";
import { QUALITY } from "../../../lib/quality";
import { Fig } from "../Fig";

// One row per basketball match: the gap between the provider's speed and three differences of
// the same rows, as speed.json has it, and P3's ratio to the backward difference as quality.json
// has it. Every figure is a `data-fig` naming its place in its file; nothing is typed here.
const COLUMNS: readonly { field: keyof SpeedMatch; label: string }[] = [
  { field: "triples", label: "triples" },
  { field: "r", label: "r, central" },
  { field: "median_gap", label: "central" },
  { field: "p99_gap", label: "central, 99th percentile" },
  { field: "median_gap_forward", label: "forward" },
  { field: "median_gap_backward", label: "backward" },
];

export const clockFig = (match_id: string) => `checks.clock.${match_id}.speed_ratio_median`;

export function PerMatch({ matches }: { matches: readonly SpeedMatch[] }) {
  return (
    <figure className="learn-fig surface-dark learn-speed-fig" data-figure="per-match">
      <div className="table-scroll">
        <table className="learn-speed-table">
          <thead>
            <tr>
              <th scope="col">match</th>
              {COLUMNS.map((c) => (
                <th key={c.field} scope="col">
                  {c.label}
                </th>
              ))}
              <th scope="col">ratio to backward, /quality</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{m.match_id}</td>
                {COLUMNS.map((c) => (
                  <td key={c.field}>
                    <Fig name={speedFig(m.match_id, c.field)}>{String(m[c.field])}</Fig>
                  </td>
                ))}
                <td>
                  <Fig name={clockFig(m.match_id)}>{String(qualityFigure(QUALITY, clockFig(m.match_id)))}</Fig>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        The gap columns are the median of |speed − estimate| in m/s, or its 99th percentile where the header says so,
        over every player row whose frames just before and just after are in the file. The last column is the median ratio of speed to the backward difference
        that the clock check on /quality published, over its own selection of frames.
      </figcaption>
    </figure>
  );
}
