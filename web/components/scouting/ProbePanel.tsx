"use client";

import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../../lib/motion";
import { Count } from "../home/Count";

// The head panel of /warehouse/scouting (task 136): one player's percentiles in one table, read
// from `scouting.json` (the default pair's first player and the probe the producer computed in
// plain Python), with no engine. The bars grow from the left and the numbers count up the first
// time the panel comes into view; the server, a page without JS and `prefers-reduced-motion` show
// them at their final width and value, and nothing moves. `data-grow` says where the bars are,
// like the home's `data-count`: still, idle, growing, done.

export interface ProbeView {
  name: string;
  team: string;
  group: string;
  age: number | null;
  ageReference: string;
  table: string;
  pool: { players: number; sample: number; noun: string };
  metrics: { id: string; label: string; pctl: number }[];
}

type Phase = "idle" | "growing" | "done";

export function ProbePanel({ probe }: { probe: ProbeView }) {
  const reduceMotion = usePrefersReducedMotion();
  const el = useRef<HTMLElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");

  useEffect(() => {
    if (reduceMotion || !el.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        setPhase("growing");
      },
      { threshold: 0.4 },
    );
    observer.observe(el.current);
    return () => observer.disconnect();
  }, [reduceMotion]);

  return (
    <figure
      ref={el}
      className="head-panel scout-probe"
      data-head-panel="probe"
      data-grow={reduceMotion ? "still" : phase}
      onAnimationEnd={() => setPhase("done")}
    >
      <figcaption className="head-panel-label">{probe.table} percentiles</figcaption>
      <p className="scout-probe-who">
        <span className="scout-probe-name">{probe.name}</span>
        <span className="scout-probe-meta">
          {probe.team} · {probe.group}
          {probe.age === null ? null : ` · ${probe.age} at ${probe.ageReference}`}
        </span>
      </p>
      <ol className="scout-probe-bars">
        {probe.metrics.map((m) => (
          <li key={m.id} data-metric={m.id} data-pctl={m.pctl}>
            <span className="scout-probe-label">{m.label}</span>
            <span className="scout-track" aria-hidden="true">
              <span className="scout-fill" style={{ width: `${m.pctl}%` }} />
            </span>
            <span className="scout-probe-pct">
              <Count value={m.pctl} kind="pct" />
            </span>
          </li>
        ))}
      </ol>
      <p className="scout-probe-pool" data-probe-pool>
        Pool: {probe.group}, {probe.pool.players} players, {probe.pool.sample.toLocaleString("en-US")}{" "}
        {probe.pool.noun} between them. A high percentile is a high value, not a verdict.
      </p>
    </figure>
  );
}
