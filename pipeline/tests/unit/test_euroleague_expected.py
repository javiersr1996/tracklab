"""Lesson 12's expected-points.json on a season built by hand: every figure is worked out below.

E2025, three teams, k = 5. Attempts, makes and points by zone class:

    AAA  rim 10, 6, 12   mid  5, 2,  4   three 5, 2, 6   (and one two with no zone)
    BBB  rim 10, 5, 10   mid 10, 5, 10   three 5, 3, 9
    CCC  rim  5, 4,  8   mid  5, 1,  2   three 4, 2, 6   (three under k: left out)
    league rim 25, 15, 30 -> 1.2;  mid 20, 8, 16 -> 0.8;  three 14, 7, 21 -> 1.5
    mean = 67 / 59 = 1.135593...

AAA: pps 22/20 = 1.1; xpps (10*1.2 + 5*0.8 + 5*1.5)/20 = 23.5/20 = 1.175;
     mix 1.175 - 1.135593 = 0.039; making 1.1 - 1.175 = -0.075.
BBB: pps 29/25 = 1.16; xpps (12 + 8 + 7.5)/25 = 1.1; mix -0.036; making 0.06.
The unweighted mean of the three classes would be 3.5/3 = 1.167, for the league and for an
xpps not weighted by attempts: neither is any figure above.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from tracklab.euroleague.aggregates import (
    EuroleaguePublishError,
    Season,
    Shot,
    expected_payload,
    public_sql_problems,
    render,
)


def _shots(team: str, zone: str | None, n: int, made: int, value: int) -> list[Shot]:
    return [
        Shot(team, "1", "PLAYER", i < made, value if i < made else 0, (0, 0), zone, False)
        for i in range(n)
    ]


def _season(code: str, shots: list[Shot], teams: tuple[str, ...]) -> Season:
    names = {t: f"Team {t}" for t in teams}
    return Season(code, "2025-10-08", 2, shots, names, Counter(dict.fromkeys(teams, 1)))


E2025 = _season(
    "E2025",
    [
        *_shots("AAA", "rim", 10, 6, 2),
        *_shots("AAA", "mid", 5, 2, 2),
        *_shots("AAA", "three", 5, 2, 3),
        *_shots("AAA", None, 1, 1, 2),
        *_shots("BBB", "rim", 10, 5, 2),
        *_shots("BBB", "mid", 10, 5, 2),
        *_shots("BBB", "three", 5, 3, 3),
        *_shots("CCC", "rim", 5, 4, 2),
        *_shots("CCC", "mid", 5, 1, 2),
        *_shots("CCC", "three", 4, 2, 3),
    ],
    ("AAA", "BBB", "CCC"),
)
# A season whose league has four threes: under k, so it is left out whole.
E2026 = _season(
    "E2026",
    [
        *_shots("AAA", "rim", 10, 5, 2),
        *_shots("AAA", "mid", 10, 5, 2),
        *_shots("BBB", "three", 4, 1, 3),
    ],
    ("AAA", "BBB"),
)


def test_the_league_by_zone_class() -> None:
    doc = expected_payload([E2025])
    assert (doc["version"], doc["k"], doc["classes"], doc["rim_zones"]) == (
        1,
        5,
        ["rim", "mid", "three"],
        ["A", "B", "C"],
    )
    (block,) = doc["seasons"]
    assert (block["season"], block["cutoff"], block["games_played"]) == ("E2025", "2025-10-08", 2)
    assert block["league"] == {
        "rim": {"n": 25, "made": 15, "pts": 30},
        "mid": {"n": 20, "made": 8, "pts": 16},
        "three": {"n": 14, "made": 7, "pts": 21},
        "unclassified": 1,
    }
    assert block["pps"] == {"rim": 1.2, "mid": 0.8, "three": 1.5}
    assert block["mean"] == 1.136  # 67 / 59, weighted by attempts; unweighted it would be 1.167


def test_each_team_against_the_league() -> None:
    (block,) = expected_payload([E2025])["seasons"]
    aaa, bbb = block["teams"]
    assert aaa == {
        "code": "AAA",
        "name": "Team AAA",
        "rim": {"n": 10, "made": 6, "pts": 12},
        "mid": {"n": 5, "made": 2, "pts": 4},
        "three": {"n": 5, "made": 2, "pts": 6},
        "pps": 1.1,
        "xpps": 1.175,
        "mix": 0.039,
        "making": -0.075,
    }
    assert {k: bbb[k] for k in ("code", "pps", "xpps", "mix", "making")} == {
        "code": "BBB",
        "pps": 1.16,
        "xpps": 1.1,
        "mix": -0.036,
        "making": 0.06,
    }
    # CCC took four threes, under k: it is left out, though its shots count for the league.
    assert block["teams_left_out"] == 1


def test_a_season_with_a_class_under_k_is_left_out() -> None:
    assert [s["season"] for s in expected_payload([E2025, E2026])["seasons"]] == ["E2025"]
    with pytest.raises(EuroleaguePublishError, match="no season"):
        expected_payload([E2026])


def test_every_count_is_k_or_more() -> None:
    # k = 6: AAA's five mid-range shots and BBB's five threes are now under it, like CCC's four.
    (block,) = expected_payload([E2025], k=6)["seasons"]
    assert (block["teams"], block["teams_left_out"]) == ([], 3)
    # k = 11: the league's three-point attempts (14) still pass; with 15, no season does.
    assert [t["code"] for t in expected_payload([E2025], k=11)["seasons"][0]["teams"]] == []
    with pytest.raises(EuroleaguePublishError):
        expected_payload([E2025], k=15)


def test_the_public_query_gives_the_file(tmp_path: Path) -> None:
    path = tmp_path / "expected-points.json"
    path.write_text(render(expected_payload([E2025])), encoding="utf-8", newline="\n")
    assert public_sql_problems(path) == (2, [])
    text = path.read_text(encoding="utf-8").replace('"making":-0.075', '"making":-0.074')
    path.write_text(text, encoding="utf-8", newline="\n")
    rows, problems = public_sql_problems(path)
    assert rows == 2 and len(problems) == 1 and "AAA" in problems[0]
