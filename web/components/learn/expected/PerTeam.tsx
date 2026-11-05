import { seasonLabel } from "../../../lib/euroleague/atlas";
import { type ExpectedSeason, type TeamRow, xpName } from "../../../lib/learn/expected-data";
import { Fig } from "../Fig";
import { INK, signed, ticks } from "../gravity/Plot";

// One table per season, a row per team, most points per shot first: the strip draws its mix (cyan,
// upper lane) and its making (magenta, lower lane) from zero, and its points per shot against the
// league's (white tick), the sum of the two; the columns are the file's rows. Nothing is typed.
const STRIP_W = 300;
const STRIP_H = 24;
const FIELDS = ["pps", "xpps", "mix", "making"] as const;

// One scale for every table: the widest value of either season, out to the next 0.05.
const halfWidth = (seasons: readonly ExpectedSeason[]) =>
  Math.ceil(Math.max(...seasons.flatMap((s) => s.teams.flatMap((t) => [Math.abs(t.mix), Math.abs(t.making), Math.abs(t.pps - s.mean)]))) / 0.05) * 0.05;

export const byPoints = (teams: readonly TeamRow[]) => [...teams].sort((a, b) => b.pps - a.pps || a.code.localeCompare(b.code));

function Table({ s, d }: { s: ExpectedSeason; d: number }) {
  const sx = (v: number) => ((v + d) / (2 * d)) * STRIP_W;
  const bar = (v: number, y: number, color: string) => (
    <line x1={sx(0)} x2={sx(v)} y1={y} y2={y} stroke={color} strokeWidth={6} vectorEffect="non-scaling-stroke" />
  );
  const cell = (t: TeamRow, field: string) => <Fig name={xpName(s.season, `teams.${t.code}.${field}`)}>{String(t[field as keyof TeamRow])}</Fig>;
  return (
    <div className="table-scroll">
      <table className="per-match learn-matches xp-teams" data-season={s.season}>
        <caption>
          {seasonLabel(s.season)}, league <Fig name={xpName(s.season, "mean")}>{String(s.mean)}</Fig> points per shot
        </caption>
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
            <th scope="col">making</th>
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
  );
}

export function PerTeam({ seasons }: { seasons: readonly ExpectedSeason[] }) {
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
      </ul>
      <figcaption>
        One row per team and season, as expected-points.json has it, field goals only. Expected is the team&apos;s own attempts,
        each at the league&apos;s points per attempt for its zone class. The current season counts the games played so far.
      </figcaption>
    </figure>
  );
}
