import {
  ageUnit,
  runLabel,
  testTotal,
  type FreshnessRow,
  type HistoryEntry,
  type Series,
  type StepSeries,
} from "../../lib/history";

// The three charts of /engineering/history (task 132), server-rendered SVG like `StepGantt`: no
// chart library and no script in the browser. Each sits in its own scrolling box and has the same
// figures as a table under it.

const fmt = (v: number | null) => (v === null ? "" : v.toFixed(1));

// --- step time per run: one strip per step, a log seconds axis -------------------------------------

const S_LABEL_W = 232;
const S_PLOT_W = 400;
const S_COL_W = 92;
const S_VERDICT_W = 84;
const S_ROW_H = 24;
const S_HEAD_H = 24;
const S_AXIS_H = 30;

function decades(steps: StepSeries[]): { lo: number; hi: number } {
  const all = steps.flatMap((s) => s.points.map((p) => p.seconds));
  return {
    lo: Math.floor(Math.log10(Math.max(Math.min(...all), 0.01))),
    hi: Math.ceil(Math.log10(Math.max(...all))),
  };
}

export function StepStrips({ series, id }: { series: Series; id: string }) {
  const { lo, hi } = decades(series.steps);
  const hiE = hi === lo ? hi + 1 : hi;
  const x = (s: number) => S_LABEL_W + ((Math.log10(Math.max(s, 10 ** lo)) - lo) / (hiE - lo)) * S_PLOT_W;
  const cols = S_LABEL_W + S_PLOT_W + 16;
  const width = cols + 3 * S_COL_W + S_VERDICT_W;
  const groups = [...new Set(series.steps.map((s) => s.group))].map((g) => ({
    group: g,
    steps: series.steps.filter((s) => s.group === g),
  }));
  const heights = groups.map((g) => S_HEAD_H + g.steps.length * S_ROW_H);
  const height = S_AXIS_H + heights.reduce((a, b) => a + b, 0) + 4;
  const ticks = Array.from({ length: hiE - lo + 1 }, (_, i) => 10 ** (lo + i));
  const tops = heights.map((_, i) => S_AXIS_H + heights.slice(0, i).reduce((a, b) => a + b, 0));

  return (
    <div
      className="gantt-scroll history-scroll"
      data-strips={id}
      tabIndex={0}
      role="region"
      aria-label={`Seconds of each step in the ${series.runs.length} runs of this selection, scrollable`}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Seconds of each of ${series.steps.length} steps in each of ${series.runs.length} runs, on a logarithmic axis, with the median and threshold of the earlier runs of the same mode`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="gantt-grid" x1={x(t)} x2={x(t)} y1={S_AXIS_H - 6} y2={height - 4} />
            <text className="gantt-tick" x={x(t)} y={14} textAnchor="middle">
              {t >= 1 ? t : t.toFixed(Math.max(0, -Math.log10(t)))} s
            </text>
          </g>
        ))}
        {["median", "threshold", "last"].map((h, i) => (
          <text key={h} className="gantt-tick" x={cols + (i + 1) * S_COL_W - 8} y={14} textAnchor="end">
            {h}
          </text>
        ))}
        {groups.map((g, gi) => {
          const groupTop = tops[gi];
          return (
            <g key={g.group} data-strip-group={g.group}>
              <text className="gantt-group" x={0} y={groupTop + 17}>
                {g.group} ({g.steps.length})
              </text>
              {g.steps.map((s, i) => {
                const cy = groupTop + S_HEAD_H + i * S_ROW_H + S_ROW_H / 2;
                return (
                  <g
                    key={s.step_key}
                    data-step={s.step_key}
                    data-runs={s.points.length}
                    data-mode={s.last.mode}
                    data-earlier={s.earlier}
                    data-median={fmt(s.median)}
                    data-threshold={fmt(s.threshold)}
                    data-last={fmt(s.last.seconds)}
                    data-verdict={s.verdict}
                  >
                    <text className="gantt-label" x={S_LABEL_W - 8} y={cy + 4} textAnchor="end">
                      {s.step_key}
                    </text>
                    <line className="strip-base" x1={x(10 ** lo)} x2={x(10 ** hiE)} y1={cy} y2={cy} />
                    {s.points.slice(0, -1).map((p) => (
                      <circle
                        key={p.run}
                        className={p.comparable ? "strip-dot" : "strip-other"}
                        cx={x(p.seconds)}
                        cy={cy}
                        r={3.5}
                        data-run={p.run}
                        data-seconds={p.seconds.toFixed(1)}
                      >
                        <title>{`${runLabel(p.run)}: ${p.seconds.toFixed(1)} s, mode ${p.mode}`}</title>
                      </circle>
                    ))}
                    {s.median !== null && (
                      <line className="strip-median" x1={x(s.median)} x2={x(s.median)} y1={cy - 8} y2={cy + 8} />
                    )}
                    {s.threshold !== null && (
                      <line className="strip-threshold" x1={x(s.threshold)} x2={x(s.threshold)} y1={cy - 10} y2={cy + 10} />
                    )}
                    <circle
                      className="strip-last"
                      cx={x(s.last.seconds)}
                      cy={cy}
                      r={5}
                      data-run={s.last.run}
                      data-seconds={s.last.seconds.toFixed(1)}
                    >
                      <title>{`last, ${runLabel(s.last.run)}: ${s.last.seconds.toFixed(1)} s, mode ${s.last.mode}`}</title>
                    </circle>
                    <text className="gantt-value" x={cols + S_COL_W - 8} y={cy + 4} textAnchor="end">
                      {s.median === null ? "–" : s.median.toFixed(1)}
                    </text>
                    <text className="gantt-value" x={cols + 2 * S_COL_W - 8} y={cy + 4} textAnchor="end">
                      {s.threshold === null ? "–" : s.threshold.toFixed(1)}
                    </text>
                    <text className="gantt-label" x={cols + 3 * S_COL_W - 8} y={cy + 4} textAnchor="end">
                      {s.last.seconds.toFixed(1)}
                    </text>
                    {s.verdict === "above" && (
                      <path className="strip-above" d={`M${cols + 3 * S_COL_W + 4} ${cy + 4} l5 -9 l5 9 z`} />
                    )}
                    <text
                      className={s.verdict === "above" ? "gantt-label" : "gantt-value"}
                      x={cols + 3 * S_COL_W + 18}
                      y={cy + 4}
                    >
                      {s.verdict}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function StepTable({ series }: { series: Series }) {
  return (
    <details className="gantt-table history-table" data-strips-table>
      <summary>Every run as a table</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Step</th>
              <th scope="col">Seconds, run by run (mode)</th>
              <th scope="col">Median</th>
              <th scope="col">Threshold</th>
              <th scope="col">Last</th>
            </tr>
          </thead>
          <tbody>
            {series.steps.map((s) => (
              <tr key={s.step_key}>
                <th scope="row">{s.step_key}</th>
                <td>{s.points.map((p) => `${p.seconds.toFixed(1)} (${p.mode})`).join(", ")}</td>
                <td>{s.median === null ? "too few" : s.median.toFixed(1)}</td>
                <td>{s.threshold === null ? "too few" : s.threshold.toFixed(1)}</td>
                <td>
                  {s.last.seconds.toFixed(1)}, {s.verdict}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

// --- quality per run: dbt tests and contracts ---------------------------------------------------

const Q_RUN_W = 196;
const Q_SEL_W = 296;
const Q_BAR_W = 160;
const Q_BAR_LABEL_W = 132;
const Q_CON_W = 250;
const Q_ROW_H = 24;
const Q_HEAD_H = 28;

export const selectLabel = (select: string | null) => select ?? "complete build";

export function contractsText(c: HistoryEntry["quality"]["contracts"]): string {
  if (c.executed === true) {
    const extra = [c.failed ? `${c.failed} failed` : null, c.errors ? `${c.errors} errors` : null, c.skipped ? `${c.skipped} skipped` : null];
    return [`${c.passed} passed`, ...extra].filter(Boolean).join(", ");
  }
  if (c.executed === false) return c.status ?? "not run";
  return `${c.files === null ? "no data" : `${c.files} files`}, run: no data`;
}

export function dbtText(t: HistoryEntry["quality"]["dbt"]["tests"]): string {
  if (!t) return "no data";
  const parts = (["pass", "fail", "warn", "error", "skipped"] as const).filter((k) => k === "pass" || t[k] > 0);
  return parts.map((k) => `${t[k]} ${k}`).join(", ");
}

export function QualityTimeline({ entries }: { entries: HistoryEntry[] }) {
  const max = Math.max(...entries.map((e) => testTotal(e.quality.dbt.tests) ?? 0));
  const x0 = Q_RUN_W + Q_SEL_W;
  const width = x0 + Q_BAR_W + Q_BAR_LABEL_W + Q_CON_W;
  const height = Q_HEAD_H + entries.length * Q_ROW_H + 4;
  const w = (n: number) => (n / max) * Q_BAR_W;
  return (
    <div className="gantt-scroll history-scroll" data-quality tabIndex={0} role="region" aria-label="dbt tests and contract tests of every run, scrollable">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`dbt tests and contract tests of each of the ${entries.length} build records, oldest first`}>
        {[["run", 0], ["selection", Q_RUN_W], ["dbt tests", x0], ["contract tests", x0 + Q_BAR_W + Q_BAR_LABEL_W]].map(([h, hx]) => (
          <text key={h} className="gantt-tick" x={hx} y={16}>
            {h}
          </text>
        ))}
        {entries.map((e, i) => {
          const cy = Q_HEAD_H + i * Q_ROW_H + Q_ROW_H / 2;
          const t = e.quality.dbt.tests;
          const total = testTotal(t);
          const counts = t
            ? [
                { cls: "q-pass", n: t.pass },
                { cls: "q-fail", n: t.fail + t.error },
                { cls: "q-other", n: t.warn + t.skipped },
              ]
            : [];
          const segments = counts.map((sg, k) => ({ ...sg, x: x0 + counts.slice(0, k).reduce((a, b) => a + w(b.n), 0) }));
          const bx = x0 + w(total ?? 0);
          const c = e.quality.contracts;
          return (
            <g
              key={e.id}
              data-run={e.id}
              data-select={selectLabel(e.select)}
              data-dbt={total === null ? "no data" : String(total)}
              data-dbt-text={dbtText(t)}
              data-contracts={contractsText(c)}
            >
              <text className="gantt-label" x={0} y={cy + 4}>
                {runLabel(e.id)}
              </text>
              <text className="gantt-value" x={Q_RUN_W} y={cy + 4}>
                {selectLabel(e.select)}
              </text>
              {segments.map((sg) =>
                sg.n > 0 ? <rect key={sg.cls} className={sg.cls} x={sg.x} y={cy - 5} width={w(sg.n)} height={10} /> : null,
              )}
              <text className={t ? "gantt-label" : "gantt-value"} x={t ? bx + 6 : x0} y={cy + 4}>
                {dbtText(t)}
              </text>
              {c.executed === true && (c.failed ?? 0) + (c.errors ?? 0) > 0 && (
                <path className="strip-above" d={`M${x0 + Q_BAR_W + Q_BAR_LABEL_W - 14} ${cy + 4} l5 -9 l5 9 z`} />
              )}
              <text className={c.executed === true ? "gantt-label" : "gantt-value"} x={x0 + Q_BAR_W + Q_BAR_LABEL_W} y={cy + 4}>
                {contractsText(c)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function QualityTable({ entries }: { entries: HistoryEntry[] }) {
  return (
    <details className="gantt-table history-table" data-quality-table>
      <summary>Every run as a table</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Run</th>
              <th scope="col">Selection</th>
              <th scope="col">dbt tests</th>
              <th scope="col">Contract tests</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <th scope="row">{runLabel(e.id)}</th>
                <td>{selectLabel(e.select)}</td>
                <td>{dbtText(e.quality.dbt.tests)}</td>
                <td>{contractsText(e.quality.contracts)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

// --- freshness: the age at publish of each silver partition, gold table and the run ---------------

const F_LABEL_W = 200;
const F_PLOT_W = 440;
const F_VALUE_W = 180;
const F_ROW_H = 30;
const F_AXIS_H = 30;

function niceStep(max: number): number {
  for (const s of [1, 2, 5, 10, 15, 20, 30, 60, 120, 300, 600, 1200, 3000]) if (max / s <= 6) return s;
  return Math.ceil(max / 6);
}

export function FreshnessStrip({ rows }: { rows: FreshnessRow[] }) {
  const maxSeconds = Math.max(...rows.flatMap((r) => r.ages.map((a) => a.seconds)));
  const { unit, per } = ageUnit(maxSeconds);
  const step = niceStep(maxSeconds / per);
  const top = Math.max(step, Math.ceil(maxSeconds / per / step) * step);
  const x = (seconds: number) => F_LABEL_W + (Math.max(seconds, 0) / per / top) * F_PLOT_W;
  const width = F_LABEL_W + F_PLOT_W + F_VALUE_W;
  const height = F_AXIS_H + rows.length * F_ROW_H + 4;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  return (
    <div className="gantt-scroll history-scroll" data-freshness tabIndex={0} role="region" aria-label="Age at publish of silver, gold and the run, scrollable">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Age, in ${unit}, of each silver partition, gold table and the run when platform.json was published`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="gantt-grid" x1={x(t * per)} x2={x(t * per)} y1={F_AXIS_H - 6} y2={height - 4} />
            <text className="gantt-tick" x={x(t * per)} y={14} textAnchor="middle">
              {t} {unit}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cy = F_AXIS_H + i * F_ROW_H + F_ROW_H / 2;
          const ages = r.ages.map((a) => a.seconds);
          const lo = Math.min(...ages) / per;
          const hi = Math.max(...ages) / per;
          return (
            <g key={r.key} data-fresh-row={r.key} data-count={r.ages.length} data-min={lo.toFixed(1)} data-max={hi.toFixed(1)} data-unit={unit}>
              <text className="gantt-label" x={F_LABEL_W - 8} y={cy + 4} textAnchor="end">
                {r.label} ({r.ages.length})
              </text>
              <line className="strip-base" x1={x(0)} x2={x(top * per)} y1={cy} y2={cy} />
              {r.ages.map((a) => (
                <circle key={a.id} className={r.key === "run" ? "strip-last" : "strip-dot"} cx={x(a.seconds)} cy={cy} r={r.key === "run" ? 5 : 3.5} data-id={a.id} data-age={a.seconds.toFixed(0)}>
                  <title>{`${a.id}: written ${a.written_utc}, ${(a.seconds / per).toFixed(1)} ${unit} before publish`}</title>
                </circle>
              ))}
              <text className="gantt-value" x={F_LABEL_W + F_PLOT_W + 12} y={cy + 4}>
                {lo.toFixed(1) === hi.toFixed(1) ? `${hi.toFixed(1)} ${unit}` : `${lo.toFixed(1)} to ${hi.toFixed(1)} ${unit}`}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
