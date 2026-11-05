"use client";

import { type CSSProperties, type KeyboardEvent, type PointerEvent, useState } from "react";
import {
  CUTS,
  cellAt,
  courtPaths,
  CURRENT_SEASON,
  type Drawn,
  fullAt,
  hexCenter,
  hexPath,
  hexScale,
  type League,
  leagueAverage,
  leagueDrawn,
  metresFromHoop,
  type Mode,
  pct,
  perShot,
  playerDrawn,
  readingOrder,
  seasonLabel,
  signedPp,
  signedPts,
  type Team,
  type TeamChanges,
  teamDrawn,
  type Tone,
  TONES,
  toneOf,
  VIEW,
} from "../../lib/euroleague/atlas";
import { pluralize } from "../../lib/format";
import { Band } from "../site/Band";
import type { Runs } from "../../lib/euroleague/runs";
import { Changes } from "./Changes";
import { Streaks } from "./Streaks";

const COURT_PATHS = courtPaths();
const keyOf = (c: { q: number; r: number }) => `${c.q},${c.r}`;

// What each tone means, in words, with the cut points of lib/euroleague/atlas.ts.
function toneText(tone: Tone, mode: Mode): string {
  const { near, well } = CUTS[mode];
  const f = (v: number) => (mode === "fg" ? `${Math.round(v * 100)} pp` : v.toFixed(2));
  return {
    hi: `${f(well)} or more above`,
    up: `${f(near)} to ${f(well)} above`,
    mid: `within ${f(near)}`,
    down: `${f(near)} to ${f(well)} below`,
    lo: `${f(well)} or more below`,
  }[tone];
}

function Swatch({ tone }: { tone: Tone }) {
  return (
    <svg viewBox="-10 -10 20 20" className="el-swatch" aria-hidden="true">
      <path d={hexPath(0, 0, 9)} className="el-tone" data-tone={tone} />
    </svg>
  );
}

// The atlas (task 116): the league's hexagons by default, a team's when one is chosen (its file is
// fetched then, and only then), one of its players after that, in either season. The hexagons'
// size is their shots, their colour how they go in against the league. Pointer, touch and the
// arrow keys pick a hexagon for the readout. The strip of "what has changed" below follows the
// team chosen here.
export function Atlas({
  league,
  changes,
  runs,
  playerMinShots,
  playersNow,
  teamsWithPlayersNow,
}: {
  league: League;
  changes: TeamChanges[];
  runs: Runs;
  playerMinShots: number;
  playersNow: number;
  teamsWithPlayersNow: number;
}) {
  const [season, setSeason] = useState(league.seasons[0].season);
  const [team, setTeam] = useState("");
  const [player, setPlayer] = useState("");
  const [loaded, setLoaded] = useState<Record<string, Team>>({});
  const [failed, setFailed] = useState("");
  const [active, setActive] = useState<string | null>(null);

  const side = league.hex.side_m * 100;
  const leagueSeason = league.seasons.find((s) => s.season === season)!;
  const teams = [...leagueSeason.teams].sort((a, b) => a.name.localeCompare(b.name));
  const names = Object.fromEntries(league.seasons.flatMap((s) => s.teams.map((t) => [t.code, t.name])));
  const teamSeason = team ? loaded[team]?.seasons.find((s) => s.season === season) : undefined;
  const playerData = player ? teamSeason?.players.find((p) => p.name === player) : undefined;
  const teamName = teams.find((t) => t.code === team)?.name ?? team;

  let drawn: Drawn[];
  let mode: Mode;
  let label: string;
  let shown: number;
  let total: number;
  if (playerData) {
    drawn = playerDrawn(playerData.cells, leagueSeason.cells);
    [mode, label, shown, total] = ["fg", playerData.name, playerData.shots_shown, playerData.shots_total];
  } else if (teamSeason) {
    drawn = teamDrawn(teamSeason.cells, leagueSeason.cells);
    [mode, label, shown, total] = ["fg", teamSeason.name, teamSeason.shots_shown, teamSeason.shots_total];
  } else {
    drawn = leagueDrawn(leagueSeason.cells);
    [mode, label, shown, total] = ["pps", "the league", leagueSeason.shots_shown, leagueSeason.shots_total];
  }
  const average = leagueAverage(leagueSeason.cells);
  const full = fullAt(drawn.map((c) => c.n));
  const ordered = readingOrder(drawn);
  const cell = active ? drawn.find((c) => keyOf(c) === active) : undefined;
  // A new key remounts the hexagons, so each selection enters afresh (CSS, motion allowed only).
  const view = `${season}|${teamSeason ? team : ""}|${playerData ? player : ""}`;
  const loading = team !== "" && !loaded[team] && failed !== team;

  async function chooseTeam(code: string) {
    setTeam(code);
    setPlayer("");
    setActive(null);
    setFailed("");
    if (!code || loaded[code]) return;
    try {
      const res = await fetch(`/data/euroleague/teams/${code}.json`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = (await res.json()) as Team;
      setLoaded((prev) => ({ ...prev, [code]: data }));
    } catch {
      setFailed(code);
    }
  }

  function chooseSeason(next: string) {
    setSeason(next);
    setActive(null);
    const there = league.seasons.find((s) => s.season === next)!;
    if (!there.teams.some((t) => t.code === team)) {
      setTeam("");
      setPlayer("");
      return;
    }
    const players = loaded[team]?.seasons.find((s) => s.season === next)?.players ?? [];
    if (!players.some((p) => p.name === player)) setPlayer("");
  }

  // The pointer, in the court's own units, resolved to the whole cell under it.
  function pick(e: PointerEvent<SVGSVGElement>) {
    const ctm = e.currentTarget.getScreenCTM();
    if (!ctm) return;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    const [q, r] = cellAt(p.x, -p.y, side);
    const hit = drawn.some((c) => c.q === q && c.r === r);
    setActive(hit ? `${q},${r}` : null);
  }

  function step(e: KeyboardEvent<HTMLDivElement>) {
    const at = cell ? ordered.findIndex((c) => keyOf(c) === keyOf(cell)) : -1;
    const last = ordered.length - 1;
    let next: number;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = at >= last ? 0 : at + 1;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = at <= 0 ? last : at - 1;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = last;
    else if (e.key === "Escape") {
      setActive(null);
      return;
    } else return;
    e.preventDefault();
    if (ordered.length > 0) setActive(keyOf(ordered[next]));
  }

  const players = teamSeason?.players ?? [];
  const leagueCellPct = (c: Drawn) => `${((c.league ?? 0) * 100).toFixed(1)}%`;

  return (
    <>
      <Band dark className="el-atlas-band">
        <div className="el-atlas" data-mode={mode} data-view={view}>
          <div className="el-controls">
            <div className="el-seasons" role="group" aria-label="Season">
              {league.seasons.map((s) => (
                <button
                  key={s.season}
                  type="button"
                  aria-pressed={s.season === season}
                  className={s.season === season ? "primary" : undefined}
                  onClick={() => chooseSeason(s.season)}
                >
                  {seasonLabel(s.season)}
                </button>
              ))}
            </div>
            <div className="el-field">
              <label htmlFor="el-team">Team</label>
              <select id="el-team" value={team} onChange={(e) => chooseTeam(e.target.value)}>
                <option value="">The league, all {teams.length} teams</option>
                {teams.map((t) => (
                  <option key={t.code} value={t.code}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="el-field">
              <label htmlFor="el-player">Player, {playerMinShots} shots or more</label>
              <select
                id="el-player"
                value={playerData ? player : ""}
                disabled={!teamSeason || players.length === 0}
                onChange={(e) => {
                  setPlayer(e.target.value);
                  setActive(null);
                }}
              >
                <option value="">
                  {!teamSeason
                    ? "Choose a team first"
                    : players.length === 0
                      ? `None with ${playerMinShots} yet`
                      : `All of ${teamSeason.name}`}
                </option>
                {players.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name} · {p.shots_total.toLocaleString("en-US")}
                  </option>
                ))}
              </select>
            </div>
            <p className="el-status" role="status">
              {loading ? `Loading ${teamName}…` : failed && failed === team ? `${teamName} could not be loaded.` : ""}
            </p>
            {season === CURRENT_SEASON ? (
              <p className="el-note" data-note="in-progress">
                {seasonLabel(season)} is in progress: {pluralize(leagueSeason.games_played, "game")} through{" "}
                {leagueSeason.cutoff}. {pluralize(playersNow, "player has", "players have")} reached{" "}
                {playerMinShots} shots for one team so far
                {teamsWithPlayersNow < leagueSeason.teams.length
                  ? `, so only ${teamsWithPlayersNow} of ${leagueSeason.teams.length} teams have player hexagons yet`
                  : ""}
                .
              </p>
            ) : null}
          </div>

          <figure className="el-court-figure">
            <div
              className="el-court"
              tabIndex={0}
              role="group"
              aria-label={`Shot hexagons of ${label}, ${seasonLabel(season)}: the arrow keys step through them`}
              onKeyDown={step}
              onBlur={() => setActive(null)}
            >
              <svg
                viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.width} ${VIEW.height}`}
                className="el-svg"
                aria-hidden="true"
                onPointerMove={(e) => e.pointerType === "mouse" && pick(e)}
                onPointerDown={pick}
                onPointerLeave={(e) => e.pointerType === "mouse" && setActive(null)}
              >
                <defs>
                  <filter id="el-glow" x="-10%" y="-10%" width="120%" height="120%">
                    <feGaussianBlur stdDeviation="12" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                <g className="el-lines">
                  <path d={COURT_PATHS.outline} />
                  <path d={COURT_PATHS.lines} />
                  <path d={COURT_PATHS.dashed} className="el-lines-dashed" />
                  <circle cx="0" cy={COURT_PATHS.hoop.cy} r={COURT_PATHS.hoop.r} />
                </g>
                <g key={view} className="el-hexes" filter="url(#el-glow)">
                  {drawn.map((c) => {
                    const [x, y] = hexCenter(c.q, c.r, side);
                    return (
                      <path
                        key={keyOf(c)}
                        d={hexPath(x, -y, side * hexScale(c.n, full))}
                        className="el-hex el-tone"
                        data-tone={toneOf(c.diff, mode)}
                        data-q={c.q}
                        data-r={c.r}
                        style={{ "--i": Math.round(Math.hypot(x, y) / 50) } as CSSProperties}
                      />
                    );
                  })}
                </g>
                {cell ? (
                  <path
                    className="el-hex-active"
                    d={(() => {
                      const [x, y] = hexCenter(cell.q, cell.r, side);
                      return hexPath(x, -y, side * Math.max(hexScale(cell.n, full), 0.5));
                    })()}
                  />
                ) : null}
              </svg>
            </div>
            <figcaption className="el-caption" data-caption>
              {shown.toLocaleString("en-US")} of {total.toLocaleString("en-US")} field goals of {label} in{" "}
              {seasonLabel(season)}; a hexagon of fewer than {league.hex.k} shots is not published, so it is not
              drawn.
            </figcaption>
          </figure>

          <div className="el-side">
            <output className="el-readout" aria-live="polite" data-readout={cell ? keyOf(cell) : "none"}>
              {cell ? (
                <>
                  <span className="el-readout-where">{metresFromHoop(cell.q, cell.r, side)} m from the hoop</span>
                  <span className="el-readout-main">
                    <span data-readout-n>{cell.n.toLocaleString("en-US")} shots</span>
                    <span data-readout-pct>{pct(cell.made, cell.n)} made</span>
                  </span>
                  {mode === "fg" ? (
                    <span data-readout-diff>
                      {signedPp(cell.diff)} against the league&apos;s {leagueCellPct(cell)} here
                    </span>
                  ) : (
                    <span data-readout-diff>
                      {perShot(cell.pts, cell.n)} points a shot, {signedPts(cell.diff)} against the league&apos;s{" "}
                      {average.toFixed(2)}
                    </span>
                  )}
                </>
              ) : (
                <span className="el-readout-hint">
                  Point at or tap a hexagon, or focus the court and use the arrow keys.
                </span>
              )}
            </output>
            <div className="el-legend">
              <p>
                <span className="el-legend-label">Size</span> shots in the hexagon: {league.hex.k} at the smallest,
                full from {full.toLocaleString("en-US")}.
              </p>
              <p>
                <span className="el-legend-label">Colour</span>{" "}
                {mode === "pps"
                  ? `points a shot against the league's average, ${average.toFixed(2)}:`
                  : "field-goal % against the league's in the same hexagon (pp, percentage points):"}
              </p>
              <ul className="el-legend-tones">
                {TONES.map((t) => (
                  <li key={t}>
                    <Swatch tone={t} /> {toneText(t, mode)}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </Band>
      <Changes changes={changes} seasons={league.seasons.map((s) => s.season)} selected={team} />
      <Streaks runs={runs} season={season} selected={team} names={names} />
    </>
  );
}
