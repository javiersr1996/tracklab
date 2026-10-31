"use client";

import { useEffect, useMemo, useState } from "react";
import { type Overlay, Replay } from "../replay/Replay";
import type { Possession } from "../../lib/replay/types";
import { at, type Clip, type Runs } from "../../lib/runs/types";

// The hook (decision 7): the run and its placebo, the same runner in the same match, each
// played by the replay component of P1 with the displacement of the defence painted on
// top. One arrow per opponent, from where he stood at the instant (t_c, or t' in the
// placebo), along the run's direction, as long as `displacement_m` in `runs.json` times
// ARROW_GAIN; a dashed arrow points against the run. It appears when the clip reaches the
// instant. Nothing here is measured: every length is a number the publisher wrote.
const ARROW_GAIN = 4;
// The marker's arrow white (--canvas-hi, 20.1:1 on the canvas), the others' the ink (--neon-ink,
// 16.3:1): apart from the marker's by width, head and ring, and from the markings (2.1:1).
export const MARKER_COLOR = "#ffffff";
export const OTHER_COLOR = "#e2e8f0";

function arrowOverlay(clip: Clip, possession: Possession, direction: [number, number]): Overlay {
  const index = new Map(possession.entities.map((e) => [e.entity_id, e.i]));
  const instant = possession.frames[clip.instant_index];
  const anchors = new Map(instant.o.map(([i, x, y]) => [i, [x, y] as const]));
  // The direction is in the attack frame of the leg's period: venue = attack_sign * it.
  const [dx, dy] = direction.map((c) => c * possession.attack_sign);
  return (ctx, view, snapshot) => {
    if (snapshot.t < instant.t) return 0;
    let drawn = 0;
    for (const d of clip.defence) {
      const i = index.get(d.entity_id);
      const anchor = i === undefined ? undefined : anchors.get(i);
      if (!anchor) continue;
      const [x, y] = anchor;
      const [x0, y0] = view.project(x, y);
      const length = d.displacement_m * ARROW_GAIN;
      const [x1, y1] = view.project(x + dx * length, y + dy * length);
      ctx.save();
      ctx.strokeStyle = d.is_marker ? MARKER_COLOR : OTHER_COLOR;
      ctx.fillStyle = ctx.strokeStyle;
      ctx.lineWidth = d.is_marker ? 4 : 2;
      ctx.setLineDash(d.displacement_m < 0 ? [6, 4] : []);
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(x1, y1, d.is_marker ? 5 : 3, 0, 2 * Math.PI);
      ctx.fill();
      if (d.is_marker) {
        ctx.beginPath();
        ctx.arc(x0, y0, 14, 0, 2 * Math.PI);
        ctx.stroke();
      }
      ctx.restore();
      drawn++;
    }
    return drawn;
  };
}

function Leg({ runs, k, possession }: { runs: Runs; k: number; possession: Possession }) {
  const clip = runs.hook.clips[k];
  const base = `hook.clips.${k}`;
  const overlay = useMemo(
    () => arrowOverlay(clip, possession, runs.hook.pair.direction),
    [clip, possession, runs.hook.pair.direction],
  );
  return (
    <section className="runs-leg" data-leg={clip.role}>
      <h3>{clip.role === "run" ? "The run" : "Its placebo"}</h3>
      <Replay key={possession.possession_id} possession={possession} autoplay overlay={overlay} name={clip.role} />
      <p>
        Marker <code>{clip.marker_entity_id}</code>:{" "}
        <span data-fig={`${base}.marker_displacement_m`}>
          {String(at(runs, `${base}.marker_displacement_m`))}
        </span>{" "}
        m along the run&apos;s direction.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">opponent</th>
              <th scope="col">role</th>
              <th scope="col">displacement (m)</th>
            </tr>
          </thead>
          <tbody>
            {clip.defence.map((d, j) => (
              <tr key={d.entity_id} data-opponent={d.entity_id}>
                <td>{d.entity_id}</td>
                <td>{d.is_marker ? "marker" : d.is_goalkeeper ? "goalkeeper" : ""}</td>
                <td data-fig={`${base}.defence.${j}.displacement_m`}>
                  {String(at(runs, `${base}.defence.${j}.displacement_m`))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RunsHook({ runs }: { runs: Runs }) {
  const [clips, setClips] = useState<Possession[] | "failed" | null>(null);
  const { hook } = runs;

  useEffect(() => {
    let live = true;
    Promise.all(
      hook.clips.map((c) => fetch(`/data/${c.file}`).then((r) => r.json() as Promise<Possession>)),
    )
      .then((p) => live && setClips(p))
      .catch(() => live && setClips("failed"));
    return () => {
      live = false;
    };
  }, [hook.clips]);

  return (
    <section className="runs-hook" data-section="hook">
      <h2>One run and its placebo</h2>
      <p>
        Match <span data-fig="hook.pair.match_id">{String(hook.pair.match_id)}</span>, run{" "}
        <code data-fig="hook.pair.run_id">{hook.pair.run_id}</code> by{" "}
        <code data-fig="hook.pair.runner_entity_id">{hook.pair.runner_entity_id}</code>, subtype{" "}
        <code data-fig="hook.subtype">{hook.subtype}</code>, and the placebo the protocol paired
        with it: the same runner at another instant. Chosen by rule, not for the size of its
        effect: <span data-fig="hook.pair.marker_effect_m">{String(hook.pair.marker_effect_m)}</span>{" "}
        m on the marker, the pair closest to the median of the subtype&apos;s{" "}
        <span data-fig="hook.subtype_pairs">{String(hook.subtype_pairs)}</span> calibration pairs (
        <span data-fig="hook.subtype_median_marker_m">{String(hook.subtype_median_marker_m)}</span>{" "}
        m). Arrows: each opponent&apos;s displacement along the run&apos;s direction (
        <span data-fig="hook.pair.direction.0">{String(hook.pair.direction[0])}</span>,{" "}
        <span data-fig="hook.pair.direction.1">{String(hook.pair.direction[1])}</span> in the attack
        frame) over the next{" "}
        <span data-fig="design_checks.cadence.windows.effect_s">
          {String(runs.design_checks.cadence.windows.effect_s)}
        </span>{" "}
        s, drawn {ARROW_GAIN} times longer than they are; dashed points against the run; the
        marker is ringed.
      </p>
      <p>
        Rule: <span data-fig="hook.rule">{hook.rule}</span>
      </p>
      {clips === null ? (
        <div className="replay-placeholder" />
      ) : clips === "failed" ? (
        <p role="alert">The clips could not be loaded.</p>
      ) : (
        <div className="runs-legs">
          {clips.map((possession, k) => (
            <Leg key={hook.clips[k].role} runs={runs} k={k} possession={possession} />
          ))}
        </div>
      )}
    </section>
  );
}
