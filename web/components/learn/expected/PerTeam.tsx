import { seasonLabel } from "../../../lib/euroleague/atlas";
import { type ExpectedSeason, type TeamRow, xpName } from "../../../lib/learn/expected-data";
import { Fig } from "../Fig";
import { INK, signed, ticks } from "../gravity/Plot";

// One table per season, a row per team, most points per shot first: the strip draws its mix (cyan,
// upper lane) and its making (magenta, lower lane) from zero, each with its interval as a capped
// line (task 117b), and its points per shot against the league's (white tick), the sum of the two;
// the columns are the file's rows. Nothing is typed.
const STRIP_W = 300;
const STRIP_H = 24;
const FIELDS = ["pps", "xpps", "mix", "mix_ci", "making", "making_ci"] as const;

// One scale for every table: the widest value or bound of either season, out to the next 0.05.
const halfWidth = (seasons: readonly ExpectedSeason[]) =>
  Math.ceil(Math.max(...seasons.flatMap((s) => s.teams.flatMap((t) => [...t.mix_ci, ...t.making_ci, t.pps - s.mean].map(Math.abs)))) / 0.05) * 0.05;

export const byPoints = (teams: readonly TeamRow[]) => [...teams].sort((a, b) => b.pps - a.pps || a.code.localeCompare(b.code));

function Table({ s, d }: { s: ExpectedSeason; d: number }) {
  const sx = (v: number) => ((v + d) / (2 * d)) * STRIP_W;
  const bar = (v: number, y: number, color: string) => (
    <line x1={sx(0)} x2={sx(v)} y1={y} y2={y} stroke={color} strokeWidth={6} vectorEffect="non-scaling-stroke" />
  );
  const whisker = ([lo, hi]: readonly [number, number], y: number, color: string) => (
    <g stroke={color} strokeWidth={1.5} data-interval="">
      <line x1={sx(lo)} x2={sx(hi)} y1={y} y2={y} vectorEffect="non-scaling-stroke" />
      <line x1={sx(lo)} x2={sx(lo)} y1={y - 4} y2={y + 4} vectorEffect="non-scaling-stroke" />
      <line x1={sx(hi)} x2={sx(hi)} y1={y - 4} y2={y + 4} vectorEffect="non-scaling-stroke" />
    </g>
  );
  const fig = (t: TeamRow, path: string, value: number) => <Fig name={xpName(s.season, `teams.${t.code}.${path}`)}>{String(value)}</Fig>;
  const cell = (t: TeamRow, field: (typeof FIELDS)[number]) => {
    const v = t[field];
    return typeof v === "number" ? (
      fig(t, field, v)
    ) : (
      <>
        {fig(t, `${field}.0`, v[0])} to {fig(t, `${field}.1`, v[1])}
      </>
    );
  };
  // The title sits outside the scroller, so it wraps on a phone instead of scrolling with the table.
  const title = `xp-teams-${s.season}`;
  return (
    <>
      <p id={title} className="xp-teams-title">
        {seasonLabel(s.season)}, league <Fig name={xpName(s.season, "mean")}>{String(s.mean)}</Fig> points per shot
      </p>
      <div className="table-scroll">
        <table className="per-match learn-matches xp-teams" data-season={s.season} aria-labelledby={title}>
          <thead>
            <tr>
              <th scope="col">team</th>
              <th scope="col" className="per-match-strip" aria-label="mix and making, points per shot against the league's">
                <span className="per-match-axis" aria-hidden="true">
                  {ticks(-d, d, 0.1).map((v) => (
                    <span key={v} style={{ left: `${(sx(v) / STRIP_W) * 100}%` }}>
                      {signed(v, 1)}
                    </span>
                  ))}
                </span>
              </th>
              <th scope="col">points per shot</th>
              <th scope="col">expected</th>
              <th scope="col">mix</th>
              <th scope="col">mix interval</th>
              <th scope="col">making</th>
              <th scope="col">making interval</th>
              <th scope="col">name</th>
            </tr>
          </thead>
          <tbody>
            {byPoints(s.teams).map((t) => (
              <tr key={t.code} data-team={t.code}>
                <td>{t.code}</td>
                <td className="per-match-strip">
                  <svg viewBox={`0 0 ${STRIP_W} ${STRIP_H}`} preserveAspectRatio="none" aria-hidden="true">
                    <line x1={sx(0)} x2={sx(0)} y1={0} y2={STRIP_H} stroke={INK.axis} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                    {bar(t.mix, 7, INK.data)}
                    {bar(t.making, 17, INK.standard)}
                    {whisker(t.mix_ci, 7, INK.data)}
                    {whisker(t.making_ci, 17, INK.standard)}
                    <line x1={sx(t.pps - s.mean)} x2={sx(t.pps - s.mean)} y1={1} y2={STRIP_H - 1} stroke={INK.probe} strokeWidth={3} vectorEffect="non-scaling-stroke" />
                  </svg>
                </td>
                {FIELDS.map((f) => (
                  <td key={f}>{cell(t, f)}</td>
                ))}
                <td>{t.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function PerTeam({ seasons, level }: { seasons: readonly ExpectedSeason[]; level: { z: number; pct: number } }) {
  const d = halfWidth(seasons);
  return (
    <figure className="learn-fig surface-dark" data-figure="per-team">
      {seasons.map((s) => (
        <Table key={s.season} s={s} d={d} />
      ))}
      <ul className="learn-legend">
        <li>
          <span className="learn-swatch" style={{ color: INK.data }} aria-hidden="true" />
          mix: expected points per shot minus the league&apos;s
        </li>
        <li>
          <span className="learn-swatch" style={{ color: INK.standard }} aria-hidden="true" />
          making: points per shot minus expected
        </li>
        <li>
          <span className="learn-swatch learn-swatch-tick" style={{ color: INK.probe }} aria-hidden="true" />
          points per shot minus the league&apos;s, the two together
        </li>
        <li>
          <span className="learn-swatch learn-swatch-interval" style={{ color: INK.data }} aria-hidden="true" />
          an interval of mix or making, drawn in its colour
        </li>
      </ul>
      <figcaption>
        One row per team and season, as expected-points.json has it, field goals only. Expected is the team&apos;s own attempts,
        each at the league&apos;s points per attempt for its zone class. Each interval is the part plus and minus{" "}
        <Fig name="xp.z">{String(level.z)}</Fig> standard errors, at <Fig name="learn.level_pct">{String(level.pct)}</Fig>
        &nbsp;%. The current season counts the games played so far. Every figure is rounded on its own, so a part can differ by one in
        the last place from the difference of the figures beside it.
      </figcaption>
    </figure>
  );
}
