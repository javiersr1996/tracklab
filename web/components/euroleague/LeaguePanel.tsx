import { CURRENT_SEASON, type League, seasonLabel } from "../../lib/euroleague/atlas";
import { threeShare } from "../../lib/euroleague/data";
import { Count } from "../home/Count";

// The head panel of /euroleague (task 116): the league in each season, from league.json. The
// field goals, games and three-point share count up as they come into view (still under reduced
// motion and on the server), the last game is a date. A figure, like a lesson's result panel.
export function LeaguePanel({ league }: { league: League }) {
  const seasons = league.seasons;
  return (
    <figure className="head-panel el-panel" data-head-panel="league">
      <figcaption className="head-panel-label">The league</figcaption>
      <table className="el-panel-table">
        <thead>
          <tr>
            <td />
            {seasons.map((s) => (
              <th key={s.season} scope="col">
                {seasonLabel(s.season)}
                {s.season === CURRENT_SEASON ? <span className="el-panel-sofar"> so far</span> : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="el-panel-main">
            <th scope="row">Field goals</th>
            {seasons.map((s) => (
              <td key={s.season} data-panel={`${s.season}-shots`}>
                <Count value={s.shots_total} kind="int" />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Games</th>
            {seasons.map((s) => (
              <td key={s.season} data-panel={`${s.season}-games`}>
                <Count value={s.games_played} kind="int" />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Threes</th>
            {seasons.map((s) => (
              <td key={s.season} data-panel={`${s.season}-threes`}>
                <Count value={threeShare(s)} kind="num" />%
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Last game</th>
            {seasons.map((s) => (
              <td key={s.season} data-panel={`${s.season}-cutoff`}>
                {s.cutoff}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <p className="head-panel-about">
        <span className="head-panel-about-label">Threes</span> are three-point attempts as a share of all field
        goals.
      </p>
    </figure>
  );
}
