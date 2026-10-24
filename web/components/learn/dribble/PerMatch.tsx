import { display } from "../../../lib/learn/display";
import type { DribbleMatch } from "../../../lib/learn/dribble-data";
import { matchFig } from "../../../lib/learn/json-figure";
import { Fig } from "../Fig";

// One row per basketball match: the intervals between the dribbles of a touch (how many, median,
// 10th and 90th percentiles), the touches with the most dribbles, and the dribbles against the
// ball's height: how many have a whole window, how many find its lowest point near the event or
// at the window's edge, the median lowest height, and the consecutive pairs that share one low
// point. Every value is dribble.json's; nothing is typed here.
const cell = (m: DribbleMatch, field: keyof DribbleMatch) => <Fig name={matchFig("dribble", m.match_id, field)}>{String(m[field])}</Fig>;

export function PerMatch({ matches }: { matches: readonly DribbleMatch[] }) {
  return (
    <figure className="learn-fig surface-dark" data-figure="per-match">
      <div className="table-scroll">
        <table className="learn-matches">
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">intervals</th>
              <th scope="col">median (s)</th>
              <th scope="col">10th percentile (s)</th>
              <th scope="col">90th percentile (s)</th>
              <th scope="col">long touches</th>
              <th scope="col">windows</th>
              <th scope="col">lowest point near the event (%)</th>
              <th scope="col">at the edge (%)</th>
              <th scope="col">median lowest height (m)</th>
              <th scope="col">pairs</th>
              <th scope="col">sharing a low point</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{display(m.match_id, "match_id")}</td>
                <td>{cell(m, "intervals")}</td>
                <td>{cell(m, "interval_median_s")}</td>
                <td>{cell(m, "interval_p10_s")}</td>
                <td>{cell(m, "interval_p90_s")}</td>
                <td>{cell(m, "touches_3")}</td>
                <td>{cell(m, "windows")}</td>
                <td>{cell(m, "near_pct")}</td>
                <td>{cell(m, "edge_pct")}</td>
                <td>{cell(m, "low_z_median")}</td>
                <td>{cell(m, "pairs")}</td>
                <td>{cell(m, "shared_low")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        An interval is the time between two consecutive dribbles of one touch. A long touch has as many dribbles as the text says
        or more. A window is a dribble with the ball&apos;s height at every frame around it; near means its lowest point is within
        the frames the text gives, and the edge is the window&apos;s first or last frame. A pair is two consecutive dribbles of a
        touch that both have a window.
      </figcaption>
    </figure>
  );
}
