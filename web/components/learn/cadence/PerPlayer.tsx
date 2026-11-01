"use client";

import { useEffect, useId, useState } from "react";
import type { PlayerRow } from "../../../lib/learn/cadence-data";
import { expose } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, ticks } from "../gravity/Plot";

// Every player's fast-band cadence over the whole match, ± two propagated sds, one row each in
// the file's order (by team and shirt number, never by a metric). The reader picks the match and
// the row; the readout prints that row of `pose.json` under the path that names it.
const C_LO = 2.9;
const C_HI = 4.3;

export interface Columns {
  team_id: number;
  number: number;
  finite_s: number;
  cad_s_p50_hz: number;
  cad_s_sd_hz: number;
}

export function PerPlayer({ rows, columns }: { rows: Readonly<Record<string, readonly PlayerRow[]>>; columns: Columns }) {
  const id = useId();
  const matches = Object.keys(rows);
  const [match, setMatch] = useState(matches[0]);
  const [pick, setPick] = useState(0);
  const list = rows[match];
  const index = Math.min(pick, list.length - 1);
  const at = list[index];

  useEffect(() => {
    expose({ player: { match, index, row: at.row, players: list.length } });
  });

  const path = (col: number) => `pose.json:tables.matches.${match}.${at.row}.${col}`;
  // A rule between the teams, where the file's order moves to the second one.
  const split = list.findIndex((r) => r.team_id !== list[0].team_id);

  return (
    <figure className="learn-fig surface-dark" data-figure="players">
      <Legend
        items={[
          { color: INK.data, label: "a player's cadence, ± two sds", dot: true },
          { color: INK.probe, label: "the player you pick", dot: true },
        ]}
      />
      <Plot
        x={{ min: C_LO, max: C_HI, ticks: ticks(C_LO + 0.1, C_HI, 0.2), format: (v) => v.toFixed(1), label: "median cadence in the fast band (steps/s)" }}
        y={{ min: 0, max: list.length + 1, ticks: [], format: String, label: "players, by team and shirt number" }}
        size="tall"
        label="Each player's fast-band cadence with two propagated standard deviations either side, in the file's order"
      >
        {({ x, y }) => (
          <>
            {split > 0 ? (
              <line x1={x(C_LO)} x2={x(C_HI)} y1={y(list.length - split + 0.5)} y2={y(list.length - split + 0.5)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            ) : null}
            {list.map((r, i) => {
              const ink = i === index ? INK.probe : INK.data;
              const yi = y(list.length - i);
              return (
                <g key={r.row} data-row={r.row}>
                  <line x1={x(r.cadence_hz - 2 * r.sd_hz)} x2={x(r.cadence_hz + 2 * r.sd_hz)} y1={yi} y2={yi} stroke={ink} strokeWidth={3} vectorEffect="non-scaling-stroke" />
                  <Dot x={x(r.cadence_hz)} y={yi} r={i === index ? 6 : 4} color={ink} />
                </g>
              );
            })}
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Match</legend>
          {matches.map((m) => (
            <label key={m}>
              <input type="radio" name={`${id}-match`} value={m} checked={m === match} onChange={() => setMatch(m)} /> {m}
            </label>
          ))}
        </fieldset>
        <label htmlFor={`${id}-row`}>Player</label>
        <input id={`${id}-row`} type="range" min={0} max={list.length - 1} step={1} value={index} onChange={(e) => setPick(Number(e.target.value))} />
      </div>
      <p className="learn-readout" aria-live="polite">
        Team <Fig name={path(columns.team_id)}>{at.team_id}</Fig>, number <Fig name={path(columns.number)}>{at.number}</Fig>:{" "}
        <Fig name={path(columns.finite_s)}>{at.finite_s}</Fig> windows with a cadence, median <Fig name={path(columns.cad_s_p50_hz)}>{at.cadence_hz}</Fig> ±{" "}
        <Fig name={path(columns.cad_s_sd_hz)}>{at.sd_hz}</Fig> steps/s
      </p>
      <figcaption>
        The rows /tracking/pose prints for the fast band, drawn. Each bar is the error the joints&apos; predicted error explains, not the
        spread of the player&apos;s own windows.
      </figcaption>
    </figure>
  );
}
