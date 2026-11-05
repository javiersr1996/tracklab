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

The intervals (task 117b), z = 1.96 at 0.95. Each attempt adds e_z - mean to mix and its points
- e_z to making; the standard error of each part is the spread of those over sqrt(n).
AAA mix: mean of e_z^2 over its attempts (0.5 * 1.44 + 0.25 * 0.64 + 0.25 * 2.25) = 1.4425, so
     the variance is 1.4425 - 1.175^2 = 0.061875 and se = sqrt(0.061875 / 20) = 0.0556215;
     0.0394068 -+ 1.96 * 0.0556215 = -0.069611 .. 0.148425 -> [-0.07, 0.148].
AAA making: its 20 attempts add 0.8 (6 makes at the rim), -1.2 (4 misses), 1.2 and -0.8 (2 and
     3 from mid-range), 1.5 and -1.5 (2 and 3 threes): squares 3.84 + 5.76 + 2.88 + 1.92 + 4.5 +
     6.75 = 25.65, variance 25.65 / 20 - 0.075^2 = 1.276875, se = 0.2526732;
     -0.075 -+ 0.4952395 = -0.570239 .. 0.420239 -> [-0.57, 0.42].
BBB mix: 0.4 * 1.44 + 0.4 * 0.64 + 0.2 * 2.25 = 1.282, variance 0.072, se = sqrt(0.072 / 25)
     = 0.0536656; -0.0355932 -+ 0.1051846 -> [-0.141, 0.07].
BBB making: squares 5 * 0.64 + 5 * 1.44 + 5 * 1.44 + 5 * 0.64 + 3 * 2.25 + 2 * 2.25 = 32.05,
     variance 32.05 / 25 - 0.06^2 = 1.2784, se = 0.2261327; 0.06 -+ 0.4432201 -> [-0.383, 0.503].
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from tracklab.euroleague.aggregates import (
    CLASSES,
    EuroleaguePublishError,
    Season,
    Shot,
    expected_payload,
    games_ratios,
    public_sql_problems,
    render,
    standard_errors,
    z_of,
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
    assert (doc["level"], doc["z"], doc["games_bootstrap"]) == (
        0.95,
        1.96,
        {"seed": 117, "replicates": 10_000},
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
        "mix_ci": [-0.07, 0.148],
        "making_ci": [-0.57, 0.42],
    }
    fields = ("code", "pps", "xpps", "mix", "making", "mix_ci", "making_ci")
    assert {k: bbb[k] for k in fields} == {
        "code": "BBB",
        "pps": 1.16,
        "xpps": 1.1,
        "mix": -0.036,
        "making": 0.06,
        "mix_ci": [-0.141, 0.07],
        "making_ci": [-0.383, 0.503],
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


def test_the_public_query_gives_the_intervals(tmp_path: Path) -> None:
    path = tmp_path / "expected-points.json"
    text = render(expected_payload([E2025]))
    assert '"making_ci":[-0.57,0.42]' in text
    path.write_text(text.replace("-0.57,0.42", "-0.57,0.421"), encoding="utf-8", newline="\n")
    rows, problems = public_sql_problems(path)
    assert rows == 2 and len(problems) == 1 and "AAA" in problems[0]


# The intervals (task 117b).


def test_z_is_the_normal_quantile_of_the_level() -> None:
    # Tables of the normal: 1.960 for a central 95 %, 1.645 for 90 % and 2.576 for 99 %.
    assert (z_of(0.95), z_of(0.9), z_of(0.99)) == (1.96, 1.64, 2.58)


def _draws(zones: dict[str, dict[str, int]], replicates: int, seed: int) -> np.ndarray:
    """The parametric bootstrap, drawn the long way: the team's attempts again from its own mix
    of classes, each made at its own rate in the class; one row of counts per draw."""
    rng = np.random.default_rng(seed)
    n = sum(zones[c]["n"] for c in CLASSES)
    attempts = rng.multinomial(n, [zones[c]["n"] / n for c in CLASSES], size=replicates)
    made = rng.binomial(attempts, [zones[c]["made"] / zones[c]["n"] for c in CLASSES])
    return np.concatenate([attempts, made], axis=1)


@pytest.mark.parametrize("code", ["AAA", "BBB"])
def test_the_standard_errors_are_the_parametric_bootstraps(code: str) -> None:
    (block,) = expected_payload([E2025])["seasons"]
    zones = next({c: t[c] for c in CLASSES} for t in block["teams"] if t["code"] == code)
    league = block["league"]
    e = np.array([league[c]["pts"] / league[c]["n"] for c in CLASSES])
    v = np.array([2, 2, 3])
    draws = _draws(zones, 200_000, seed=1)
    n = draws[:, :3].sum(axis=1)
    xpps = (draws[:, :3] * e).sum(axis=1) / n
    making = (draws[:, 3:] * v).sum(axis=1) / n - xpps
    league_pps = {c: float(x) for c, x in zip(CLASSES, e, strict=True)}
    se_mix, se_making = standard_errors(zones, league_pps)
    assert np.std(xpps) == pytest.approx(se_mix, rel=0.01)
    assert np.std(making) == pytest.approx(se_making, rel=0.01)


def _games(team: str, counts: list[tuple[int, int, int, int]]) -> list[Shot]:
    """A team's shots by game: (rim attempts, rim makes, threes, threes made) in each."""
    out = []
    for g, (rim, rim_made, three, three_made) in enumerate(counts):
        out += [
            Shot(
                team, "1", "P", i < rim_made, 2 if i < rim_made else 0, (0, 0), "rim", False, str(g)
            )
            for i in range(rim)
        ]
        out += [
            Shot(
                team, "1", "P", i < three_made, 3 * (i < three_made), (0, 0), "three", False, str(g)
            )
            for i in range(three)
        ]
    return out


PPS = {"rim": 1.2, "mid": 0.8, "three": 1.5}
MEAN = 1.1


def test_identical_games_give_a_bootstrap_over_games_of_no_width() -> None:
    shots = _games("AAA", [(6, 4, 4, 1)] * 30)
    ratios = games_ratios(shots, PPS, MEAN, (0.01, 0.1), 0.95, 1.96, np.random.default_rng(1), 500)
    assert ratios == (0.0, 0.0)


def test_the_bootstrap_over_games_is_its_linearisation() -> None:
    # 40 games of 10 attempts each, rim and threes in proportions that change from game to game.
    # With as many attempts in every game, mix and making are means over games of per-game
    # figures, so the bootstrap's standard deviation is theirs over sqrt(40), and its central
    # 95 % is 2 * 1.96 of it wide; the ratio is that over 2 * 1.96 of the error given.
    rng = np.random.default_rng(5)
    counts = []
    for _ in range(40):
        rim = int(rng.integers(2, 9))
        counts.append(
            (rim, int(rng.integers(0, rim + 1)), 10 - rim, int(rng.integers(0, 11 - rim)))
        )
    mix_g = np.array([(r * 1.2 + t * 1.5) / 10 - MEAN for r, _, t, _ in counts])
    making_g = np.array([(2 * rm + 3 * tm - r * 1.2 - t * 1.5) / 10 for r, rm, t, tm in counts])
    errors = (0.004, 0.03)
    got = games_ratios(
        _games("AAA", counts), PPS, MEAN, errors, 0.95, 1.96, np.random.default_rng(2), 40_000
    )
    assert got[0] == pytest.approx(np.std(mix_g) / np.sqrt(40) / errors[0], rel=0.03)
    assert got[1] == pytest.approx(np.std(making_g) / np.sqrt(40) / errors[1], rel=0.03)


def test_the_bootstrap_over_games_follows_its_seed_and_its_replicates() -> None:
    shots = _games("AAA", [(3 + g % 5, g % 4, 6 - g % 5, g % 3) for g in range(30)])

    def ratios(seed: int, replicates: int) -> tuple[float, float]:
        rng = np.random.default_rng(seed)
        return games_ratios(shots, PPS, MEAN, (0.01, 0.1), 0.95, 1.96, rng, replicates)

    assert ratios(7, 300) == ratios(7, 300)
    assert ratios(7, 300) != ratios(8, 300)
    assert ratios(7, 1) == (0.0, 0.0)  # one draw: a central interval of no width
    # The payload passes its own seed and replicates through, and writes them (AAA's games now
    # differ; its hand-made shots are one more game).
    season = _season("E2025", [*E2025.shots, *shots], ("AAA", "BBB", "CCC"))
    one = expected_payload([season], seed=3, replicates=50)
    assert one == expected_payload([season], seed=3, replicates=50)
    assert one["games_bootstrap"] == {"seed": 3, "replicates": 50}
    assert (
        one["seasons"][0]["games_ratio"]
        != expected_payload([season], seed=4, replicates=50)["seasons"][0]["games_ratio"]
    )
