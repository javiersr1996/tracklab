import { axisTicks, placedInTime, stepGroups, type PlatformData } from "../../lib/platform";

// Every step of `platform.json` as one bar on a shared seconds axis (task 123), server-rendered SVG,
// no library. Rows are grouped by layer; all bars wear one neon fill and the group is named in a
// header row, so no meaning rides on colour. The axis runs to the run's wall clock. With a v2 record
// a bar ends at the step's last event and is its own duration long (task 132, `stepGroups`); a v1
// record has durations and no times, so every bar starts at 0.
const LABEL_W = 232;
const PLOT_W = 440;
const VALUE_W = 120;
const ROW_H = 22;
const HEAD_H = 26;
const AXIS_H = 28;
const BAR_H = 10;

export function StepGantt({ platform }: { platform: PlatformData }) {
  const wall = platform.run.wall_seconds;
  const groups = stepGroups(platform.steps, undefined, platform.run.started_utc);
  const placed = placedInTime(platform.steps);
  const x = (s: number) => LABEL_W + (s / wall) * PLOT_W;
  const width = LABEL_W + PLOT_W + VALUE_W;

  const heights = groups.map((g) => HEAD_H + g.steps.length * ROW_H);
  const rows = groups.map((g, i) => ({
    g,
    top: AXIS_H + heights.slice(0, i).reduce((sum, h) => sum + h, 0),
  }));
  const height = AXIS_H + heights.reduce((sum, h) => sum + h, 0) + 4;
  // A tick closer than 60 px to the wall-clock line would print on top of its label.
  const ticks = axisTicks(wall).filter((tick) => ((wall - tick) / wall) * PLOT_W >= 60);

  return (
    <>
    <div
      className="gantt-scroll"
      data-gantt
      data-steps={platform.steps.length}
      tabIndex={0}
      role="region"
      aria-label="Step durations chart, scrollable"
    >
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${placed ? "When each" : "Duration of each"} of the ${platform.steps.length} steps ran, in seconds, on an axis up to the run's ${wall} second wall clock`}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="gantt-grid" x1={x(t)} x2={x(t)} y1={AXIS_H - 6} y2={height - 4} />
            <text className="gantt-tick" x={x(t)} y={14} textAnchor="middle">
              {t} s
            </text>
          </g>
        ))}
        <line className="gantt-wall" x1={x(wall)} x2={x(wall)} y1={AXIS_H - 6} y2={height - 4} />
        <text className="gantt-tick" x={x(wall)} y={14} textAnchor="start" dx={4}>
          wall {wall} s
        </text>
        {rows.map(({ g, top }) => (
          <g key={g.group} data-gantt-group={g.group}>
            <text className="gantt-group" x={0} y={top + 17}>
              {g.group} ({g.steps.length}) · {g.seconds.toFixed(1)} s
            </text>
            {g.steps.map((s, i) => {
              const cy = top + HEAD_H + i * ROW_H + ROW_H / 2;
              return (
                <g
                  key={s.step_key}
                  data-gantt-step={s.step_key}
                  data-seconds={s.seconds.toFixed(1)}
                  data-start={s.start.toFixed(1)}
                  data-end={s.end.toFixed(1)}
                >
                  <title>{placed ? `${s.step_key}: ${s.seconds.toFixed(1)} s, ending ${s.end.toFixed(1)} s into the run` : `${s.step_key}: ${s.seconds.toFixed(1)} s`}</title>
                  <text className="gantt-label" x={LABEL_W - 8} y={cy + 4} textAnchor="end">
                    {s.step_key}
                  </text>
                  <rect
                    className="gantt-bar"
                    x={x(s.start)}
                    y={cy - BAR_H / 2}
                    width={Math.max(2, (s.seconds / wall) * PLOT_W)}
                    height={BAR_H}
                    rx={2}
                  />
                  <text
                    className="gantt-value"
                    x={x(s.start) + Math.max(2, (s.seconds / wall) * PLOT_W) + 6}
                    y={cy + 4}
                  >
                    {s.seconds.toFixed(1)} s
                  </text>
                </g>
              );
            })}
          </g>
        ))}
      </svg>
    </div>
    <details className="gantt-table" data-gantt-table>
      <summary>Steps as a table</summary>
      <table>
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col">Layer</th>
            <th scope="col">Seconds</th>
            {placed && <th scope="col">Ends at (s)</th>}
          </tr>
        </thead>
        <tbody>
          {groups.flatMap((g) =>
            g.steps.map((s) => (
              <tr key={s.step_key}>
                <th scope="row">{s.step_key}</th>
                <td>{g.group}</td>
                <td>{s.seconds.toFixed(1)}</td>
                {placed && <td>{s.end.toFixed(1)}</td>}
              </tr>
            )),
          )}
        </tbody>
      </table>
    </details>
    </>
  );
}
