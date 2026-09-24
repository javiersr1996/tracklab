"use client";

import { useEffect, useRef, useState } from "react";
import type { Hook } from "../../lib/quality";

// Side view of one real basketball shot: height (z) against time, the ball
// falling at the g its own data implies next to the same flight at standard
// gravity, from the same position and velocity the data's own fit has at
// t=0. Starts on its own and loops at the flight's own duration (task 30's
// gancho).
const WIDTH = 640;
const HEIGHT = 320;
const PAD = 36;
const DATA_COLOR = "#e0883a";
const REAL_COLOR = "#4ea1f2";

function interpolate(t: number[], series: number[], at: number): number {
  if (at <= t[0]) return series[0];
  for (let i = 1; i < t.length; i++) {
    if (t[i] >= at) {
      const span = t[i] - t[i - 1];
      const w = span > 0 ? (at - t[i - 1]) / span : 0;
      return series[i - 1] * (1 - w) + series[i] * w;
    }
  }
  return series[series.length - 1];
}

export function HookAnimation({ hook }: { hook: Hook }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<"idle" | "playing">("idle");

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const { t_s: t, z_data_m: zData, z_real_m: zReal } = hook;
    const t0 = t[0];
    const t1 = t[t.length - 1];
    const durationMs = (t1 - t0) * 1000;
    const zMin = Math.min(...zData, ...zReal);
    const zMax = Math.max(...zData, ...zReal);
    const px = (ti: number) => PAD + ((ti - t0) / (t1 - t0)) * (WIDTH - 2 * PAD);
    const py = (zi: number) => HEIGHT - PAD - ((zi - zMin) / (zMax - zMin)) * (HEIGHT - 2 * PAD);

    const drawPath = (series: number[], color: string) => {
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.4;
      ctx.lineWidth = 2;
      ctx.beginPath();
      t.forEach((ti, i) => {
        const x = px(ti);
        const y = py(series[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.globalAlpha = 1;
    };

    const drawBall = (series: number[], color: string, at: number) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(px(at), py(interpolate(t, series, at)), 7, 0, Math.PI * 2);
      ctx.fill();
    };

    let raf = 0;
    const start = performance.now();
    const frame = (now: number) => {
      const at = t0 + ((now - start) % durationMs) / 1000;

      ctx.clearRect(0, 0, WIDTH, HEIGHT);
      ctx.strokeStyle = "#3a4149";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(PAD, py(zMin));
      ctx.lineTo(WIDTH - PAD, py(zMin));
      ctx.stroke();

      drawPath(zData, DATA_COLOR);
      drawPath(zReal, REAL_COLOR);
      drawBall(zData, DATA_COLOR, at);
      drawBall(zReal, REAL_COLOR, at);

      setState("playing");
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [hook]);

  return (
    <figure className="hook" data-state={state}>
      <canvas
        ref={canvasRef}
        width={WIDTH}
        height={HEIGHT}
        aria-label="One basketball shot falling at the data's gravity next to standard gravity"
      />
      <figcaption>
        <span style={{ color: DATA_COLOR }}>&#9679; the data ({hook.g_data} m/s&sup2;)</span>{" "}
        <span style={{ color: REAL_COLOR }}>&#9679; standard gravity ({hook.g_real} m/s&sup2;)</span>
      </figcaption>
    </figure>
  );
}
