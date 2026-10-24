import type { SpeedExample, SpeedFile } from "../../../lib/learn/speed-data";
import { EXAMPLE_WINDOWS, exampleGap, K_MAX } from "../../../lib/learn/speed-figures";
import { Dot, INK, Legend, Plot, ticks } from "../gravity/Plot";

// The median gap between the provider's speed and a moving average of k central differences,
// against k: one line per match at the files' full precision (speed.json), and the example's
// published positions at 1 cm (computed here). Nothing to move: the trace above is the control.
const GAP_HI = 0.05;

export function WindowPlot({ example, file }: { example: SpeedExample; file: SpeedFile }) {
  const exRows = EXAMPLE_WINDOWS.map((k) => ({ k, median: exampleGap(example, "central", k).median }));
  const polyline = (rows: readonly { k: number; median: number }[], x: (v: number) => number, y: (v: number) => number) =>
    rows.map((r) => `${x(r.k).toFixed(1)},${y(Math.min(GAP_HI, r.median)).toFixed(1)}`).join(" ");

  return (
    <figure className="learn-fig surface-dark learn-speed-fig" data-figure="window">
      <Legend
        items={[
          { color: INK.data, label: "each match, at the file's precision" },
          { color: INK.probe, label: "the example, at the published centimetre", dot: true },
        ]}
      />
      <Plot
        x={{ min: 0, max: K_MAX + 1, ticks: EXAMPLE_WINDOWS, format: (v) => String(v), label: "k, central differences averaged" }}
        y={{ min: 0, max: GAP_HI, ticks: ticks(0, GAP_HI, 0.01), format: (v) => v.toFixed(2), label: "median gap to the provider's speed (m/s)" }}
        size="tall"
        label="Median gap between the provider's speed and a moving average of k central differences, against k, for every match and for the example"
      >
        {({ x, y }) => (
          <>
            {file.matches.map((m) => (
              <polyline
                key={m.match_id}
                data-match={m.match_id}
                points={polyline(
                  file.windows.map((k) => ({ k, median: m.by_window[String(k)] })),
                  x,
                  y,
                )}
                fill="none"
                stroke={INK.data}
                strokeWidth={2}
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <polyline points={polyline(exRows, x, y)} fill="none" stroke={INK.probe} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            {exRows.map((r) => (
              <Dot key={r.k} x={x(r.k)} y={y(Math.min(GAP_HI, r.median))} r={5} color={INK.probe} />
            ))}
          </>
        )}
      </Plot>
      <figcaption>
        Averaging more differences first takes noise out and then starts to bend the speed itself. At the files&apos; own
        precision every match bottoms out at the same window; at the published centimetre the example does too, from
        higher up.
      </figcaption>
    </figure>
  );
}
