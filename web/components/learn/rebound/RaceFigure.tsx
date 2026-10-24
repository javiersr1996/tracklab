"use client";

import { useEffect, useId, useState } from "react";
import { surfacePrimitives } from "../../../lib/geometry";
import { expose, shown } from "../../../lib/learn/expose";
import { distance } from "../../../lib/learn/rebound";
import type { ReboundFile } from "../../../lib/learn/rebound-data";
import { raceAt, REACTION_MAX, REACTION_STEP, SPEED_MAX, SPEED_MIN, SPEED_STEP } from "../../../lib/learn/rebound-figures";
import { Marking } from "../coordinates/FrameFigure";
import { Fig } from "../Fig";
import { INK } from "../gravity/Plot";

// The example rebound, frozen at the end of its shot: the ten players on the half court, how far
// the reaction carries each, the spot where the rebound was taken, and every player's time to
// arrive and chance of being first. The reader moves the reaction time and the top speed; nothing
// moves until they do.
const TEAM = { shooting: INK.data, defending: INK.standard } as const;
const ink = (team: string) => (team === "shooting" ? TEAM.shooting : TEAM.defending);
const COURT = { spec: "fiba_28x15", length_m: 28, width_m: 15 };
const MARGIN = 0.6; // m around the half court
const R = 0.32; // m, a player's mark

export function RaceFigure({ file }: { file: ReboundFile }) {
  const id = useId();
  const [reaction, setReaction] = useState(file.reaction_s);
  const [topSpeed, setTopSpeed] = useState(file.top_speed);
  const ex = file.example;
  const race = raceAt(file, reaction, topSpeed);
  const order = ex.players.map((_, i) => i).sort((a, b) => race.times[a] - race.times[b]);

  const figures = {
    reaction: shown(reaction, 2),
    top_speed: shown(topSpeed, 1),
    first: race.first,
    nearest: race.nearest,
    first_jersey: ex.players[race.first].jersey,
    first_time: shown(race.times[race.first], 2),
    first_chance: shown(100 * race.chance[race.first], 0),
    rebounder_chance: shown(100 * race.chance[ex.rebounder], 0),
    players: ex.players.map((p, i) => ({
      dist: shown(distance(p, ex.target), 2),
      time: shown(race.times[i], 2),
      chance: shown(100 * race.chance[i], 0),
    })),
  };

  useEffect(() => {
    expose({ race: figures });
  });

  const side = ex.basket_side;
  const x0 = side < 0 ? -COURT.length_m / 2 - MARGIN : -MARGIN;
  const w = COURT.length_m / 2 + 2 * MARGIN;
  const h = COURT.width_m + 2 * MARGIN;
  const [tx, ty] = ex.target;
  const notes = (i: number) =>
    [i === ex.rebounder && "took the rebound", i === race.nearest && "nearest", i === race.first && "model's first"].filter(Boolean).join(", ");

  return (
    <figure className="learn-fig surface-dark learn-rebound-race" data-figure="race" data-first={race.first}>
      <ul className="learn-legend">
        <li>
          <span className="learn-swatch learn-swatch-dot" style={{ color: TEAM.shooting }} aria-hidden="true" />
          the shooting team
        </li>
        <li>
          <span className="learn-swatch learn-swatch-dot" style={{ color: TEAM.defending }} aria-hidden="true" />
          the defending team
        </li>
        <li>
          <span className="learn-swatch learn-swatch-dot learn-rebound-ring" style={{ color: INK.probe }} aria-hidden="true" />
          took the rebound
        </li>
        <li>
          <span className="learn-swatch learn-swatch-dot learn-rebound-ring learn-rebound-ring-dashed" style={{ color: INK.probe }} aria-hidden="true" />
          the model&apos;s first
        </li>
        <li>
          <span className="learn-rebound-cross" style={{ color: INK.probe }} aria-hidden="true">
            ×
          </span>
          where the rebound was taken
        </li>
      </ul>
      <div className="learn-rebound-layout">
        <div className="learn-rebound-court">
          <svg
            viewBox={`${x0} ${-h / 2} ${w} ${h}`}
            style={{ aspectRatio: `${w} / ${h}` }}
            role="img"
            aria-label="The half court at the end of the shot: ten players, how far the reaction carries each, and the spot where the rebound was taken"
          >
            {surfacePrimitives(COURT).map((p, k) => (
              <Marking key={k} p={p} />
            ))}
            {ex.players.map((p, i) => {
              const cx = p.x + p.vx * reaction;
              const cy = p.y + p.vy * reaction;
              return (
                <g key={i} data-player={i}>
                  <line x1={p.x} y1={-p.y} x2={cx} y2={-cy} stroke={ink(p.team)} strokeWidth={2} vectorEffect="non-scaling-stroke" />
                  <circle cx={cx} cy={-cy} r={R / 2} fill="none" stroke={ink(p.team)} strokeWidth={2} vectorEffect="non-scaling-stroke" />
                  <circle cx={p.x} cy={-p.y} r={R} fill={ink(p.team)} />
                </g>
              );
            })}
            {(() => {
              const reb = ex.players[ex.rebounder];
              const pick = ex.players[race.first];
              return (
                <>
                  <circle cx={reb.x} cy={-reb.y} r={1.7 * R} fill="none" stroke={INK.probe} strokeWidth={2} vectorEffect="non-scaling-stroke" />
                  <circle cx={pick.x} cy={-pick.y} r={2.4 * R} fill="none" stroke={INK.probe} strokeWidth={2} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
                </>
              );
            })()}
            {[-1, 1].map((s) => (
              <line key={s} x1={tx - R} y1={-ty - s * R} x2={tx + R} y2={-ty + s * R} stroke={INK.probe} strokeWidth={2.5} vectorEffect="non-scaling-stroke" />
            ))}
          </svg>
        </div>
        <div className="learn-rebound-side">
          <div className="controls">
            <label htmlFor={`${id}-reaction`}>
              Reaction time: <Fig name="learn.race.reaction">{figures.reaction}</Fig>&nbsp;s
            </label>
            <input
              id={`${id}-reaction`}
              type="range"
              min={0}
              max={REACTION_MAX}
              step={REACTION_STEP}
              value={reaction}
              onChange={(e) => setReaction(Number(e.target.value))}
            />
            <label htmlFor={`${id}-speed`}>
              Top speed: <Fig name="learn.race.top_speed">{figures.top_speed}</Fig>&nbsp;m/s
            </label>
            <input
              id={`${id}-speed`}
              type="range"
              min={SPEED_MIN}
              max={SPEED_MAX}
              step={SPEED_STEP}
              value={topSpeed}
              onChange={(e) => setTopSpeed(Number(e.target.value))}
            />
            <div className="learn-rebound-buttons">
              <button
                type="button"
                onClick={() => {
                  setReaction(file.reaction_s);
                  setTopSpeed(file.top_speed);
                }}
              >
                The sources&apos; values
              </button>
              <button type="button" onClick={() => setReaction(0)}>
                No reaction
              </button>
            </div>
          </div>
          <p className="learn-readout" aria-live="polite">
            First by the model: {ex.players[race.first].team} <Fig name="learn.race.first_jersey">{figures.first_jersey}</Fig>, at{" "}
            <Fig name="learn.race.first_time">{figures.first_time}</Fig>&nbsp;s, with a chance of{" "}
            <Fig name="learn.race.first_chance">{figures.first_chance}</Fig>&nbsp;% of being first. The player who took the
            rebound has <Fig name="learn.race.rebounder_chance">{figures.rebounder_chance}</Fig>&nbsp;%.
          </p>
        </div>
      </div>
      <div className="table-scroll">
        <table className="learn-rebound-table">
          <thead>
            <tr>
              <th scope="col">player</th>
              <th scope="col">distance (m)</th>
              <th scope="col">time (s)</th>
              <th scope="col">chance (%)</th>
            </tr>
          </thead>
          <tbody>
            {order.map((i) => (
              <tr key={i} data-player={i}>
                <th scope="row">
                  <span className="learn-swatch learn-swatch-dot" style={{ color: ink(ex.players[i].team) }} aria-hidden="true" />
                  <Fig name={`rebound.example.players.${i}.jersey`}>{ex.players[i].jersey}</Fig>
                  <span className="learn-rebound-note">{[ex.players[i].team, notes(i)].filter(Boolean).join(", ")}</span>
                </th>
                <td>
                  <Fig name={`learn.race.players.${i}.dist`}>{figures.players[i].dist}</Fig>
                </td>
                <td>
                  <Fig name={`learn.race.players.${i}.time`}>{figures.players[i].time}</Fig>
                </td>
                <td>
                  <Fig name={`learn.race.players.${i}.chance`}>{figures.players[i].chance}</Fig>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        Rebound <Fig name="rebound.example.rebound_id">{ex.rebound_id}</Fig> of match <Fig name="rebound.example.match_id">{ex.match_id}</Fig>,
        frozen at frame <Fig name="rebound.example.end_frame">{ex.end_frame}</Fig>, the end of its shot. Each line runs from where a
        player stands to where the reaction time carries them; the small ring is that point. The table gives each player&apos;s distance to the spot, time to arrive and chance of
        being first, with a spread of{" "}
        <Fig name="rebound.spread_s">{file.spread_s}</Fig>&nbsp;s.
      </figcaption>
    </figure>
  );
}
