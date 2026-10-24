"use client";

import { useEffect, useId, useState } from "react";
import { analyticSdG, apparentG, gAtHalfWindow, rmsAt } from "../../../lib/learn/gravity";
import type { GravityHook } from "../../../lib/learn/gravity-data";
import { expose, shown } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { INK, Legend, Plot, ticks } from "./Plot";

// g of the hook flight over the 2H + 1 samples around its highest one, for H from 2 to the whole
// window, each with ±2 sd: the sd independent noise as large as the whole fit's residual RMS
// would give that window (2σ/√Σw²). The reader picks H; P3 fits the whole window.
const H_MIN = 2;
const G_LO = 3;
const G_HI = 11;

export function WindowPlot({ hook }: { hook: GravityHook }) {
  const { t_s: t, z_data_m: z, g_real: G } = hook;
  const id = useId();
  const mid = (t.length - 1) / 2;
  const [h, setH] = useState(mid);

  const sigma = rmsAt(t, z, apparentG(t, z));
  const rows = Array.from({ length: mid - H_MIN + 1 }, (_, k) => {
    const hk = H_MIN + k;
    return { h: hk, g: gAtHalfWindow(t, z, hk), sd: analyticSdG(t.slice(mid - hk, mid + hk + 1), sigma) };
  });
  const pick = rows.find((r) => r.h === h) ?? rows[rows.length - 1];
  const figures = { h: pick.h, samples: 2 * pick.h + 1, g: shown(pick.g, 4), sd2: shown(2 * pick.sd, 2) };

  useEffect(() => {
    expose({ window: figures });
  });

  const clamp = (v: number) => Math.min(G_HI, Math.max(G_LO, v));

  return (
    <figure className="learn-fig surface-dark" data-figure="window">
      <Legend
        items={[
          { color: INK.data, label: "g with ±2 sd", dot: true },
          { color: INK.probe, label: "the window you pick", dot: true },
          { color: INK.standard, label: "standard gravity", dashed: true },
        ]}
      />
      <Plot
        x={{ min: H_MIN - 0.5, max: mid + 0.5, ticks: ticks(H_MIN, mid, 2), format: (v) => String(v), label: "H, samples each side of the highest one" }}
        y={{ min: G_LO, max: G_HI, ticks: ticks(G_LO + 1, G_HI, 2), format: (v) => String(v), label: "g (m/s²)" }}
        height={320}
        label="g of the hook flight against the half-window H, with plus or minus two standard deviations, and the line of standard gravity"
      >
        {({ x, y }) => (
          <>
            <line x1={x(H_MIN - 0.5)} x2={x(mid + 0.5)} y1={y(G)} y2={y(G)} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" />
            {rows.map((r) => {
              const ink = r.h === pick.h ? INK.probe : INK.data;
              return (
                <g key={r.h} data-h={r.h}>
                  <line x1={x(r.h)} x2={x(r.h)} y1={y(clamp(r.g - 2 * r.sd))} y2={y(clamp(r.g + 2 * r.sd))} stroke={ink} strokeWidth={3} />
                  <circle cx={x(r.h)} cy={y(clamp(r.g))} r={r.h === pick.h ? 8 : 6} fill={ink} />
                </g>
              );
            })}
          </>
        )}
      </Plot>
      <div className="controls">
        <label htmlFor={`${id}-h`}>Half-window H</label>
        <input id={`${id}-h`} type="range" min={H_MIN} max={mid} step={1} value={h} onChange={(e) => setH(Number(e.target.value))} />
      </div>
      <p className="learn-readout" aria-live="polite">
        H <Fig name="learn.window.h">{figures.h}</Fig>, <Fig name="learn.window.samples">{figures.samples}</Fig> samples: g{" "}
        <Fig name="learn.window.g">{figures.g}</Fig> ± <Fig name="learn.window.sd2">{figures.sd2}</Fig> m/s²
      </p>
      <figcaption>
        The bars are two standard deviations of g if every sample carried independent noise as large as the whole
        fit&apos;s residual RMS. Short windows swing widely; none of them reaches <Fig name="hook.g_real">{G}</Fig>.
      </figcaption>
    </figure>
  );
}
