"""The biggest run and the biggest comeback (P14b, task 118), on toy games worked out by hand.

Game 1 (AAA at home to BBB, 2025-10-01), scoreboard after each basket, A-B:
  0-0, 2-0, 5-0, 6-0, 7-0 (a free throw by BBB cuts it: A's run is 7), 7-1, 9-1,
  9-4, 9-6, 9-9, 9-11, 9-14, 9-17 (B's run from 9-1 is 3+2+3+2+3+3 = 16), 11-17, 14-17, 14-19,
  14-22, 14-25 (A trails by 11 for the first time), 17-25, 20-25, 22-25, 25-25 (a tie), 27-25
  (A's run from 14-25 is 3+3+2+3+2 = 13). AAA wins 27-25 in regulation.
Game 2 (AAA at home to CCC, 2025-10-08): 3-0, 3-3, tied at the end of the fourth quarter, and in
  the overtime 3-6, 3-8, 6-8, 9-8. CCC's run goes on across the break: 3+3+2 = 8 from 3-0. AAA's
  best is 6 (3-8 to 9-8), it trailed by 5 and wins 9-8 in the overtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tracklab.euroleague.aggregates import EuroleaguePublishError
from tracklab.euroleague.runs import (
    Run,
    load_games,
    ranked,
    read_game,
    score_path,
    season_block,
)

Score = tuple[int, int]
GAME_1_PERIODS: list[list[Score | None]] = [
    [(2, 0), None, (5, 0), (6, 0), (7, 0), (7, 0), (7, 1), (9, 1)],  # (7, 0) twice: a repeat
    [(9, 4), (9, 6), None, (9, 9), (9, 11), (9, 14), (9, 17)],
    [(11, 17), (14, 17), (14, 19), None, (14, 22), (14, 25)],
    [(17, 25), (20, 25), None, (22, 25), (22, 25), (25, 25), (27, 25)],  # a foul and a repeat
]
GAME_2_PERIODS: list[list[Score | None]] = [
    [(3, 0), (3, 3)],
    [None],
    [None],
    [None],
    [(3, 6), (3, 8), (6, 8), (9, 8)],
]


def row(score: Score | None, number: int) -> dict[str, Any]:
    if score is None:  # a foul, a turnover, a miss: no scoreboard
        return {"NUMBEROFPLAY": number, "PLAYTYPE": "CM", "POINTS_A": None, "POINTS_B": None}
    a, b = score
    return {
        "NUMBEROFPLAY": number,
        "PLAYTYPE": "2FGM",
        "POINTS_A": a or None,  # the feed leaves a team's 0 blank
        "POINTS_B": b or None,
    }


def feed(periods: list[list[Score | None]]) -> dict[str, Any]:
    """A play-by-play whose NUMBEROFPLAY runs backwards inside each period, as it does not
    follow the clock in the real feed."""
    names = ("FirstQuarter", "SecondQuarter", "ThirdQuarter", "ForthQuarter", "ExtraTime")
    out: dict[str, Any] = {"CodeTeamA": "AAA ", "CodeTeamB": "BBB "}
    number = 1000
    for name, plays in zip(names, [*periods, []], strict=False):
        rows = []
        for score in plays:
            number -= 1
            rows.append(row(score, number))
        out[name] = rows
    for name in names[len(periods) :]:
        out.setdefault(name, [])
    return out


def test_the_path_is_ordered_by_the_sum_and_drops_repeats() -> None:
    path = score_path(feed(GAME_1_PERIODS))
    expected = [(0, 0)] + [s for p in GAME_1_PERIODS for s in p if s is not None]
    expected = [s for i, s in enumerate(expected) if i == 0 or s != expected[i - 1]]
    assert path == expected
    assert len(path) == 23  # 22 baskets and the start
    assert path[-1] == (27, 25)


def test_game_one_run_cut_by_a_rival_free_throw_and_a_comeback_through_a_tie() -> None:
    game = read_game(score_path(feed(GAME_1_PERIODS)))
    assert game.runs[0] == Run(0, 13, (14, 25), (27, 25))  # not 7, 7 + 2 or 20
    assert game.runs[1] == Run(1, 16, (9, 1), (9, 17))
    assert (game.final, game.winner) == ((27, 25), 0)
    assert (game.deficit, game.deficit_at) == (11, (14, 25))


def test_game_two_a_run_across_the_break_and_a_comeback_in_the_overtime() -> None:
    path = score_path(feed(GAME_2_PERIODS))
    assert path == [(0, 0), (3, 0), (3, 3), (3, 6), (3, 8), (6, 8), (9, 8)]
    game = read_game(path)
    assert game.runs[1] == Run(1, 8, (3, 0), (3, 8))  # 3 before the break, 5 after it
    assert game.runs[0] == Run(0, 6, (3, 8), (9, 8))
    assert (game.final, game.winner, game.deficit, game.deficit_at) == ((9, 8), 0, 5, (3, 8))


def test_without_the_overtime_game_two_is_a_tie_and_is_refused() -> None:
    pbp = feed(GAME_2_PERIODS)
    with pytest.raises(EuroleaguePublishError, match="tie"):
        read_game(
            score_path(
                pbp, periods=("FirstQuarter", "SecondQuarter", "ThirdQuarter", "ForthQuarter")
            )
        )


def test_a_step_that_raises_both_sides_is_nobody_s_run() -> None:
    game = read_game([(0, 0), (2, 0), (3, 3), (5, 3)])
    assert game.runs[0] == Run(0, 2, (0, 0), (2, 0))  # 2 and 2, not 4; a tie keeps the first
    assert game.runs[1] is None  # the 3 of the step is not credited
    assert (game.winner, game.deficit) == (0, 0)


def test_a_scoreboard_that_goes_back_is_not_a_path() -> None:
    with pytest.raises(EuroleaguePublishError, match="not a path"):
        score_path({"FirstQuarter": [row((4, 1), 1), row((3, 2), 2)]})


def games() -> list[Any]:
    from tracklab.euroleague.runs import Played

    return [
        Played("2025-10-01", ("AAA", "BBB"), read_game(score_path(feed(GAME_1_PERIODS)))),
        Played("2025-10-08", ("AAA", "CCC"), read_game(score_path(feed(GAME_2_PERIODS)))),
    ]


def test_the_summary_by_team_counts_the_threshold_with_greater_or_equal() -> None:
    block = season_block("E2025", games(), 2, "2025-10-08", 0, run_min=13, deficit_min=5, top=3)
    summary = {t["code"]: t for t in block["teams"]}
    keys = ("games", "best_run", "runs_n", "comeback_for", "comeback_against", "wins_from_n")
    assert [[summary[c][k] for k in keys] for c in ("AAA", "BBB", "CCC")] == [
        [2, 13, 1, 11, 0, 2],  # a run of exactly 13 counts; a win from exactly 5 down counts
        [1, 16, 1, 0, 11, 0],
        [1, 8, 0, 0, 5, 0],
    ]
    assert [t["code"] for t in block["teams"]] == ["AAA", "BBB", "CCC"]


def test_the_rankings_name_both_teams_the_date_and_the_scores() -> None:
    block = season_block("E2025", games(), 2, "2025-10-08", 0, run_min=13, deficit_min=5, top=3)
    assert block["runs"] == [
        {
            "team": "BBB",
            "opp": "AAA",
            "date": "2025-10-01",
            "size": 16,
            "from": [1, 9],
            "to": [17, 9],
        },
        {
            "team": "AAA",
            "opp": "BBB",
            "date": "2025-10-01",
            "size": 13,
            "from": [14, 25],
            "to": [27, 25],
        },
        {
            "team": "CCC",
            "opp": "AAA",
            "date": "2025-10-08",
            "size": 8,
            "from": [0, 3],
            "to": [8, 3],
        },
    ]
    assert block["comebacks"] == [
        {
            "team": "AAA",
            "opp": "BBB",
            "date": "2025-10-01",
            "deficit": 11,
            "at": [14, 25],
            "final": [27, 25],
        },
        {
            "team": "AAA",
            "opp": "CCC",
            "date": "2025-10-08",
            "deficit": 5,
            "at": [3, 8],
            "final": [9, 8],
        },
    ]
    # No play, no clock, no id: the entries hold these keys and no more.
    assert {frozenset(r) for r in block["runs"]} == {
        frozenset({"team", "opp", "date", "size", "from", "to"})
    }


def test_the_loser_s_best_deficit_is_not_a_comeback() -> None:
    # BBB led by 17 - 9 and by 25 - 14 and lost: that is not a comeback of BBB's
    block = season_block("E2025", games(), 2, "2025-10-08", 0, run_min=13, deficit_min=5)
    assert {t["code"]: t["comeback_for"] for t in block["teams"]} == {"AAA": 11, "BBB": 0, "CCC": 0}


def test_a_ranking_keeps_everyone_who_ties_with_the_last() -> None:
    def entry(size: int, date: str) -> tuple[int, str, str, dict[str, Any]]:
        return (-size, date, "X", {"size": size, "date": date})

    rows = [entry(9, "d3"), entry(5, "d1"), entry(5, "d2"), entry(5, "d4"), entry(2, "d1")]
    assert [r["date"] for r in ranked(rows, 3)] == ["d3", "d1", "d2", "d4"]  # the 5s all stay
    assert [r["date"] for r in ranked(rows, 1)] == ["d3"]
    assert len(ranked(rows, 10)) == 5


def write_raw(root: Path, official: list[int], pbp: dict[str, Any]) -> Path:
    season = root / "E2025"
    (season / "PlaybyPlay").mkdir(parents=True)
    (season / "Boxscore").mkdir()
    (season / "PlaybyPlay" / "1.json").write_text(json.dumps(pbp), encoding="utf-8")
    box = {"Stats": [{"totr": {"Points": official[0]}}, {"totr": {"Points": official[1]}}]}
    (season / "Boxscore" / "1.json").write_text(json.dumps(box), encoding="utf-8")
    manifest = {
        "cutoff": "2025-10-01",
        "games": [
            {
                "gamecode": 1,
                "date": "2025-10-01",
                "files": {"PlaybyPlay": "PlaybyPlay/1.json", "Boxscore": "Boxscore/1.json"},
            }
        ],
    }
    (season / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_the_rebuilt_score_must_be_the_boxscore_s(tmp_path: Path) -> None:
    raw = write_raw(tmp_path, [27, 25], feed(GAME_1_PERIODS))
    played, total, cutoff, left_out = load_games(raw, "E2025")
    assert (len(played), total, cutoff, left_out) == (1, 1, "2025-10-01", 0)
    assert played[0].codes == ("AAA", "BBB")
    wrong = write_raw(tmp_path / "wrong", [27, 26], feed(GAME_1_PERIODS))
    with pytest.raises(EuroleaguePublishError, match="Boxscore says"):
        load_games(wrong, "E2025")


def test_a_game_without_a_scoreboard_is_left_out_and_counted(tmp_path: Path) -> None:
    raw = write_raw(tmp_path, [0, 0], feed([[None, None]]))
    played, total, _, left_out = load_games(raw, "E2025")
    assert (played, total, left_out) == ([], 1, 1)
