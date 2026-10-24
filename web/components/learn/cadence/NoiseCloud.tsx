"use client";

import { useEffect, useId, useState } from "react";
import { cadenceHz, linearSd, mean, monteCarlo, sd } from "../../../lib/learn/cadence";
import { SEED } from "../../../lib/learn/cadence-figures";
import type { HookWindow } from "../../../lib/learn/cadence-data";
import { expose, shown } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { Dot, INK, Legend, Plot, ticks } from "../gravity/Plot";

// Monte Carlo on the hook window: every click adds `PER_CLICK` noisy copies of s(t), each sample
// moved by a normal draw of sd scale × σ_i, and reads each cadence again. The draws come from one
// stream, so the same clicks give the same cloud and a new scale keeps the draws and stretches
// them. Beside the cloud, the first-order interval at the same scale.
const SCALES = [0.25, 0.5, 1, 2];
const PER_CLICK = 20;
const MAX_CLICKS = 10;
const C_LO = 2.8;
const C_HI = 4.4;
const ROWS = 10;

export function NoiseCloud({ hook }: { hook: HookWindow }) {
  const { s_m: s, sigma_m: sigma, fps } = hook;
  const id = useId();
  const [scale, setScale] = useState(1);
  const [clicks, setClicks] = useState(0);

  const c0 = cadenceHz(s, fps);
  const linear = scale * linearSd(s, sigma, fps);
  const draws = monteCarlo(s, sigma, fps, clicks * PER_CLICK, SEED, scale);
  const ok = draws.filter(Number.isFinite);
  const figures =
    ok.length > 1
      ? {
          scale,
          draws: draws.length,
          mean: shown(mean(ok), 4),
          sd: shown(sd(ok), 4),
          linear_sd: shown(linear, 4),
          no_cadence: draws.length - ok.length,
        }
      : null;

  useEffect(() => {
    expose({ noise: { scale, draws: draws.length, cadences: draws, ...figures } });
  });

  const clamp = (v: number) => Math.min(C_HI, Math.max(C_LO, v));

  return (
    <figure className="learn-fig surface-dark" data-figure="noise">
      <Legend
        items={[
          { color: INK.probe, label: "the cadence of a noisy copy", dot: true },
          { color: INK.data, label: "the window's own cadence" },
          { color: INK.standard, label: "± two first-order sds", dashed: true },
        ]}
      />
      <Plot
        x={{ min: C_LO, max: C_HI, ticks: ticks(C_LO, C_HI, 0.4), format: (v) => v.toFixed(1), label: "cadence of the copy (steps/s)" }}
        y={{ min: 0, max: ROWS + 1, ticks: [], format: String, label: "" }}
        size="short"
        label="Cadences of noisy copies of the window, against the window's own cadence and the first-order interval"
      >
        {({ x, y }) => (
          <>
            {[-2, 2].map((m) => (
              <line key={m} x1={x(clamp(c0 + m * linear))} x2={x(clamp(c0 + m * linear))} y1={y(0)} y2={y(ROWS + 1)} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
            ))}
            <line x1={x(c0)} x2={x(c0)} y1={y(0)} y2={y(ROWS + 1)} stroke={INK.data} strokeWidth={3} vectorEffect="non-scaling-stroke" />
            <g data-draws={draws.length}>
              {draws.map((c, j) => (Number.isFinite(c) ? <Dot key={j} x={x(clamp(c))} y={y(1 + (j % ROWS))} r={4} color={INK.probe} /> : null))}
            </g>
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Times the predicted error</legend>
          {SCALES.map((v) => (
            <label key={v}>
              <input type="radio" name={`${id}-scale`} value={v} checked={v === scale} onChange={() => setScale(v)} /> {v}
            </label>
          ))}
        </fieldset>
        <button type="button" className="primary" disabled={clicks >= MAX_CLICKS} onClick={() => setClicks((c) => c + 1)}>
          Add {PER_CLICK} noisy copies
        </button>
        <button type="button" disabled={clicks === 0} onClick={() => setClicks(0)}>
          Clear
        </button>
      </div>
      <p className="learn-readout" aria-live="polite">
        {figures ? (
          <>
            <Fig name="learn.noise.draws">{figures.draws}</Fig> copies at <Fig name="learn.noise.scale">{figures.scale}</Fig> times the
            error: mean <Fig name="learn.noise.mean">{figures.mean}</Fig>, sd <Fig name="learn.noise.sd">{figures.sd}</Fig> steps/s (first order:{" "}
            <Fig name="learn.noise.linear_sd">{figures.linear_sd}</Fig>), <Fig name="learn.noise.no_cadence">{figures.no_cadence}</Fig> with no cadence
          </>
        ) : (
          "No noisy copies yet."
        )}
      </p>
      <figcaption>
        Each dot is the window read again after every sample moved by its own normal error. The pipeline published an sd of{" "}
        <Fig name={`${hook.file}:windows.0.cadence_sd_hz`}>{hook.cadence_sd_hz}</Fig> for this window, from its own draws at the
        predicted error.
      </figcaption>
    </figure>
  );
}
