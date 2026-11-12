"use client";

import { type CSSProperties, useState } from "react";
import { across, type GroupView, type MetricView, type PositionsView, SPOTS } from "../../lib/warehouse/positions";

// The figure of /warehouse/positions (task 184a): a metric switcher, the pitch with each position
// group where it plays (its median in large type, its players as faint dots on one scale for all
// groups, the bar from the first to the third quartile, a tick at the median), the same groups
// ranked on one axis, and the console query that returns the same numbers. The server computed
// every value (lib/warehouse/positions-data.ts); this only draws the metric the reader picks.

// A pool's players as faint dots, its middle half as a bar and its median as a tick, across the
// metric's axis. The dots are spread a little up and down by their rank so stacked values show.
function Strip({ m, g, compact = false }: { m: MetricView; g: GroupView; compact?: boolean }) {
  const at = (v: number) => across(m.domain, v);
  return (
    <div
      className={compact ? "pos-strip pos-strip-compact" : "pos-strip"}
      role="img"
      aria-label={`${g.group}: ${g.n} players, median ${g.text.median}, middle half from ${g.text.q1} to ${g.text.q3} ${m.unit}`}
    >
      {g.values.map((v, i) => (
        <span key={i} className="pos-dot" style={{ left: `${at(v)}%`, "--jitter": ((i * 0.618034) % 1) - 0.5 } as CSSProperties} />
      ))}
      <span className="pos-iqr" style={{ left: `${at(g.q1)}%`, width: `${at(g.q3) - at(g.q1)}%` }} />
      <span className="pos-med" style={{ left: `${at(g.median)}%` }} />
    </div>
  );
}

function Axis({ m }: { m: MetricView }) {
  return (
    <div className="pos-axis" aria-hidden="true">
      {m.ticks.map((t) => (
        <span key={t.value} style={{ left: `${across(m.domain, t.value)}%` }}>
          {t.text}
        </span>
      ))}
    </div>
  );
}

export function Positions({ view, pitch }: { view: PositionsView; pitch: string }) {
  const [k, setK] = useState(0);
  const m = view.metrics[k];
  const ranked = [...m.groups].sort((a, b) => b.median - a.median || a.group.localeCompare(b.group));
  const { length: L, width: W } = view.pitch;
  const box = (w: number, h: number) => `${-w / 2 - 1} ${-h / 2 - 1} ${w + 2} ${h + 2}`;
  return (
    <div className="pos" data-metric={m.id}>
      <div className="pos-switch" role="group" aria-label="Metric">
        {view.metrics.map((x, i) => (
          <button type="button" key={x.id} data-metric-button={x.id} aria-pressed={i === k} onClick={() => setK(i)}>
            {x.label}
          </button>
        ))}
      </div>
      <h2 className="pos-title" aria-live="polite">
        {m.label} <span className="pos-scale">({m.scale})</span>
      </h2>
      <div className="pos-grid">
        <figure className="pos-pitch" aria-labelledby="pos-pitch-caption">
          <div className="pos-field" style={{ "--aspect": `${L + 2} / ${W + 2}`, "--aspect-tall": `${W + 2} / ${L + 2}` } as CSSProperties}>
            <svg className="pos-lines pos-lines-wide" viewBox={box(L, W)} aria-hidden="true" focusable="false">
              <path d={pitch} />
            </svg>
            <svg className="pos-lines pos-lines-tall" viewBox={box(W, L)} aria-hidden="true" focusable="false">
              <g transform="rotate(-90)">
                <path d={pitch} />
              </g>
            </svg>
            <ul className="pos-cards">
              {m.groups.map((g) => {
                const s = SPOTS[g.group];
                // Across the pitch lying down; upright (a phone), the flanks a little further in.
                const spot = { "--x": `${50 + s.x * 45}%`, "--y": `${50 + s.y * 45}%`, "--tx": `${50 + s.y * 38}%`, "--ty": `${50 - s.x * 45}%` };
                return (
                  <li key={g.group} className="pos-card" data-group={g.group} style={spot as CSSProperties}>
                    <span className="pos-card-name">{g.group}</span>
                    <span className="pos-card-value">
                      <output data-median>{g.text.median}</output> <span className="pos-unit">{m.unit}</span>
                    </span>
                    <span className="pos-card-n">
                      n = <span data-n>{g.n}</span>
                    </span>
                    <Strip m={m} g={g} compact />
                  </li>
                );
              })}
            </ul>
          </div>
          <figcaption id="pos-pitch-caption">
            Each group where it plays, own goal to the left (at the foot on a phone), with its median. On a wide screen
            each card also draws the group&apos;s players as faint dots, a bar from the first to the third quartile and a
            tick at the median, on one scale for every group.
          </figcaption>
        </figure>
        <figure className="pos-ranked" aria-labelledby="pos-ranked-caption">
          <figcaption id="pos-ranked-caption">
            The same groups ranked by their median on one axis: every player a faint dot, the middle half a bar, the
            median a white tick.
          </figcaption>
          <ol>
            {ranked.map((g) => (
              <li key={g.group} data-group={g.group}>
                <p className="pos-rank-label">
                  <span className="pos-rank-name">{g.group}</span> n = <span data-n>{g.n}</span>, median{" "}
                  <output data-median>{g.text.median}</output>, middle half <span data-q1>{g.text.q1}</span> to{" "}
                  <span data-q3>{g.text.q3}</span>
                </p>
                <Strip m={m} g={g} />
              </li>
            ))}
          </ol>
          <Axis m={m} />
        </figure>
      </div>
      <div className="pos-query">
        <p>
          The query that returns these numbers: paste it into <a href="/warehouse">the console</a>, which runs it on the
          same Parquet file in your browser.
        </p>
        <pre data-sql={m.id}>
          <code>{m.sql}</code>
        </pre>
      </div>
    </div>
  );
}
