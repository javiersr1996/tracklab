import { display } from "../../../lib/learn/display";
import { hypothesesFig, type HypothesesFile, type MatchHypotheses } from "../../../lib/learn/hypotheses-data";
import { Fig } from "../Fig";
import { type Axis, INK, Legend, Plot, signed, ticks } from "./Plot";

// "What the data add" (task 87): gravity.json's two tests, match by match. Above, each match's
// median g at each half-window (calibration solid, control dashed) against standard gravity;
// below, each match's flights split by the frames from the shot's start to the window's first
// frame, with the n and median g of each bin. Every number is a `data-fig` naming its place in the
// file; nothing is typed here and nothing moves.
const G_LO = 7;
const G_HI = 10;

const byCalibration = (a: MatchHypotheses, b: MatchHypotheses) =>
  a.is_calibration === b.is_calibration ? a.match_id.localeCompare(b.match_id) : a.is_calibration ? -1 : 1;

export function HypothesisPlot({ file }: { file: HypothesesFile }) {
  const hs = file.half_windows;
  const rows = [...file.matches].sort(byCalibration);
  const x: Axis = { min: hs[0], max: hs[hs.length - 1], ticks: hs, format: String, label: "half-window H, samples on each side of the highest one" };
  const y: Axis = { min: G_LO, max: G_HI, ticks: ticks(G_LO, G_HI, 1), format: (v) => signed(v, 0), label: "the match's median g, m/s²" };
  const bins = file.start_bins;
  return (
    <figure className="learn-fig surface-dark" data-figure="hypotheses">
      <Plot x={x} y={y} size="tall" label="Each match's median g at each half-window, against standard gravity">
        {(s) => (
          <>
            <line x1={s.x(x.min)} x2={s.x(x.max)} y1={s.y(file.g_real)} y2={s.y(file.g_real)} stroke={INK.standard} strokeWidth={2} vectorEffect="non-scaling-stroke" />
            {rows.map((r) => (
              <polyline
                key={r.match_id}
                points={hs
                  .map((h) => [h, r.g_median_by_half_window[String(h)]] as const)
                  .filter((p): p is readonly [number, number] => p[1] !== null)
                  .map(([h, g]) => `${s.x(h).toFixed(1)},${s.y(g).toFixed(1)}`)
                  .join(" ")}
                fill="none"
                stroke={INK.data}
                strokeWidth={2}
                strokeDasharray={r.is_calibration ? undefined : "6 4"}
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </>
        )}
      </Plot>
      <Legend
        items={[
          { color: INK.data, label: "calibration match" },
          { color: INK.data, label: "control match", dashed: true },
          { color: INK.standard, label: "standard gravity" },
        ]}
      />
      <div className="table-scroll">
        <table className="per-match" data-table="start-bins">
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">set</th>
              <th scope="col">frames from the start, median</th>
              <th scope="col">windows before the start</th>
              {bins.map(([lo, hi], i) => (
                <th scope="col" key={i}>
                  <Fig name={`hypotheses.start_bins.${i}.0`}>{lo!}</Fig>
                  {hi === null ? " frames or more" : <> to <Fig name={`hypotheses.start_bins.${i}.1`}>{hi}</Fig> frames</>}: n, median g
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.match_id} data-match={r.match_id}>
                <td>{display(r.match_id, "match_id")}</td>
                <td>{r.is_calibration ? "calibration" : "control"}</td>
                <td>{r.frames_from_start_median === null ? "none" : <Fig name={hypothesesFig(r.match_id, "frames_from_start_median")}>{r.frames_from_start_median}</Fig>}</td>
                <td>
                  <Fig name={hypothesesFig(r.match_id, "before_start")}>{r.before_start}</Fig>
                </td>
                {r.by_frames_from_start.map((b, i) => (
                  <td key={i}>
                    <Fig name={hypothesesFig(r.match_id, `by_frames_from_start.${i}.n`)}>{b.n}</Fig>,{" "}
                    {b.g_median === null ? "none" : <Fig name={hypothesesFig(r.match_id, `by_frames_from_start.${i}.g_median`)}>{b.g_median}</Fig>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <figcaption>
        Every flight the check keeps, fitted again around the same highest sample: above, the median of each match at each
        half-window; below, the flights split by how many frames after the shot&apos;s start their window begins.
      </figcaption>
    </figure>
  );
}
