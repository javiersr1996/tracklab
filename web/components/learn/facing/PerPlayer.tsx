"use client";

import { useEffect, useId, useState } from "react";
import { display } from "../../../lib/learn/display";
import { expose } from "../../../lib/learn/expose";
import { SIDE_DEG } from "../../../lib/learn/facing";
import type { PlayerRow } from "../../../lib/learn/facing-figures";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, ticks } from "../gravity/Plot";

// Every qualifying player of each clip: the median of |relative| as a dot, one row per player in
// the file's order (by team and shirt number, never by a metric), then the same players in a
// table. The reader picks the clip and the row; the readout prints that row under the names the
// table prints it by.
const STEP = 15;

const row = (match: string, i: number, key: keyof PlayerRow) => `learn.players.${match}.${i}.${key}`;

export function PerPlayer({ rows, hooks }: { rows: Readonly<Record<string, readonly PlayerRow[]>>; hooks: Readonly<Record<string, number>> }) {
  const id = useId();
  const matches = Object.keys(rows);
  const [match, setMatch] = useState(matches[0]);
  const [pick, setPick] = useState(0);
  const list = rows[match];
  const index = Math.min(pick, list.length - 1);
  const at = list[index];

  useEffect(() => {
    expose({ player: { match, index, players: list.length } });
  });

  const xMax = Math.max(90, Math.ceil(Math.max(...matches.flatMap((m) => rows[m].map((r) => r.median_abs))) / STEP) * STEP);
  const split = list.findIndex((r) => r.team_id !== list[0].team_id);
  const cell = (key: keyof PlayerRow) => <Fig name={row(match, index, key)}>{at[key]}</Fig>;

  return (
    <figure className="learn-fig surface-dark" data-figure="players">
      <Legend
        items={[
          { color: INK.data, label: "a player's median relative angle, as a size", dot: true },
          { color: INK.probe, label: "the player you pick", dot: true },
          { color: INK.standard, label: "side on from here", dashed: true },
        ]}
      />
      <Plot
        x={{ min: 0, max: xMax, ticks: ticks(0, xMax, STEP), format: (v) => v.toFixed(0), label: "median of |facing − heading| over the player's frames (degrees)" }}
        y={{ min: 0, max: list.length + 1, ticks: [], format: String, label: "players, by team and shirt number" }}
        size="tall"
        label="Each qualifying player's median relative angle, in the file's order, with the side-on line marked"
      >
        {({ x, y }) => (
          <>
            <line x1={x(SIDE_DEG)} x2={x(SIDE_DEG)} y1={y(0)} y2={y(list.length + 1)} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
            {split > 0 ? (
              <line x1={x(0)} x2={x(xMax)} y1={y(list.length - split + 0.5)} y2={y(list.length - split + 0.5)} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            ) : null}
            {list.map((r, i) => (
              <g key={r.index} data-row={i} data-hook={r.index === hooks[match] ? "" : undefined}>
                <line x1={x(0)} x2={x(r.median_abs)} y1={y(list.length - i)} y2={y(list.length - i)} stroke={i === index ? INK.probe : INK.data} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                <Dot x={x(r.median_abs)} y={y(list.length - i)} r={i === index ? 6 : 4} color={i === index ? INK.probe : INK.data} />
              </g>
            ))}
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Match</legend>
          {matches.map((m) => (
            <label key={m}>
              <input type="radio" name={`${id}-match`} value={m} checked={m === match} onChange={() => setMatch(m)} /> {display(m, "match_id")}
            </label>
          ))}
        </fieldset>
        <label htmlFor={`${id}-row`}>Player</label>
        <input id={`${id}-row`} type="range" min={0} max={list.length - 1} step={1} value={index} onChange={(e) => setPick(Number(e.target.value))} />
      </div>
      <p className="learn-readout" aria-live="polite">
        Team {cell("team_id")}, number {cell("number")}: {cell("frames")} frames, median relative angle {cell("median_abs")}°, circular mean{" "}
        {cell("circ_mean")}°, circular variance {cell("circ_var")}, side on or further in {cell("off_pct")}&nbsp;% of frames
      </p>
      {matches.map((m) => (
        <div className="table-scroll" key={m}>
          <table className="learn-matches learn-facing-table" data-match={m}>
            <caption>Match {display(m, "match_id")}</caption>
            <thead>
              <tr>
                <th scope="col">team</th>
                <th scope="col">number</th>
                <th scope="col">frames</th>
                <th scope="col">median |relative| (°)</th>
                <th scope="col">circular mean (°)</th>
                <th scope="col">circular variance</th>
                <th scope="col">side on or further (%)</th>
              </tr>
            </thead>
            <tbody>
              {rows[m].map((r, i) => (
                <tr key={r.index} data-row={i}>
                  <td>
                    <Fig name={row(m, i, "team_id")}>{r.team_id}</Fig>
                  </td>
                  <td>
                    <Fig name={row(m, i, "number")}>{r.number}</Fig>
                  </td>
                  <td>
                    <Fig name={row(m, i, "frames")}>{r.frames}</Fig>
                  </td>
                  <td>
                    <Fig name={row(m, i, "median_abs")}>{r.median_abs}</Fig>
                  </td>
                  <td>
                    <Fig name={row(m, i, "circ_mean")}>{r.circ_mean}</Fig>
                  </td>
                  <td>
                    <Fig name={row(m, i, "circ_var")}>{r.circ_var}</Fig>
                  </td>
                  <td>
                    <Fig name={row(m, i, "off_pct")}>{r.off_pct}</Fig>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <figcaption>
        A player is in the tables with at least the lesson&apos;s floor of frames: in the clip at the frame before and after, with the nose and both
        shoulders, moving faster than the lesson&apos;s floor of speed. The angles are the clip&apos;s joints, in whole centimetres, and its positions.
      </figcaption>
    </figure>
  );
}
