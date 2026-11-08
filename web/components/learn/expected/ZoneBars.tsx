import { seasonLabel } from "../../../lib/euroleague/atlas";
import { CLASSES, type ExpectedSeason } from "../../../lib/learn/expected-data";
import { attempts } from "../../../lib/learn/expected";
import { INK, Legend, Plot, ticks } from "../gravity/Plot";

// The league's points per attempt in each zone class, one season per plot: a bar per class, as wide
// as its share of the league's attempts and as tall as its points per attempt, so the area of the
// three bars over their width is the league's points per shot, the dashed line. Drawn on the
// server from the file's counts; nothing moves.
const NAME = { rim: "rim", mid: "mid", three: "three" } as const;
const Y_MAX = 1.6;

function Bars({ s }: { s: ExpectedSeason }) {
  const total = attempts(s.league);
  const width = CLASSES.map((c) => s.league[c].n / total);
  const left = width.map((_, i) => width.slice(0, i).reduce((a, w) => a + w, 0));
  const centres = left.map((l, i) => l + width[i] / 2);
  return (
    <Plot
      x={{ min: 0, max: 1, ticks: centres, format: (v) => NAME[CLASSES[centres.indexOf(v)]], label: "share of the league's attempts" }}
      y={{ min: 0, max: Y_MAX, ticks: ticks(0, Y_MAX, 0.4), format: (v) => v.toFixed(1), label: `${seasonLabel(s.season)}: points per attempt` }}
      size="short"
      label={`${seasonLabel(s.season)}: points per attempt in each zone class, each bar as wide as the class's share of the attempts, and the league's points per shot`}
    >
      {({ x, y }) => (
        <>
          {CLASSES.map((c, i) => {
            const e = s.league[c].pts / s.league[c].n;
            const x0 = x(left[i]);
            const x1 = x(left[i] + width[i]);
            return (
              <rect
                key={c}
                data-class={c}
                x={x0.toFixed(1)}
                y={y(e).toFixed(1)}
                width={(x1 - x0 - 2).toFixed(1)}
                height={(y(0) - y(e)).toFixed(1)}
                fill={INK.data}
                fillOpacity={0.22}
                stroke={INK.data}
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
          <line x1={x(0)} x2={x(1)} y1={y(s.mean)} y2={y(s.mean)} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 5" vectorEffect="non-scaling-stroke" />
        </>
      )}
    </Plot>
  );
}

export function ZoneBars({ seasons }: { seasons: readonly ExpectedSeason[] }) {
  return (
    <figure className="learn-fig surface-dark" data-figure="zones">
      <Legend
        items={[
          { color: INK.data, label: "a zone class: width, its share of the attempts; height, its points per attempt" },
          { color: INK.standard, label: "the league's points per shot", dashed: true },
        ]}
      />
      {seasons.map((s) => (
        <Bars key={s.season} s={s} />
      ))}
      <figcaption>
        Field goals only. The dashed line is the mean of the bars&apos; heights weighted by their widths: the parts of the bars
        that rise above it add up to the same area as the gaps between it and the bars that stop below it.
      </figcaption>
    </figure>
  );
}
