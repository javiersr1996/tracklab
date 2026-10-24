import type { MatchGravity } from "../../../lib/learn/gravity-data";
import { gravityFig } from "../../../lib/learn/gravity-data";
import { Fig } from "../Fig";
import { INK, ticks } from "./Plot";

// The ten basketball matches of P3's gravity check as `quality.json` has them: median g, Q1 to
// Q3 and the flights it was taken over, calibration first, against the line of standard gravity.
// Every figure is a `data-fig` naming its row of the file; nothing is typed here.
const G_LO = 7;
const G_HI = 10;
const STRIP_W = 300;
const STRIP_H = 24;

const sx = (v: number) => ((Math.min(G_HI, Math.max(G_LO, v)) - G_LO) / (G_HI - G_LO)) * STRIP_W;

export function PerMatch({ matches, g }: { matches: readonly MatchGravity[]; g: number }) {
  const rows = [...matches].sort((a, b) =>
    a.is_calibration === b.is_calibration ? a.match_id.localeCompare(b.match_id) : a.is_calibration ? -1 : 1,
  );
  return (
    <figure className="learn-fig surface-dark" data-figure="per-match">
      <div className="table-scroll">
        <table className="per-match">
          <thead>
            <tr>
              <th scope="col">match</th>
              <th scope="col">set</th>
              <th scope="col">flights</th>
              <th scope="col">Q1</th>
              <th scope="col">median g</th>
              <th scope="col">Q3</th>
              <th scope="col" className="per-match-strip" aria-label="Q1 to Q3 and median against standard gravity, m/s²">
                <span className="per-match-axis" aria-hidden="true">
                  {ticks(G_LO, G_HI, 1).map((v) => (
                    <span key={v} style={{ left: `${(sx(v) / STRIP_W) * 100}%` }}>
                      {v}
                    </span>
                  ))}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.match_id} data-match={r.match_id}>
                <td>{r.match_id}</td>
                <td>{r.is_calibration ? "calibration" : "control"}</td>
                <td>
                  <Fig name={gravityFig(r.match_id, "flights")}>{r.flights}</Fig>
                </td>
                <td>
                  <Fig name={gravityFig(r.match_id, "g_q1")}>{r.g_q1}</Fig>
                </td>
                <td>
                  <Fig name={gravityFig(r.match_id, "g_median")}>{r.g_median}</Fig>
                </td>
                <td>
                  <Fig name={gravityFig(r.match_id, "g_q3")}>{r.g_q3}</Fig>
                </td>
                <td className="per-match-strip">
                  <svg viewBox={`0 0 ${STRIP_W} ${STRIP_H}`} preserveAspectRatio="none" aria-hidden="true">
                    <line x1={sx(g)} x2={sx(g)} y1={0} y2={STRIP_H} stroke={INK.standard} strokeWidth={2} vectorEffect="non-scaling-stroke" />
                    <line x1={sx(r.g_q1)} x2={sx(r.g_q3)} y1={STRIP_H / 2} y2={STRIP_H / 2} stroke={INK.data} strokeWidth={8} vectorEffect="non-scaling-stroke" />
                    <line x1={sx(r.g_median)} x2={sx(r.g_median)} y1={2} y2={STRIP_H - 2} stroke={INK.probe} strokeWidth={3} vectorEffect="non-scaling-stroke" />
                  </svg>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="learn-legend">
        <li>
          <span className="learn-swatch" style={{ color: INK.data }} aria-hidden="true" />Q1 to Q3
        </li>
        <li>
          <span className="learn-swatch learn-swatch-tick" style={{ color: INK.probe }} aria-hidden="true" />median
        </li>
        <li>
          <span className="learn-swatch learn-swatch-tick" style={{ color: INK.standard }} aria-hidden="true" />
          standard gravity, <Fig name="hook.g_real">{g}</Fig> m/s²
        </li>
      </ul>
      <figcaption>
        One row per match, as P3 published it. The calibration matches set P3&apos;s thresholds; the control matches were
        scored with them frozen.
      </figcaption>
    </figure>
  );
}
