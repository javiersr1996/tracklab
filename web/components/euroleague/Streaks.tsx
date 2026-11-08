import type { ReactNode } from "react";
import { seasonLabel } from "../../lib/euroleague/atlas";
import { type Pair, ranks, type Runs, score, type TeamRuns } from "../../lib/euroleague/runs";
import { Band } from "../site/Band";

interface Entry {
  team: string;
  opp: string;
  date: string;
  size: number;
  detail: ReactNode;
}

function Ranking({
  id,
  title,
  note,
  unit,
  entries,
  selected,
  names,
}: {
  id: string;
  title: string;
  note: string;
  unit: string;
  entries: Entry[];
  selected: string;
  names: Record<string, string>;
}) {
  const place = ranks(entries.map((e) => e.size));
  const biggest = entries[0]?.size ?? 1;
  return (
    <div className="el-rank-block">
      <h3 id={`el-${id}-title`}>{title}</h3>
      <p className="el-rank-note">{note}</p>
      <ol className="el-ranking" aria-labelledby={`el-${id}-title`} data-ranking={id}>
        {entries.map((e, i) => (
          <li
            key={`${e.team}|${e.date}|${e.opp}`}
            className="el-rank-row"
            data-rank-team={e.team}
            data-selected={selected === e.team ? "true" : undefined}
            aria-current={selected === e.team ? "true" : undefined}
          >
            <span className="el-rank-place">{place[i]}</span>
            <span className="el-rank-who">
              <strong>{names[e.team] ?? e.team}</strong> against {names[e.opp] ?? e.opp}
            </span>
            <span className="el-rank-size" data-rank-size>
              {e.size}
              <span className="el-rank-unit"> {unit}</span>
            </span>
            <span className="el-rank-bar" aria-hidden="true">
              <span style={{ width: `${(e.size / biggest) * 100}%` }} />
            </span>
            <span className="el-rank-meta">
              {e.date}, {e.detail}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

const STATS: { key: keyof Omit<TeamRuns, "code" | "games">; label: (r: Runs) => string }[] = [
  { key: "best_run", label: () => "Biggest run" },
  { key: "runs_n", label: (r) => `Games with a run of ${r.run_min}+` },
  { key: "comeback_for", label: () => "Biggest comeback for" },
  { key: "comeback_against", label: () => "Biggest comeback against" },
  { key: "wins_from_n", label: (r) => `Wins after trailing by ${r.deficit_min}+` },
];

// A score never breaks across lines: "77–50" stays whole.
const S = ({ p }: { p: Pair }) => <span className="el-score">{score(p)}</span>;

// "Runs and comebacks" (task 118): the top of the season's biggest runs and comebacks, and a card
// per team, from runs.json. The team chosen in the atlas comes first, lit, as in "What has changed".
export function Streaks({
  runs,
  season,
  selected,
  names,
}: {
  runs: Runs;
  season: string;
  selected: string;
  names: Record<string, string>;
}) {
  const block = runs.seasons.find((s) => s.season === season)!;
  const teams = [...block.teams].sort((a, b) => {
    if (a.code === selected || b.code === selected) return a.code === selected ? -1 : 1;
    return b.best_run - a.best_run || (names[a.code] ?? a.code).localeCompare(names[b.code] ?? b.code);
  });
  return (
    <Band dark className="el-streaks-band">
      <section aria-labelledby="el-streaks-title" data-streaks={season}>
        <h2 id="el-streaks-title">Runs and comebacks</h2>
        <p>
          A run is the most points a team scores in a row inside a game while the other side does not score; a
          comeback is the biggest deficit that the team that won had overcome. {seasonLabel(season)}:{" "}
          {block.games_read} games read, through {block.cutoff}. Each list is the top {runs.top} of the season,
          with every tie at the last place kept; the rest of the games are summed up by team below, never one row
          per game.
        </p>
        <div className="el-rankings">
          <Ranking
            id="runs"
            title="Biggest runs"
            note="Points in a row by one team, and the score it started and ended on (its own first)."
            unit="in a row"
            selected={selected}
            names={names}
            entries={block.runs.map((r) => ({
              team: r.team,
              opp: r.opp,
              date: r.date,
              size: r.size,
              detail: (
                <>
                  from <S p={r.from} /> to <S p={r.to} />
                </>
              ),
            }))}
          />
          <Ranking
            id="comebacks"
            title="Biggest comebacks"
            note="The deficit the winner overcame, the score when it was that far behind and the final score."
            unit="down"
            selected={selected}
            names={names}
            entries={block.comebacks.map((c) => ({
              team: c.team,
              opp: c.opp,
              date: c.date,
              size: c.deficit,
              detail: (
                <>
                  trailed <S p={c.at} />, won <S p={c.final} />
                </>
              ),
            }))}
          />
        </div>
        <h3 id="el-streaks-teams-title">By team</h3>
        <p>
          Sorted by the biggest run, with the team chosen above first. A game counts in &ldquo;games with a run
          of {runs.run_min}+&rdquo; from {runs.run_min} points in a row, and in &ldquo;wins after trailing by{" "}
          {runs.deficit_min}+&rdquo; from {runs.deficit_min} points behind.
        </p>
        <ol className="el-streak-teams" aria-labelledby="el-streaks-teams-title">
          {teams.map((t) => (
            <li
              key={t.code}
              className="el-streak-team"
              data-streak-team={t.code}
              data-selected={selected === t.code ? "true" : undefined}
              aria-current={selected === t.code ? "true" : undefined}
            >
              <h4 className="el-streak-name">{names[t.code] ?? t.code}</h4>
              <p className="el-streak-games">{t.games} games</p>
              <dl className="el-streak-stats">
                {STATS.map((s) => (
                  <div key={s.key}>
                    <dt>{s.label(runs)}</dt>
                    <dd data-stat={s.key}>{t[s.key]}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ol>
      </section>
    </Band>
  );
}
