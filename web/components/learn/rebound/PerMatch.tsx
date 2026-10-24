import { reboundFig, type ReboundMatch } from "../../../lib/learn/rebound-data";
import type { ReboundFigures } from "../../../lib/learn/rebound-figures";
import { display } from "../../../lib/learn/display";
import { Fig } from "../Fig";

// One row per basketball match: how many rebounds raced, how often each rule named the player who
// took the rebound, how often they named the same player, the chance the model gave its own pick,
// and the median wait from the shot's end to the rebound. Counts are rebound.json's; percentages
// are computed from them (`rate` of `reboundFigures`). Nothing is typed here.
const COUNT = (m: ReboundMatch, field: keyof ReboundMatch) => <Fig name={reboundFig(m.match_id, field)}>{String(m[field])}</Fig>;

export function PerMatch({ matches, rate }: { matches: readonly ReboundMatch[]; rate: ReboundFigures["rate"] }) {
  const pct = (m: ReboundMatch, key: keyof ReboundFigures["rate"][string]) => (
    <Fig name={`learn.rate.${m.match_id}.${key}`}>{String(rate[m.match_id][key])}</Fig>
  );
  return (
    <figure className="learn-fig surface-dark learn-rebound-fig" data-figure="per-match">
      <div className="table-scroll">
        <table className="learn-rebound-matches">
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">rebounds raced</th>
              <th scope="col">model&apos;s first took it</th>
              <th scope="col">%</th>
              <th scope="col">nearest took it</th>
              <th scope="col">%</th>
              <th scope="col">same player, %</th>
              <th scope="col">model&apos;s chance for its pick, %</th>
              <th scope="col">median wait (s)</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.match_id} data-match={m.match_id}>
                <td>{display(m.match_id, "match_id")}</td>
                <td>{COUNT(m, "n")}</td>
                <td>{COUNT(m, "model")}</td>
                <td>{pct(m, "model")}</td>
                <td>{COUNT(m, "nearest")}</td>
                <td>{pct(m, "nearest")}</td>
                <td>{pct(m, "same")}</td>
                <td>{pct(m, "confidence")}</td>
                <td>{COUNT(m, "median_wait_s")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        Every rebound a player took after a missed field goal, with ten players on court at the end of the shot. The model is
        the time to arrive at the sources&apos; reaction time and top speed; the chance is the mean, over the match, of the chance
        it gave its own first of being first.
      </figcaption>
    </figure>
  );
}
