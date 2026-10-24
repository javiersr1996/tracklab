import type { ClockMatch } from "../../../lib/learn/clock-data";
import type { ClockFigures } from "../../../lib/learn/clock-figures";
import { display } from "../../../lib/learn/display";
import { matchFig } from "../../../lib/learn/json-figure";
import { Fig } from "../Fig";

// One row per basketball match: the segments where the provider says the game clock runs, the
// median and quartiles of the game clock's slope against the video's, and the steps inside them
// where the game clock holds. Counts and slopes are clock.json's; the share of held steps is
// computed from them (`held_pct` of `clockFigures`). Nothing is typed here.
const cell = (m: ClockMatch, field: keyof ClockMatch) => <Fig name={matchFig("clock", m.match_id, field)}>{String(m[field])}</Fig>;

export function PerMatch({ matches, held }: { matches: readonly ClockMatch[]; held: ClockFigures["held_pct"] }) {
  return (
    <figure className="learn-fig surface-dark" data-figure="per-match">
      <div className="table-scroll">
        <table className="learn-matches">
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">split</th>
              <th scope="col">segments</th>
              <th scope="col">frames</th>
              <th scope="col">median slope</th>
              <th scope="col">Q1</th>
              <th scope="col">Q3</th>
              <th scope="col">held steps</th>
              <th scope="col">%</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{display(m.match_id, "match_id")}</td>
                <td>{m.calibration ? "calibration" : "control"}</td>
                <td>{cell(m, "segments")}</td>
                <td>{cell(m, "frames")}</td>
                <td>{cell(m, "slope_median")}</td>
                <td>{cell(m, "slope_q1")}</td>
                <td>{cell(m, "slope_q3")}</td>
                <td>{cell(m, "held")}</td>
                <td>
                  <Fig name={`learn.held_pct.${m.match_id}`}>{String(held[m.match_id])}</Fig>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        A segment is a run of consecutive frames inside one period where the provider says the game clock runs, five seconds or
        longer; the slope is the game clock&apos;s seconds per second of video, fitted by least squares over each segment, and a
        held step is one frame to the next with the game clock where it was. The split is the one the quality checks made. A
        clock that keeps the video&apos;s time counts down one second per second.
      </figcaption>
    </figure>
  );
}
