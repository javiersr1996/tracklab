"""euroleague publish on a synthetic download of three games: every figure is worked out by hand.

E2025, game 1 (Alpha AAA v Beta BBB) and game 2 (no shot; Beta is "Beta Renamed" by then);
E2026, game 1 (Alpha New AAA v Gamma CCC). Points are cm from the hoop; with 1.0 m hexagons
(0, 0) is cell (0, 0), (0, 300) is (-1, 2), (87, 750) is (-2, 5) and (-500, 600) is (-5, 4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tracklab.euroleague import aggregates
from tracklab.euroleague.aggregates import hex_cell, run_euroleague_publish, zone_class

_POINTS = {"2FGM": 2, "2FGA": 0, "3FGM": 3, "3FGA": 0, "FTM": 1}


def _row(team: str, pid: str, name: str, action: str, x: int, y: int, zone: str, fb: str = "0"):
    return {
        "NUM_ANOT": 0,
        "TEAM": f"{team}       ",
        "ID_PLAYER": f"{pid}   ",
        "PLAYER": name,
        "ID_ACTION": f"{action}      ",  # the feed pads some of them
        "POINTS": _POINTS[action],
        "COORD_X": x,
        "COORD_Y": y,
        "ZONE": zone,
        "FASTBREAK": fb,
        "MINUTE": 1,
        "UTC": "20251001180000",
    }


def _rows(n: int, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return [_row(*args, **kwargs) for _ in range(n)]


def _game(raw: Path, season: str, code: int, teams: tuple[str, str, str, str], rows: list) -> None:
    (raw / season / "Points").mkdir(parents=True, exist_ok=True)
    (raw / season / "PlaybyPlay").mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(rows, start=1):
        row["NUM_ANOT"] = i
    (raw / season / "Points" / f"{code}.json").write_text(json.dumps({"Rows": rows}), "utf-8")
    a, name_a, b, name_b = teams
    pbp = {"CodeTeamA": f"{a}       ", "TeamA": name_a, "CodeTeamB": f"{b}  ", "TeamB": name_b}
    (raw / season / "PlaybyPlay" / f"{code}.json").write_text(json.dumps(pbp), "utf-8")


def _manifest(raw: Path, season: str, games: list[tuple[int, str]]) -> None:
    files = lambda c: {e: f"{e}/{c}.json" for e in ("Points", "PlaybyPlay", "Boxscore")}  # noqa: E731
    manifest = {
        "season": season,
        "cutoff": max(d for _, d in games),
        "games_played": len(games),
        "games": [{"gamecode": c, "date": d, "files": files(c)} for c, d in games],
    }
    (raw / season / "manifest.json").write_text(json.dumps(manifest), "utf-8")


@pytest.fixture
def data(tmp_path: Path) -> Path:
    raw = tmp_path / "data" / "euroleague" / "raw"
    _game(
        raw,
        "E2025",
        1,
        ("AAA", "Alpha", "BBB", "Beta"),
        [
            *_rows(60, "AAA", "P1", "ONE, PLAYER", "2FGM", 0, 0, "A"),
            *_rows(40, "AAA", "P1", "ONE, PLAYER", "3FGA", 87, 750, "I"),
            *_rows(99, "AAA", "P2", "TWO, PLAYER", "2FGA", 0, 0, "B"),
            *_rows(4, "AAA", "P3", "THREE, PLAYER", "2FGM", 0, 300, "D", fb="1"),
            _row("AAA", "P3", "THREE, PLAYER", "2FGA", -1, -1, " "),  # no location
            _row("AAA", "P3", "THREE, PLAYER", "2FGM", -500, 600, "H"),  # a two tagged H
            _row("AAA", "P3", "THREE, PLAYER", "FTM", -1, -1, " "),
            *_rows(41, "BBB", "Q1", "QUEUE, ONE", "2FGM", 0, 0, "A"),
            _row("BBB", "Q1", "QUEUE, ONE", "2FGA", 0, 300, "E"),
        ],
    )
    _game(raw, "E2025", 2, ("BBB", "Beta Renamed", "AAA", "Alpha"), [])
    _manifest(raw, "E2025", [(2, "2025-10-08"), (1, "2025-10-01")])
    _game(
        raw,
        "E2026",
        1,
        ("CCC", "Gamma", "AAA", "Alpha New"),
        [
            *_rows(5, "AAA", "P1", "ONE, PLAYER", "3FGM", 87, 750, "I", fb="1"),
            *_rows(5, "AAA", "P1", "ONE, PLAYER", "3FGM", 87, 750, "I"),
            *_rows(5, "CCC", "R1", "ARR, ONE", "2FGA", 0, 0, "C"),
        ],
    )
    _manifest(raw, "E2026", [(1, "2026-10-01")])
    return tmp_path / "data"


def _publish(data: Path, out: Path) -> dict[str, Any]:
    assert run_euroleague_publish(data, out) == 0
    folder = out / "euroleague"
    return {
        p.relative_to(folder).as_posix(): json.loads(p.read_text(encoding="utf-8"))
        for p in folder.rglob("*.json")
    }


def test_a_known_shot_falls_in_its_cell() -> None:
    assert hex_cell(0, 0, 100) == (0, 0)
    assert hex_cell(0, 300, 100) == (-1, 2)
    assert hex_cell(87, 750, 100) == (-2, 5)
    assert hex_cell(-500, 600, 100) == (-5, 4)
    assert hex_cell(173, 0, 100) == (1, 0)
    assert hex_cell(87, 750, 75) == (-3, 7)  # the side matters


def test_zone_classes() -> None:
    assert zone_class("2FGM", "A") == "rim"
    assert zone_class("2FGA", "C") == "rim"
    assert zone_class("2FGA", "D") == "mid"
    assert zone_class("2FGM", "G") == "mid"
    assert zone_class("2FGA", "H") == "mid"  # the twos the feed tags H or I
    assert zone_class("3FGA", "G") == "three"  # by ID_ACTION, whatever the zone
    assert zone_class("3FGM", "") == "three"
    assert zone_class("2FGA", "") is None


def test_league(data: Path, tmp_path: Path) -> None:
    files = _publish(data, tmp_path / "out")
    assert sorted(files) == [
        "expected-points.json",
        "league.json",
        "teams/AAA.json",
        "teams/BBB.json",
        "teams/CCC.json",
    ]
    league = files["league.json"]
    assert league["version"] == 1
    assert league["source"] == "EuroLeague (live.euroleague.net)"
    assert league["hex"] == {"side_m": 1.0, "layout": "pointy-top axial", "origin": "hoop", "k": 5}
    e25, e26 = league["seasons"]
    assert (e25["season"], e25["cutoff"], e25["games_played"]) == ("E2025", "2025-10-08", 2)
    # (-1, 2) has 4 + 1 shots and is kept; (-5, 4) has 1 and is not; the shot without a place
    # counts in shots_total only.
    assert e25["cells"] == [[-2, 5, 40, 0, 0], [-1, 2, 5, 4, 8], [0, 0, 200, 101, 202]]
    assert (e25["shots_total"], e25["shots_shown"]) == (247, 245)
    assert e25["zones"] == {
        "rim": {"n": 200, "made": 101, "pts": 202},
        "mid": {"n": 6, "made": 5, "pts": 10},
        "three": {"n": 40, "made": 0, "pts": 0},
    }
    assert e25["unclassified"] == 1
    assert e25["teams"] == [
        {"code": "AAA", "name": "Alpha"},
        {"code": "BBB", "name": "Beta Renamed"},  # the name of its last game
    ]
    assert e26["cells"] == [[-2, 5, 10, 10, 30], [0, 0, 5, 0, 0]]
    assert [t["code"] for t in e26["teams"]] == ["AAA", "CCC"]


def test_team_cells_and_the_difference_with_the_league(data: Path, tmp_path: Path) -> None:
    files = _publish(data, tmp_path / "out")
    aaa = files["teams/AAA.json"]
    assert (aaa["code"], aaa["name"]) == ("AAA", "Alpha New")
    assert aaa["cell_fields"] == ["q", "r", "n", "made", "pts", "diff"]
    e25, e26 = aaa["seasons"]
    assert (e25["season"], e25["cutoff"], e25["games_played"], e25["team_games"]) == (
        "E2025",
        "2025-10-08",
        2,
        2,
    )
    # (-1, 2) has 4 shots of AAA: under k for the team though the league keeps it.
    # (0, 0): 60/159 against the league's 101/200.
    assert e25["cells"] == [[-2, 5, 40, 0, 0, 0.0], [0, 0, 159, 60, 120, -0.128]]
    assert (e25["shots_total"], e25["shots_shown"]) == (205, 199)
    assert files["teams/BBB.json"]["seasons"][0]["cells"] == [[0, 0, 41, 41, 82, 0.495]]
    assert e26["cells"] == [[-2, 5, 10, 10, 30, 0.0]]
    assert [s["season"] for s in files["teams/CCC.json"]["seasons"]] == ["E2026"]


def test_players_from_100_shots(data: Path, tmp_path: Path) -> None:
    aaa = _publish(data, tmp_path / "out")["teams/AAA.json"]
    e25, e26 = aaa["seasons"]
    assert aaa["player_min_shots"] == 100
    assert e25["players"] == [  # TWO, PLAYER has 99 and is left out
        {
            "name": "ONE, PLAYER",
            "shots_total": 100,
            "shots_shown": 100,
            "cells": [[-2, 5, 40, 0, 0], [0, 0, 60, 60, 120]],
        }
    ]
    assert e26["players"] == []


def test_what_has_changed(data: Path, tmp_path: Path) -> None:
    aaa = _publish(data, tmp_path / "out")["teams/AAA.json"]
    assert aaa["changes"] == [
        {
            "season": "E2025",
            "attempts": 205,
            "rim": {"n": 159, "share": 0.776},
            "mid": {"n": 5, "share": 0.024},
            "three": {"n": 40, "share": 0.195},
            "unclassified": 1,
            "fastbreak": {"n": 4, "share": 0.02},
        },
        {
            "season": "E2026",
            "attempts": 10,
            "rim": {"n": 0, "share": 0.0},
            "mid": {"n": 0, "share": 0.0},
            "three": {"n": 10, "share": 1.0},
            "unclassified": 0,
            "fastbreak": {"n": 5, "share": 0.5},
        },
    ]


def test_expected_points_leave_out_what_is_under_k(data: Path, tmp_path: Path) -> None:
    # E2026's league has no mid-range shot, and BBB took one in E2025: only AAA's E2025 is in.
    doc = _publish(data, tmp_path / "out")["expected-points.json"]
    assert [s["season"] for s in doc["seasons"]] == ["E2025"]
    assert [t["code"] for t in doc["seasons"][0]["teams"]] == ["AAA"]
    assert doc["seasons"][0]["teams_left_out"] == 1


def test_no_field_of_a_shot_is_written(data: Path, tmp_path: Path) -> None:
    _publish(data, tmp_path / "out")
    for path in (tmp_path / "out" / "euroleague").rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        for key in ("NUM_ANOT", "UTC", "COORD", "MINUTE", "ID_PLAYER", "2025100118"):
            assert key not in text, (path.name, key)


def test_check_and_stale_files(
    data: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    stale = out / "euroleague" / "teams" / "ZZZ.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", "utf-8")
    _publish(data, out)
    assert not stale.exists()
    assert b"\r" not in (out / "euroleague" / "league.json").read_bytes()
    assert run_euroleague_publish(data, out, check=True) == 0
    assert "FULL 5/5" in capsys.readouterr().out
    (out / "euroleague" / "teams" / "BBB.json").write_text("{}\n", "utf-8")
    assert run_euroleague_publish(data, out, check=True) == 1
    assert run_euroleague_publish(tmp_path / "nothing", out, check=True) == 0
    assert "PARTIAL" in capsys.readouterr().out


def test_over_the_cap_writes_nothing(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(aggregates, "TEAM_CAP_BYTES", 500)
    assert run_euroleague_publish(data, tmp_path / "out") == 1
    assert not (tmp_path / "out").exists()
