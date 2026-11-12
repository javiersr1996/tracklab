import { cellPaths, COLORS, FLOOR, type OccupancyView, pct, STEPS } from "../../lib/occupancy/data";

// The server half of /tracking/occupancy (task 184b): every group's cells, drawn once as SVG
// definitions the large map and the small ones reference, the legend of the one colour scale they
// share, and the small multiples.

// One <g> per group in grid units, placed on the pitch in metres: col 0 at the own goal line,
// row 0 at the right touchline, which is the bottom of a pitch drawn with y up.
export function OccupancyCells({ view }: { view: OccupancyView }) {
  const { cols, cell_length_m: cl, cell_width_m: cw, length_m: L, width_m: W } = view.grid;
  return (
    <svg className="occ-defs" width="0" height="0" aria-hidden="true" focusable="false">
      <defs>
        {view.groups.map((g) => (
          <g key={g.slug} id={`occ-${g.slug}`} transform={`translate(${-L / 2} ${W / 2}) scale(${cl} ${-cw})`} shapeRendering="crispEdges">
            {cellPaths(g, cols, view.top).map((p) => (
              <path key={p.step} d={p.d} fill={COLORS[p.step - 1]} data-step={p.step} />
            ))}
          </g>
        ))}
      </defs>
    </svg>
  );
}

// The steps of the scale, each with the largest share it holds; under the floor a cell keeps the
// pitch's colour.
export function Legend({ view }: { view: OccupancyView }) {
  return (
    <figure className="occ-legend" aria-labelledby="occ-legend-caption">
      <figcaption id="occ-legend-caption">
        Share of the group&apos;s player-frames in one square, one scale for every map (under{" "}
        <span data-floor>{pct(FLOOR, 2)}</span> a square stays the colour of the pitch)
      </figcaption>
      <ol className="occ-steps">
        {COLORS.map((c, k) => (
          <li key={c}>
            <span className="occ-swatch" style={{ background: c }} aria-hidden="true" />
            up to <span data-edge={k + 1}>{pct(view.edges[k], 3)}</span>
          </li>
        ))}
      </ol>
      <p className="occ-legend-note">
        Darkest to brightest in {STEPS} equal steps up to the brightest square of all, which holds{" "}
        <span data-top>{pct(view.top, 2)}</span> of its group&apos;s player-frames.
      </p>
    </figure>
  );
}

export function SmallMultiples({ view, lines }: { view: OccupancyView; lines: string }) {
  const { length_m: L, width_m: W } = view.grid;
  return (
    <ul className="occ-multiples">
      {view.groups.map((g) => (
        <li key={g.slug} data-group={g.slug}>
          <p className="occ-multiple-name">{g.group}</p>
          <svg
            viewBox={`${-L / 2 - 1} ${-W / 2 - 1} ${L + 2} ${W + 2}`}
            role="img"
            aria-label={`${g.group}: busiest in the ${g.third.name}, ${pct(g.third.share)}, and on the ${g.lane.name}, ${pct(g.lane.share)}`}
          >
            <use href={`#occ-${g.slug}`} />
            <path className="occ-lines" d={lines} />
          </svg>
          <p className="occ-multiple-n">
            <span data-field="player_frames">{g.player_frames.toLocaleString("en-US")}</span> player-frames
          </p>
        </li>
      ))}
    </ul>
  );
}
