import { display } from "../../../lib/learn/display";
import { matchFig } from "../../../lib/learn/json-figure";
import type { PassMatch } from "../../../lib/learn/pass-data";
import { Fig } from "../Fig";

// One row per basketball match: how many passes were measured, the ball's chord speed (median and
// 90th percentile), its path over its chord, the provider's distance over the same time and the
// ball's chord over that distance, all medians. Every value is pass.json's; nothing is typed here.
const cell = (m: PassMatch, field: keyof PassMatch) => <Fig name={matchFig("pass", m.match_id, field)}>{String(m[field])}</Fig>;

export function PerMatch({ matches }: { matches: readonly PassMatch[] }) {
  return (
    <figure className="learn-fig surface-dark" data-figure="per-match">
      <div className="table-scroll">
        <table className="learn-matches">
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">passes measured</th>
              <th scope="col">chord speed, median (m/s)</th>
              <th scope="col">90th percentile (m/s)</th>
              <th scope="col">path over chord</th>
              <th scope="col">provider&apos;s distance over time (m/s)</th>
              <th scope="col">chord over distance</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{display(m.match_id, "match_id")}</td>
                <td>{cell(m, "n")}</td>
                <td>{cell(m, "chord_speed_median")}</td>
                <td>{cell(m, "chord_speed_p90")}</td>
                <td>{cell(m, "path_over_chord")}</td>
                <td>{cell(m, "distance_speed_median")}</td>
                <td>{cell(m, "chord_over_distance")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        Every complete pass that ends after it starts and has the ball at every frame of the way. The chord is the ball&apos;s
        displacement from the pass&apos;s first frame to its last, in three dimensions; the path adds up every step between; the
        provider&apos;s distance is the one its event gives. Every column but the first two is a median over the match&apos;s
        passes.
      </figcaption>
    </figure>
  );
}
