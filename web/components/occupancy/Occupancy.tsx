"use client";

import { type CSSProperties, useState } from "react";

// The figure of /tracking/occupancy (task 184b): a group switcher and the selected group's heat map
// on a large pitch, own goal on the left and the attack to the right (upright on a phone, attack
// up). The cells are drawn once per group by the page (`OccupancyCells`) and only referenced here,
// so a switch moves a reference, not six hundred cells.

export interface PickGroup {
  group: string;
  slug: string;
  player_frames: string;
  player_matches: string;
  matches: string;
  label: string;
}

export function Occupancy({ groups, lines, length, width }: { groups: PickGroup[]; lines: string; length: number; width: number }) {
  const [k, setK] = useState(0);
  const g = groups[k];
  const wide = `${-length / 2 - 1} ${-width / 2 - 1} ${length + 2} ${width + 2}`;
  const tall = `${-width / 2 - 1} ${-length / 2 - 1} ${width + 2} ${length + 2}`;
  const aspect = { "--aspect": `${length + 2} / ${width + 2}`, "--aspect-tall": `${width + 2} / ${length + 2}` } as CSSProperties;
  return (
    <div className="occ" data-group={g.slug}>
      <div className="occ-switch" role="group" aria-label="Position group">
        {groups.map((x, i) => (
          <button type="button" key={x.slug} data-group-button={x.slug} aria-pressed={i === k} onClick={() => setK(i)}>
            {x.group}
          </button>
        ))}
      </div>
      <h2 className="occ-title" aria-live="polite">
        {g.group}{" "}
        <span className="occ-n">
          <span data-field="player_frames">{g.player_frames}</span> player-frames, <span data-field="player_matches">{g.player_matches}</span>{" "}
          player-matches in <span data-field="matches">{g.matches}</span> matches
        </span>
      </h2>
      <figure className="occ-figure" aria-labelledby="occ-caption">
        <p className="occ-direction">
          <span>attacking this way</span>
          <svg className="occ-arrow occ-arrow-across" viewBox="0 0 40 12" aria-hidden="true" focusable="false">
            <path d="M1 6h34M28 1l8 5-8 5" />
          </svg>
          <svg className="occ-arrow occ-arrow-up" viewBox="0 0 12 24" aria-hidden="true" focusable="false">
            <path d="M6 23V2M1 8l5-6 5 6" />
          </svg>
        </p>
        <div className="occ-field" style={aspect}>
          <svg className="occ-map occ-wide" viewBox={wide} role="img" aria-label={g.label} key={`w-${g.slug}`}>
            <use href={`#occ-${g.slug}`} />
            <path className="occ-lines" d={lines} />
          </svg>
          <svg className="occ-map occ-tall" viewBox={tall} role="img" aria-label={g.label} key={`t-${g.slug}`}>
            <g transform="rotate(-90)">
              <use href={`#occ-${g.slug}`} />
              <path className="occ-lines" d={lines} />
            </g>
          </svg>
        </div>
        <figcaption id="occ-caption">
          Where the {g.group.toLowerCase()} group&apos;s players were, every team turned to attack to the right (up, on a
          phone). The brighter a square, the larger its share of the group&apos;s player-frames.
        </figcaption>
      </figure>
    </div>
  );
}
