"""``runs.json`` (P14b, task 118): the biggest scoring run and the biggest comeback, never a play.

Each game's play-by-play is read here, on this machine, and reduced to two numbers per team; what
leaves is the top ``TOP`` of each by season and a summary by team. No row of the feed, no event id
and no clock goes out. The definitions are the spec's (docs/superpowers/specs/2026-10-31-euroleague-
design.md): a run is the most points a team scores in a row inside one game with the rival not
scoring; the comeback of a game is the biggest deficit the team that won had overcome.

Reading the feed (docs/euroleague-probe.md section 6, and what 492 games showed):

- Only plays that carry the scoreboard (``POINTS_A``/``POINTS_B``, a team's blank is 0) count. A
  foul, a turnover or a miss has none, so it never cuts a run: only the rival scoring does.
- ``NUMBEROFPLAY`` is not chronological. The plays are ordered by ``POINTS_A + POINTS_B``: every
  basket adds 1 to 3 to one side, so the sum is a clock of the game.
- A scoreboard that repeats (a late row restating a score) is one point of the path. In 492 games,
  10 repeats.
- Quarters and overtime are one path: a run goes on across a break, and the overtime is read like
  any other period. Free throws in a row are steps of 1 or 2 by the same team and add up; one by
  the rival cuts the run.
- Eight steps of 492 games raise both sides at once (the feed lost the middle score). Which came
  first cannot be known, so the step is counted as nobody's: it cuts both runs and starts none.
  That can only make a run shorter, by at most 3 points.
- The rebuilt final score must be the Boxscore's ``totr.Points``; if one is not, nothing is
  written. A game whose play-by-play has no scoreboard at all is left out and counted.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tracklab.euroleague.aggregates import (
    QUARTERS,
    SOURCE,
    VERSION,
    EuroleaguePublishError,
    _read_json,
)

TOP = 10  # rows of each ranking by season (and whoever ties with the 10th)
RUN_MIN = 12  # a game counts in a team's "runs of N or more" at this many points in a row
DEFICIT_MIN = 10  # a win counts in "wins after trailing by N or more" from this deficit
Score = tuple[int, int]


@dataclass(frozen=True)
class Run:
    side: int  # 0 = team A (home), 1 = team B
    size: int
    start: Score  # (A, B) before its first point
    end: Score  # (A, B) after its last


@dataclass(frozen=True)
class Game:
    runs: tuple[Run | None, Run | None]  # the biggest run of each side; None if it never scored
    final: Score
    winner: int
    deficit: int  # the most the winner trailed by
    deficit_at: Score  # the score the first time it trailed by that much


def score_path(pbp: dict[str, Any], periods: tuple[str, ...] = QUARTERS) -> list[Score]:
    """The scoreboards of the game, from 0-0, in play order and without repeats."""
    seen: list[Score] = []
    for period in periods:
        for play in pbp.get(period) or []:
            a, b = play.get("POINTS_A"), play.get("POINTS_B")
            if a is not None or b is not None:
                seen.append((int(a or 0), int(b or 0)))
    path: list[Score] = [(0, 0)]
    for score in sorted(seen, key=sum):
        if score == path[-1]:
            continue
        if score[0] < path[-1][0] or score[1] < path[-1][1]:
            raise EuroleaguePublishError(f"scoreboard {score} after {path[-1]}: not a path")
        path.append(score)
    return path


def read_game(path: list[Score]) -> Game:
    best: list[Run | None] = [None, None]
    open_side: int | None = None
    open_start: Score = (0, 0)
    deficits = [(0, (0, 0)), (0, (0, 0))]  # per side: most trailed by, and the score then
    for before, after in zip(path, path[1:], strict=False):
        gain = (after[0] - before[0], after[1] - before[1])
        side = 0 if gain[1] == 0 else 1 if gain[0] == 0 else None
        if side is None:  # both sides moved: nobody's run
            open_side = None
        else:
            if open_side != side:
                open_side, open_start = side, before
            size = after[side] - open_start[side]
            if best[side] is None or size > best[side].size:  # type: ignore[union-attr]
                best[side] = Run(side, size, open_start, after)
        for s in (0, 1):
            behind = after[1 - s] - after[s]
            if behind > deficits[s][0]:
                deficits[s] = (behind, after)
    final = path[-1]
    if final[0] == final[1]:
        raise EuroleaguePublishError(f"final score {final} is a tie")
    winner = 0 if final[0] > final[1] else 1
    return Game((best[0], best[1]), final, winner, deficits[winner][0], deficits[winner][1])


def _own(score: Score, side: int) -> list[int]:
    return [score[side], score[1 - side]]


@dataclass(frozen=True)
class Played:
    date: str
    codes: tuple[str, str]  # (A, B)
    game: Game


def load_games(raw: Path, season: str) -> tuple[list[Played], int, str, int]:
    """The games of the season that have a scoreboard: (games, played, cutoff, left out)."""
    manifest = _read_json(raw / season / "manifest.json")
    out: list[Played] = []
    left_out = 0
    for entry in sorted(manifest["games"], key=lambda g: (g["date"], g["gamecode"])):
        pbp = _read_json(raw / season / entry["files"]["PlaybyPlay"])
        path = score_path(pbp)
        if len(path) == 1:
            left_out += 1
            continue
        official = [
            int(t["totr"]["Points"])
            for t in _read_json(raw / season / entry["files"]["Boxscore"])["Stats"]
        ]
        if list(path[-1]) != official:
            raise EuroleaguePublishError(
                f"{season} game {entry['gamecode']}: the play-by-play ends {path[-1]}, "
                f"the Boxscore says {official}"
            )
        codes = (str(pbp["CodeTeamA"]).strip(), str(pbp["CodeTeamB"]).strip())
        out.append(Played(str(entry["date"]), codes, read_game(path)))
    return out, len(manifest["games"]), str(manifest["cutoff"]), left_out


def ranked(
    rows: list[tuple[int, str, str, dict[str, Any]]], top: int = TOP
) -> list[dict[str, Any]]:
    """The ``top`` biggest (rows are ``(-size, date, team, entry)``), and everyone who ties with
    the last of them: a ranking that cut a tie by date would say the later game is smaller."""
    rows = sorted(rows, key=lambda r: r[:3])
    if len(rows) > top:
        rows = [r for r in rows if r[0] <= rows[top - 1][0]]
    return [r[3] for r in rows]


def season_block(
    season: str,
    games: list[Played],
    played: int,
    cutoff: str,
    left_out: int,
    *,
    run_min: int = RUN_MIN,
    deficit_min: int = DEFICIT_MIN,
    top: int = TOP,
) -> dict[str, Any]:
    run_rows, comeback_rows = [], []
    teams: dict[str, dict[str, int]] = defaultdict(
        lambda: dict.fromkeys(
            ("games", "best_run", "runs_n", "comeback_for", "comeback_against", "wins_from_n"), 0
        )
    )
    for g in games:
        for side in (0, 1):
            team, rival = g.codes[side], g.codes[1 - side]
            t = teams[team]
            t["games"] += 1
            run = g.game.runs[side]
            if run is not None:
                t["best_run"] = max(t["best_run"], run.size)
                if run.size >= run_min:
                    t["runs_n"] += 1
                run_rows.append(
                    (
                        -run.size,
                        g.date,
                        team,
                        {
                            "team": team,
                            "opp": rival,
                            "date": g.date,
                            "size": run.size,
                            "from": _own(run.start, side),
                            "to": _own(run.end, side),
                        },
                    )
                )
            if g.game.winner == side:
                t["comeback_for"] = max(t["comeback_for"], g.game.deficit)
                if g.game.deficit >= deficit_min:
                    t["wins_from_n"] += 1
                comeback_rows.append(
                    (
                        -g.game.deficit,
                        g.date,
                        team,
                        {
                            "team": team,
                            "opp": rival,
                            "date": g.date,
                            "deficit": g.game.deficit,
                            "at": _own(g.game.deficit_at, side),
                            "final": _own(g.game.final, side),
                        },
                    )
                )
            else:
                t["comeback_against"] = max(t["comeback_against"], g.game.deficit)
    return {
        "season": season,
        "cutoff": cutoff,
        "games_played": played,
        "games_read": len(games),
        "games_left_out": left_out,
        "runs": ranked(run_rows, top),
        "comebacks": ranked(comeback_rows, top),
        "teams": [{"code": c, **teams[c]} for c in sorted(teams)],
    }


def runs_payload(raw: Path, seasons: list[str]) -> dict[str, Any]:
    blocks = []
    for season in seasons:
        games, played, cutoff, left_out = load_games(raw, season)
        blocks.append(season_block(season, games, played, cutoff, left_out))
    return {
        "version": VERSION,
        "source": SOURCE,
        "top": TOP,
        "run_min": RUN_MIN,
        "deficit_min": DEFICIT_MIN,
        "seasons": blocks,
    }
