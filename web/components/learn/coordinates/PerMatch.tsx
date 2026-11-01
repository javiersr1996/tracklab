import { clockFig, HOME_STEMS, type MatchCoordinates, possession, possessionFig, statsFig } from "../../../lib/learn/coordinates-data";
import type { Sport } from "../../../lib/replay/types";
import { display } from "../../../lib/learn/display";
import { Fig } from "../Fig";

// One row per match: how its frame clock steps, how many rows it puts in `frames`, and, where a
// possession of it is published, the surface and the attack sign that possession carries. Every
// figure is a `data-fig` naming its file and path; `learn.minutes.<match>` is computed from them.
const fmt = (n: number) => String(n);
const sign = (k: number) => (k > 0 ? "+1" : "−1");

function Rows({ sport, rows }: { sport: Sport; rows: readonly MatchCoordinates[] }) {
  const home = HOME_STEMS[sport];
  return (
    <tbody>
      <tr className="learn-coordinates-sport">
        <th scope="rowgroup" colSpan={7}>
          {sport === "basketball" ? "Basketball" : "Football"}, <Fig name={possessionFig(home, "sample_rate_hz")}>{possession(home).sample_rate_hz}</Fig>&nbsp;Hz
        </th>
      </tr>
      {rows.map((m) => {
        const p = m.stem ? possession(m.stem) : null;
        return (
          <tr key={m.match_id} data-match={m.match_id}>
            <th scope="row">{display(m.match_id, "match_id")}</th>
            <td>
              <Fig name={clockFig(m.match_id, true)}>{fmt(m.steps)}</Fig>
            </td>
            <td>
              <Fig name={clockFig(m.match_id)}>{m.exact_pct}</Fig>
            </td>
            <td>
              <Fig name={`learn.minutes.${m.match_id}`}>{m.minutes}</Fig>
            </td>
            <td>
              <Fig name={statsFig("frames", m.match_id)}>{fmt(m.rows)}</Fig>
            </td>
            <td>
              {p && m.stem ? (
                <>
                  <Fig name={possessionFig(m.stem, "surface.length_m")}>{p.surface.length_m}</Fig>&nbsp;×&nbsp;
                  <Fig name={possessionFig(m.stem, "surface.width_m")}>{p.surface.width_m}</Fig>
                </>
              ) : (
                "not published"
              )}
            </td>
            <td>{p && m.stem ? <Fig name={possessionFig(m.stem, "attack_sign")}>{sign(p.attack_sign)}</Fig> : "not published"}</td>
          </tr>
        );
      })}
    </tbody>
  );
}

export function PerMatch({ matches }: { matches: readonly MatchCoordinates[] }) {
  return (
    <figure className="learn-fig learn-coordinates-table" data-figure="per-match">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">frame steps checked</th>
              <th scope="col">steps exact (%)</th>
              <th scope="col">minutes they cover</th>
              <th scope="col">rows in frames</th>
              <th scope="col">surface (m)</th>
              <th scope="col">attack sign</th>
            </tr>
          </thead>
          {(["basketball", "football"] as const).map((sport) => (
            <Rows key={sport} sport={sport} rows={matches.filter((m) => m.sport === sport)} />
          ))}
        </table>
      </div>
      <figcaption>
        The steps and their exactness are the clock check of /engineering/quality; the rows are the build&apos;s count for{" "}
        <code>frames</code>. Surface and sign come from the match&apos;s published possession: the sign is that of the team
        with the ball, in the period the possession was played.
      </figcaption>
    </figure>
  );
}
