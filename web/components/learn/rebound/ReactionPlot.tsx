import type { ReboundFile } from "../../../lib/learn/rebound-data";
import { INK, Legend, Plot, ticks } from "../gravity/Plot";

// How often the model's first took the rebound, against the reaction time it assumes: one line
// per match, from rebound.json's counts. At no reaction the model is the nearest rule. Nothing to
// move: the race above is the control.
const LO = 10;
const HI = 55;

export function ReactionPlot({ file }: { file: ReboundFile }) {
  const last = file.reactions[file.reactions.length - 1];
  const clamp = (v: number) => Math.min(HI, Math.max(LO, v));
  return (
    <figure className="learn-fig surface-dark learn-rebound-fig" data-figure="reaction">
      <Legend
        items={[
          { color: INK.data, label: "each match" },
          { color: INK.standard, label: "the sources' reaction time", dashed: true },
        ]}
      />
      <Plot
        x={{ min: 0, max: last, ticks: ticks(0, last, 0.5), format: (v) => v.toFixed(1), label: "reaction time the model assumes (s)" }}
        y={{ min: LO, max: HI, ticks: ticks(LO, HI, 10), format: (v) => v.toFixed(0), label: "rebounds where the model's first took it (%)" }}
        size="tall"
        label="For every match, the share of rebounds where the model's first player took the rebound, against the reaction time the model assumes"
      >
        {({ x, y }) => (
          <>
            <line x1={x(file.reaction_s)} x2={x(file.reaction_s)} y1={y(LO)} y2={y(HI)} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
            {file.matches.map((m) => (
              <polyline
                key={m.match_id}
                data-match={m.match_id}
                points={file.reactions.map((r, i) => `${x(r).toFixed(1)},${y(clamp((100 * m.by_reaction[i]) / m.n)).toFixed(1)}`).join(" ")}
                fill="none"
                stroke={INK.data}
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </>
        )}
      </Plot>
      <figcaption>
        The left end of every line is the nearest rule, since with no reaction the model reduces to it. The dashed line is the
        value the lesson uses, taken from the sources before looking at these rebounds.
      </figcaption>
    </figure>
  );
}
