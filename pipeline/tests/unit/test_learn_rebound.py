"""`tracklab learn rebound` and the SQL of lesson 4's "Reproduce it".

A synthetic match in feet, like the public bundle, with eight rebounds. Five fail one rule of
selection each (a team rebound, a free throw's, no location, a rebound not after the shot's end,
nine players on court); three race:

- R2 (first in frame order): the rebounder stands nearest and still; both rules name him.
- R1: the rebounder is 4 m away running at the target at 5 m/s, another player stands 3 m away;
  the nearest rule names the other, the model names the rebounder.
- R3: the rebounder stands 8 m away, another stands 2 m away; both rules name the other.

So n = 3, the model names the rebounder twice, the nearest rule once, and they agree twice; the
example is R1. Each test that checks a figure also runs one mutation of the function behind it
and asserts the synthetic tells the two apart (a test that cannot fail protects nothing):

- `arrival` without the velocity: the model's hits fall to the nearest rule's;
- `nearest` taking the farthest player: its hits change;
- `read_match` with the velocity reversed (the frames either side swapped): R1 is lost;
- `chance_first` with the standard deviation as the logistic's scale: off the Monte Carlo value;
- `example_race` taking the first race: the example is R2, not R1;
- the SQL without the rule on the shot's end, without the count of players (R5 enters), or
  without the velocity: one of its three counts changes.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pytest

from tracklab.cli import main
from tracklab.learn import rebound as rb

FT = 0.3048
MATCH = int(rb.SQL_MATCH_ID)
SHOOTING, DEFENDING = 100, 200
TEAM = {p: SHOOTING if p <= 5 else DEFENDING for p in range(1, 11)}

# Where everyone stands (m) and how they move (m/s) at the end of each shot; the target is (0, 0).
FAR = {p: ((10.0 + p, 6.0 - p), (0.0, 0.0)) for p in range(1, 11)}


def _scene(**moves: tuple[tuple[float, float], tuple[float, float]]) -> dict[int, Any]:
    out = dict(FAR)
    out.update({int(k[1:]): v for k, v in moves.items()})
    return out


RACES: dict[str, dict[str, Any]] = {
    # frame order: R2, R1, R3; the end of R4's shot is after its rebound.
    "R2": {
        "end": 100,
        "frame": 120,
        "rebounder": 7,
        "players": _scene(p7=((1.0, 0.0), (0.0, 0.0))),
    },
    "R1": {
        "end": 200,
        "frame": 222,
        "rebounder": 3,
        "players": _scene(p3=((-4.0, 0.0), (5.0, 0.0)), p8=((0.0, 3.0), (0.0, 0.0))),
    },
    "R3": {
        "end": 300,
        "frame": 330,
        "rebounder": 2,
        "players": _scene(p2=((8.0, 0.0), (0.0, 0.0)), p9=((0.0, -2.0), (0.0, 0.0))),
    },
    "R4": {"end": 420, "frame": 410, "rebounder": 4, "players": _scene()},
    "R5": {
        "end": 500,
        "frame": 520,
        "rebounder": 5,
        "players": {p: v for p, v in _scene().items() if p != 10},
    },
}
# Rebounds that never reach the tracking: (id, frame, rebounded, rebounderId, shot, location).
OTHERS = [
    ("R6", 600, False, None, "S6", (0.0, 0.0)),  # a team rebound
    ("R7", 700, True, 6, None, (0.0, 0.0)),  # after a free throw: no shot
    ("R8", 800, True, 6, "S8", None),  # no location
]


def _rebounds() -> list[dict[str, Any]]:
    out = [
        {
            "id": rid,
            "frame": r["frame"],
            "rebounded": True,
            "rebounderId": r["rebounder"],
            "shotId": f"S{rid[1:]}",
            "location": [0.0, 0.0],
        }
        for rid, r in RACES.items()
    ]
    out += [
        {
            "id": rid,
            "frame": f,
            "rebounded": ok,
            "rebounderId": who,
            "shotId": shot or "FT1",
            "location": None if loc is None else [loc[0] / FT, loc[1] / FT],
        }
        for rid, f, ok, who, shot, loc in OTHERS
    ]
    return out


def _shots() -> list[dict[str, Any]]:
    shots = [{"id": f"S{rid[1:]}", "endFrame": r["end"]} for rid, r in RACES.items()]
    shots += [{"id": "S6", "endFrame": 590}, {"id": "S8", "endFrame": 790}]
    return [{**s, "offTeamId": SHOOTING, "location_x": -40.0} for s in shots]


def _tracking() -> list[tuple[int, int, float, float]]:
    """(frame, player, x ft, y ft) at the frames either side of each race's end."""
    rows = []
    for r in RACES.values():
        for k in (-1, 0, 1):
            for p, ((x, y), (vx, vy)) in r["players"].items():
                rows.append((r["end"] + k, p, (x + vx * k / 25) / FT, (y + vy * k / 25) / FT))
    return rows


def write_bronze(root: Path) -> None:
    bronze = root / "bronze" / "basketball"
    for table in ("events_rebounds", "events_shots", "tracking_objects", "game_players"):
        (bronze / table).mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE r (id VARCHAR, frame BIGINT, rebounded BOOLEAN, rebounderId BIGINT, "
        "shotId VARCHAR, location_x DOUBLE, location_y DOUBLE)"
    )
    for e in _rebounds():
        loc = e["location"] or [None, None]
        con.execute(
            "INSERT INTO r VALUES (?, ?, ?, ?, ?, ?, ?)",
            [e["id"], e["frame"], e["rebounded"], e["rebounderId"], e["shotId"], *loc],
        )
    con.execute("CREATE TABLE s (id VARCHAR, endFrame BIGINT, offTeamId BIGINT, location_x DOUBLE)")
    for s in _shots():
        con.execute(
            "INSERT INTO s VALUES (?, ?, ?, ?)",
            [s["id"], s["endFrame"], s["offTeamId"], s["location_x"]],
        )
    con.execute(
        "CREATE TABLE o (side VARCHAR, playerId BIGINT, jersey VARCHAR, frameIdx BIGINT, "
        "x DOUBLE, y DOUBLE)"
    )
    for f, p, x, y in _tracking():
        side = "home" if TEAM[p] == SHOOTING else "away"
        con.execute("INSERT INTO o VALUES (?, ?, ?, ?, ?, ?)", [side, p, str(p), f, x, y])
    con.execute("INSERT INTO o VALUES ('ball', NULL, NULL, 200, 0, 0)")  # never a player
    con.execute("CREATE TABLE g (playerId BIGINT, teamId BIGINT)")
    con.executemany("INSERT INTO g VALUES (?, ?)", list(TEAM.items()))
    for name, table in (
        ("events_rebounds", "r"),
        ("events_shots", "s"),
        ("tracking_objects", "o"),
        ("game_players", "g"),
    ):
        path = (bronze / name / f"{MATCH}.parquet").as_posix()
        con.execute(f"COPY {table} TO '{path}' (FORMAT parquet)")


def write_raw(folder: Path) -> None:
    """The match's two public files the SQL reads."""
    folder.mkdir(parents=True, exist_ok=True)
    events = {"rebounds": _rebounds(), "shots": _shots()}
    (folder / f"{MATCH}_dynamic_events.json").write_text(json.dumps(events), encoding="utf-8")
    by_frame: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for f, p, x, y in _tracking():
        side = "homePlayers" if TEAM[p] == SHOOTING else "awayPlayers"
        frame = by_frame.setdefault(f, {"homePlayers": [], "awayPlayers": []})
        frame[side].append({"xyz": [x, y, 0.0], "speed": 0.0, "jersey": str(p), "playerId": p})
    lines = [json.dumps({"frameIdx": f, **p, "ball": {}}) for f, p in sorted(by_frame.items())]
    with gzip.open(folder / f"{MATCH}_tracking_data.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


@pytest.fixture
def bronze(tmp_path: Path) -> Path:
    write_bronze(tmp_path)
    return tmp_path / "bronze" / "basketball"


def _figures(bronze: Path) -> dict[str, Any]:
    return rb.match_figures(*rb.read_match(bronze, MATCH))


# The figures.


def test_the_selection_and_the_two_rules_on_the_synthetic(bronze: Path) -> None:
    funnel, races = rb.read_match(bronze, MATCH)
    assert funnel == rb.Funnel(rebounds=8, by_player=7, field_goal=6, located=5, after_end=4)
    assert [r.rebound_id for r in races] == ["R2", "R1", "R3"]
    fig = rb.match_figures(funnel, races)
    print(f"learn rebound synthetic: {fig}")
    assert (fig["n"], fig["model"], fig["nearest"], fig["same"]) == (3, 2, 1, 2)
    assert fig["by_reaction"][0] == fig["nearest"]  # no reaction: the nearest player
    assert fig["median_wait_s"] == round(22 / 25, 2)
    # R1's velocity, from the frames either side: 5 m/s along x.
    assert races[1].vel[races[1].rebounder] == pytest.approx([5.0, 0.0])


def test_mutation_arrival_without_velocity_is_caught(
    bronze: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def still(
        race: rb.Race, reaction: float = rb.REACTION_S, top_speed: float = rb.TOP_SPEED
    ) -> np.ndarray:  # type: ignore[type-arg]
        rest = race.target - race.pos
        return reaction + np.hypot(rest[:, 0], rest[:, 1]) / top_speed

    monkeypatch.setattr(rb, "arrival", still)
    assert _figures(bronze)["model"] == 1


def test_mutation_nearest_is_caught(bronze: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rb, "nearest", lambda race: int(np.argmax(np.hypot(*(race.target - race.pos).T)))
    )
    assert _figures(bronze)["nearest"] != 1


def test_mutation_velocity_reversed_is_caught(
    bronze: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rb, "FPS", -rb.FPS)  # (next - before) * FPS / 2 now points backwards
    assert rb.match_figures(*rb.read_match(bronze, MATCH))["model"] == 1


def _monte_carlo(times: list[float], spread: float, n: int = 400_000) -> np.ndarray:  # type: ignore[type-arg]
    scale = math.sqrt(3) * spread / math.pi  # a logistic's sd is scale * pi / sqrt(3)
    draws = np.random.default_rng(4).logistic(times, scale, size=(n, len(times)))
    return np.bincount(draws.argmin(axis=1), minlength=len(times)) / n


def test_chance_first_matches_a_monte_carlo_and_its_mutation_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = [0.8, 0.8 + rb.SPREAD_S, 1.3, 2.5]
    got = rb.chance_first(np.array(times))
    print(f"learn rebound chance_first: {got}")
    assert got.sum() == pytest.approx(1.0, abs=1e-6)
    assert rb.chance_first(np.array([1.0, 1.0])) == pytest.approx([0.5, 0.5], abs=1e-9)
    want = _monte_carlo(times, rb.SPREAD_S)
    assert np.abs(got - want).max() < 0.004

    monkeypatch.setattr(math, "pi", math.sqrt(3.0))  # the scale becomes the standard deviation
    assert np.abs(rb.chance_first(np.array(times)) - want).max() > 0.02


def test_the_example_is_the_first_race_where_the_rules_differ(
    bronze: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, races = rb.read_match(bronze, MATCH)
    ex = rb.example_figures(bronze, MATCH, rb.example_race(races))
    assert ex["rebound_id"] == "R1"
    assert ex["model"] == ex["rebounder"] != ex["nearest"]
    assert [p["team"] for p in ex["players"]] == ["shooting"] * 5 + ["defending"] * 5
    assert ex["times"][ex["rebounder"]] == pytest.approx(
        0.8
    )  # 3.5 m in the reaction, 0.5 m at 5 m/s

    monkeypatch.setattr(rb, "example_race", lambda races: rb.rounded(races[0]))
    assert rb.example_figures(bronze, MATCH, rb.example_race(races))["rebound_id"] == "R2"


# The public SQL.


def test_the_sql_gives_the_three_counts(tmp_path: Path) -> None:
    write_raw(tmp_path / "m")
    got = rb.run_sql(rb.read_sql(), tmp_path / "m")
    print(f"learn rebound synthetic SQL: {got}")
    assert got == (3, 2, 1)


SQL_MUTATIONS = {
    "no rule on the shot's end": (" AND r.frame > s.endFrame", ""),
    "no count of players": ("count(*) = 10 AND any_value(players) = 10", "true"),
    "no velocity": ("0.7 * vx", "0 * vx"),
}


@pytest.mark.parametrize("name", SQL_MUTATIONS)
def test_each_sql_mutation_changes_a_count(tmp_path: Path, name: str) -> None:
    write_raw(tmp_path / "m")
    old, new = SQL_MUTATIONS[name]
    sql = rb.read_sql()
    assert old in sql, f"{name}: {old!r} is no longer in rebound.sql"
    assert rb.run_sql(sql.replace(old, new), tmp_path / "m") != (3, 2, 1), name


def test_the_sql_names_its_match_in_its_file_names_and_is_lf() -> None:
    raw = rb.SQL_PATH.read_bytes()
    assert raw.count(rb.SQL_MATCH_ID.encode()) == rb.SQL_NAMES
    assert b"\r" not in raw


# The command, on a data root made in tmp_path.


def _root(tmp_path: Path, *, raw: bool) -> Path:
    root = tmp_path / "data"
    write_bronze(root)
    if raw:
        receipt = root / "raw" / "opendata-basketball"
        receipt.mkdir(parents=True)
        (receipt / "_receipt.json").write_text(json.dumps({"failed": []}), encoding="utf-8")
        write_raw(receipt / "data" / "matches" / str(MATCH))
    return root


def _run(root: Path, out: Path, *extra: str) -> int:
    return main(["learn", "rebound", "--data-dir", str(root), "--out", str(out), *extra])


def test_the_file_is_written_lf_and_then_checks_full(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=True)
    out = tmp_path / "learn" / "rebound.json"
    assert _run(root, out) == 0
    assert b"\r" not in out.read_bytes()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["example"]["rebound_id"] == "R1"
    assert _run(root, out, "--check") == 0
    assert "FULL 1/1" in capsys.readouterr().out


def test_the_check_is_partial_without_the_raw_files_and_fails_on_a_changed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path, raw=False)
    out = tmp_path / "rebound.json"
    assert _run(root, out) == 0
    assert _run(root, out, "--check") == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out
    out.write_text(
        out.read_text(encoding="utf-8").replace('"model": 2,', '"model": 3,'),
        encoding="utf-8",
        newline="\n",
    )
    assert _run(root, out, "--check") == 1
    assert "differs from what bronze gives" in capsys.readouterr().out
