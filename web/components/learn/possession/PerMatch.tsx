import { display } from "../../../lib/learn/display";
import type { BasketballMatch, FootballMatch } from "../../../lib/learn/possession-data";
import type { PossessionLessonFigures } from "../../../lib/learn/possession-figures";
import { Fig } from "../Fig";

// Two tables, one row per match. Football: the provider's phases, the runs of same-team phases,
// their median and 90th percentile, and the share that spans more than one phase. Basketball: the
// provider's possessions, their median and 90th percentile. In both, the 90th percentile over the
// median, computed from the row (`*_ratio` of `lessonPossessionFigures`). Nothing is typed here.
const fbCell = (m: FootballMatch, field: keyof FootballMatch) => <Fig name={`possession.football.matches.${m.match_id}.${field}`}>{String(m[field])}</Fig>;
const bbCell = (m: BasketballMatch, field: keyof BasketballMatch) => <Fig name={`possession.basketball.matches.${m.match_id}.${field}`}>{String(m[field])}</Fig>;

export function PerMatch({
  football,
  basketball,
  ratios,
}: {
  football: readonly FootballMatch[];
  basketball: readonly BasketballMatch[];
  ratios: Pick<PossessionLessonFigures, "fb_ratio" | "bb_ratio">;
}) {
  return (
    <figure className="learn-fig surface-dark" data-figure="per-match">
      <div className="table-scroll">
        <table className="learn-matches" data-sport="football">
          <caption>Football</caption>
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">phases</th>
              <th scope="col">runs</th>
              <th scope="col">median (s)</th>
              <th scope="col">90th percentile (s)</th>
              <th scope="col">over the median</th>
              <th scope="col">over more than one phase (%)</th>
            </tr>
          </thead>
          <tbody>
            {football.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{display(m.match_id, "match_id")}</td>
                <td>{fbCell(m, "phases")}</td>
                <td>{fbCell(m, "runs")}</td>
                <td>{fbCell(m, "run_median_s")}</td>
                <td>{fbCell(m, "run_p90_s")}</td>
                <td>
                  <Fig name={`learn.fb_ratio.${m.match_id}`}>{String(ratios.fb_ratio[m.match_id])}</Fig>
                </td>
                <td>{fbCell(m, "multi_phase_pct")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-scroll">
        <table className="learn-matches" data-sport="basketball">
          <caption>Basketball</caption>
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">possessions</th>
              <th scope="col">median (s)</th>
              <th scope="col">90th percentile (s)</th>
              <th scope="col">over the median</th>
            </tr>
          </thead>
          <tbody>
            {basketball.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{display(m.match_id, "match_id")}</td>
                <td>{bbCell(m, "possessions")}</td>
                <td>{bbCell(m, "median_s")}</td>
                <td>{bbCell(m, "p90_s")}</td>
                <td>
                  <Fig name={`learn.bb_ratio.${m.match_id}`}>{String(ratios.bb_ratio[m.match_id])}</Fig>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        A football run is a stretch of consecutive phases of one period with the same team in possession; a basketball possession
        is the provider&apos;s own. Times are the video&apos;s, from the first frame to the last. The football matches are the ten
        the lesson may use; the others are not read.
      </figcaption>
    </figure>
  );
}
