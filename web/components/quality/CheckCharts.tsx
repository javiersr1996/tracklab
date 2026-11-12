import type { CSSProperties, ReactNode } from "react";
import { across, cellKey, formatMetric, QUALITY_SPORTS, scaleOf, seriesOf, stacked, type TableMetric, TABLE_METRICS } from "../../lib/quality";

// /engineering/quality (task 183): one chart per column of the table, a dot per match, basketball
// and football on their own rows, the median of each marked and printed, the reference where the
// metric has one. Drawn on the server in HTML, so every label keeps the page's text size at any
// width; the dots are marks, and each row's label and the reading under the chart say what they are.

const SPORT_NAME: Record<string, string> = { basketball: "Basketball", football: "Football" };

// What each chart shows, in the bulletin's words (/engineering/bulletin) or the page's own; where
// neither gives a reading, only what is plotted.
const READING: Record<string, ReactNode> = {
  ball_detected_pct: (
    <>
      The share of frames in which the provider marks the ball as actually seen, against extrapolated (its{" "}
      <code>is_detected</code> flag): a pipeline that filters on it for the ball keeps nothing in basketball, and
      football&apos;s detection is partial and should be read per match, not assumed constant.
    </>
  ),
  player_detected_pct: <>The same flag for the players: in football it is partial and should be read per match, not assumed constant.</>,
  g_median: (
    <>
      The gravity each match&apos;s ball flights imply: in basketball a systematic low bias, not a random error, which any
      quantity derived from raw height in flight inherits; football carries the same measurement with no calibration
      reference to grade it against.
    </>
  ),
  g_median_bias_pct: <>The same medians as a percentage away from standard gravity, negative below it.</>,
  gap_median_deg: (
    <>
      The required minus the reported angle at the rim, median per match. Part of that distance comes from the method
      itself, and would remain even with a perfect flight: the <a href="/learn/entry">entry lesson</a> explains where.
    </>
  ),
  ball_player_d2_ratio: (
    <>
      How much more the ball&apos;s position jitters from frame to frame than a detected player&apos;s: smoothing tuned
      on player tracks under-smooths the basketball ball by about that factor, while football&apos;s ratio is capped by
      how its coordinates are stored, not by the ball&apos;s motion.
    </>
  ),
  clock_step_exact_pct: (
    <>
      The share of frame-to-frame steps at the sport&apos;s declared rate: a real cross-check in basketball, against the
      video&apos;s wall clock, and a count of contiguity in football, where no independent field exists to check against.
    </>
  ),
};

// What a row says when it cannot be read as the others: the basketball ball's flag, and a check
// with no rows for a sport.
function rowNote(m: TableMetric, sport: string, values: readonly number[] | null): string | null {
  if (values === null) {
    return m.check === "entry_angle"
      ? "Does not apply: the check measures shots at a basketball rim, and quality.json has no football row of it."
      : `Does not apply: quality.json has no ${sport} row of this check.`;
  }
  if (m.metric === "ball_detected_pct" && sport === "basketball" && values.every((v) => v === 0)) {
    return `${formatMetric(m, 0)} in all ${values.length} matches: the flag is false for the basketball ball in every frame, though its positions are in the data (the gravity and jitter checks below measure them); a pipeline that filters on the flag keeps none of them.`;
  }
  return null;
}

function Chart({ m }: { m: TableMetric }) {
  const series = seriesOf(m);
  const scale = scaleOf(m, QUALITY_SPORTS.flatMap((s) => series[s]?.points.map((p) => p.value) ?? []));
  const at = (v: number) => `${across(scale.domain, v)}%`;
  const fmt = (v: number) => formatMetric(m, v);
  const id = `chart-${m.metric}`;
  return (
    <figure className="qchart" data-chart={m.metric} aria-labelledby={id}>
      <h3 id={id}>
        {m.label} <span className="qchart-unit">({m.unit})</span>
      </h3>
      {m.reference ? (
        <p className="qchart-ref" data-reference={m.reference.value}>
          <span className="qchart-ref-swatch" aria-hidden="true" /> dashed line: {m.reference.text}
        </p>
      ) : null}
      {QUALITY_SPORTS.map((sport) => {
        const s = series[sport];
        const values = s ? s.points.map((p) => p.value) : null;
        const note = rowNote(m, sport, values);
        const dots = s ? stacked(s.points, scale.domain) : [];
        return (
          <div className="qrow" key={sport} data-sport={sport}>
            <p className="qrow-label">
              <span className="qrow-sport">{SPORT_NAME[sport]}</span>
              {s ? (
                <>
                  {" "}
                  <span data-matches>{s.points.length}</span> matches, median <output data-median>{fmt(s.median)}</output>
                </>
              ) : null}
            </p>
            {s && values ? (
              <div
                className="qstrip"
                role="img"
                aria-label={`${m.label}, ${sport}: ${values.length} matches from ${fmt(Math.min(...values))} to ${fmt(Math.max(...values))}, median ${fmt(s.median)}`}
                style={{ "--levels": Math.max(...dots.map((d) => d.level)) + 1 } as CSSProperties}
              >
                {m.reference ? <span className="qstrip-ref" style={{ left: at(m.reference.value) }} /> : null}
                <span className="qstrip-median" style={{ left: at(s.median) }} />
                {dots.map((d) => (
                  <span
                    key={d.match_id}
                    className="qdot"
                    data-match={d.match_id}
                    data-value={d.value}
                    style={{ left: `${d.x}%`, "--level": d.level } as CSSProperties}
                  />
                ))}
              </div>
            ) : null}
            {note ? (
              <p className="qrow-note" data-note={s ? "flag" : "not-applicable"}>
                {note}
              </p>
            ) : null}
          </div>
        );
      })}
      <div className="qaxis" aria-hidden="true">
        {scale.ticks.map((t) => (
          <span key={t} style={{ left: at(t) }}>
            {t.toFixed(scale.tickDecimals)}
          </span>
        ))}
      </div>
      <figcaption>
        <p className="qchart-reading" data-check={m.check === "entry_angle" ? "entry_angle" : undefined}>
          {READING[m.metric]}
        </p>
      </figcaption>
    </figure>
  );
}

export function CheckCharts() {
  return (
    <div className="qcharts">
      {TABLE_METRICS.map((m) => (
        <Chart key={cellKey(m.check, m.metric)} m={m} />
      ))}
    </div>
  );
}
