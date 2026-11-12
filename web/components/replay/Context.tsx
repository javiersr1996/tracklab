import type { IndexEntry } from "../../lib/data";
import { formatClock } from "../../lib/replay/engine";
import type { Possession } from "../../lib/replay/types";

// Beside the player on `/tracking/replay`: what the possession on show is, every figure read from
// its file (and its length from index.json, as the picker prints it). The file says which team has
// the ball but not which of the match's two names that team is, so the legend names roles.
export function ReplayContext({ possession, entry }: { possession: Possession; entry: IndexEntry }) {
  const first = possession.frames[0];
  const last = possession.frames[possession.frames.length - 1];
  const players = possession.entities.filter((e) => e.kind === "player").length;
  const clock = (s: number) => formatClock(s, possession.clock_kind);
  return (
    <aside className="head-panel replay-context" aria-label="About this possession" data-replay-context>
      <p className="head-panel-label">This possession</p>
      <dl className="replay-facts">
        <div>
          <dt>sport</dt>
          <dd data-context="sport">{possession.sport}</dd>
        </div>
        <div>
          <dt>match</dt>
          <dd data-context="match">
            {possession.match.home} v {possession.match.away}, {possession.match.kickoff_utc.slice(0, 10)}
          </dd>
        </div>
        <div>
          <dt>clock</dt>
          <dd data-context="clock">
            {clock(first.clock)} to {clock(last.clock)}
            {possession.clock_kind === "countdown" ? ", the game clock counting down" : ", the match clock counting up"}
          </dd>
        </div>
        <div>
          <dt>length</dt>
          <dd data-context="duration">{entry.duration_s} s</dd>
        </div>
        <div>
          <dt>sampled</dt>
          <dd data-context="rate">
            {possession.sample_rate_hz} times a second, {possession.frames.length} frames
          </dd>
        </div>
        <div>
          <dt>tracked</dt>
          <dd data-context="players">{players} players and the ball</dd>
        </div>
        <div>
          <dt>{possession.sport === "basketball" ? "court" : "pitch"}</dt>
          <dd data-context="surface">
            {possession.surface.length_m} by {possession.surface.width_m} m
          </dd>
        </div>
      </dl>
      <ul className="replay-legend" aria-label="Colours">
        <li>
          <span className="replay-swatch replay-swatch-attack" aria-hidden="true" /> the team with the ball
        </li>
        <li>
          <span className="replay-swatch replay-swatch-defence" aria-hidden="true" /> the other team
        </li>
        <li>
          <span className="replay-swatch replay-swatch-ball" aria-hidden="true" /> the ball, drawn larger the higher the data puts it
        </li>
      </ul>
      <p className="replay-context-about">
        One Canvas renderer draws both sports from the same <code>frames</code> schema: each frame lists
        every tracked entity in metres, and a faded disc is a player the provider did not see in that
        frame and placed by estimate.
      </p>
    </aside>
  );
}
