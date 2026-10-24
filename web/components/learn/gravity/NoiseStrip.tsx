"use client";

import { useEffect, useId, useState } from "react";
import { analyticSdG, apparentG, withNoise } from "../../../lib/learn/gravity";
import type { GravityHook } from "../../../lib/learn/gravity-data";
import { expose, shown } from "../../../lib/learn/expose";
import { Fig } from "../Fig";
import { INK, Legend, Plot, ticks } from "./Plot";

// Noise on the hook flight redrawn at standard gravity (`z_real_m`), refitted: every click adds
// `PER_CLICK` synthetic flights, seeds 1, 2, 3, ... so the same clicks give the same cloud. A
// change of sd keeps the seeds, so the cloud scales about its centre. The hook's own g sits beside.
const SIGMAS_CM = [1, 3, 10];
const PER_CLICK = 20;
const MAX_CLICKS = 10;
const G_LO = 6.5;
const G_HI = 13;
const ROWS = 10;

const mean = (xs: readonly number[]) => xs.reduce((s, x) => s + x, 0) / xs.length;
const sd = (xs: readonly number[]) => {
  const m = mean(xs);
  return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / (xs.length - 1));
};

export function NoiseStrip({ hook }: { hook: GravityHook }) {
  const { t_s: t, z_data_m: z, z_real_m: zReal, g_real: G } = hook;
  const id = useId();
  const [sigmaCm, setSigmaCm] = useState(SIGMAS_CM[0]);
  const [clicks, setClicks] = useState(0);

  const sigma = sigmaCm / 100;
  const gs = Array.from({ length: clicks * PER_CLICK }, (_, k) => apparentG(t, withNoise(zReal, sigma, k + 1)));
  const hookG = apparentG(t, z);
  const figures =
    gs.length > 1
      ? {
          sigma_cm: sigmaCm,
          flights: gs.length,
          mean: shown(mean(gs), 3),
          sd: shown(sd(gs), 3),
          sd_formula: shown(analyticSdG(t, sigma), 3),
          lowest: shown(Math.min(...gs), 3),
        }
      : null;

  useEffect(() => {
    expose({ noise: { sigma_cm: sigmaCm, flights: gs.length, gs, ...figures } });
  });

  const clamp = (v: number) => Math.min(G_HI, Math.max(G_LO, v));

  return (
    <figure className="learn-fig surface-dark" data-figure="noise">
      <Legend
        items={[
          { color: INK.probe, label: "a noisy flight at standard gravity, refitted", dot: true },
          { color: INK.standard, label: "standard gravity", dashed: true },
          { color: INK.data, label: "the hook flight's g" },
        ]}
      />
      <Plot
        x={{ min: G_LO, max: G_HI, ticks: ticks(G_LO, G_HI, 1), format: (v) => String(v), label: "g of the refitted flight (m/s²)" }}
        y={{ min: 0, max: ROWS + 1, ticks: [], format: String, label: "" }}
        height={200}
        label="g of synthetic noisy flights at standard gravity, against standard gravity and the hook flight's g"
      >
        {({ x, y }) => (
          <>
            <line x1={x(G)} x2={x(G)} y1={y(0)} y2={y(ROWS + 1)} stroke={INK.standard} strokeWidth={2} strokeDasharray="8 6" />
            <line x1={x(hookG)} x2={x(hookG)} y1={y(0)} y2={y(ROWS + 1)} stroke={INK.data} strokeWidth={3} />
            {gs.map((gk, k) => (
              <circle key={k} cx={x(clamp(gk))} cy={y(1 + (k % ROWS))} r={4} fill={INK.probe} />
            ))}
          </>
        )}
      </Plot>
      <div className="controls">
        <fieldset className="learn-choice">
          <legend>Noise sd</legend>
          {SIGMAS_CM.map((s) => (
            <label key={s}>
              <input type="radio" name={`${id}-sigma`} value={s} checked={s === sigmaCm} onChange={() => setSigmaCm(s)} /> {s} cm
            </label>
          ))}
        </fieldset>
        <button type="button" className="primary" disabled={clicks >= MAX_CLICKS} onClick={() => setClicks((c) => c + 1)}>
          Add {PER_CLICK} noisy flights
        </button>
        <button type="button" disabled={clicks === 0} onClick={() => setClicks(0)}>
          Clear
        </button>
      </div>
      <p className="learn-readout" aria-live="polite">
        {figures ? (
          <>
            <Fig name="learn.noise.flights">{figures.flights}</Fig> flights at <Fig name="learn.noise.sigma_cm">{figures.sigma_cm}</Fig> cm:
            mean g <Fig name="learn.noise.mean">{figures.mean}</Fig>, sd <Fig name="learn.noise.sd">{figures.sd}</Fig> (the formula
            gives <Fig name="learn.noise.sd_formula">{figures.sd_formula}</Fig>), lowest <Fig name="learn.noise.lowest">{figures.lowest}</Fig>{" "}
            m/s²
          </>
        ) : (
          "No noisy flights yet."
        )}
      </p>
      <figcaption>
        Each dot is the flight drawn at <Fig name="hook.g_real">{G}</Fig>, noise added to every height, fitted again.
        The cloud widens with the noise and stays where it started.
      </figcaption>
    </figure>
  );
}
