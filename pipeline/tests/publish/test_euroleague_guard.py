"""The guard of the EuroLeague JSON (P14, task 115): aggregates only, read from the published files.

The data has no open license (docs/superpowers/specs/2026-10-31-euroleague-design.md), so every
file under `web/public/data/euroleague/` must hold counts of hexagons (and, for lesson 12, of zone
classes) and nothing that rebuilds a shot. This reads those files as the browser gets them and
never calls the code that writes them: its constants (k, the byte caps of docs/euroleague-probe.md,
the keys of the raw feed) are its own. The folder is in git, so it runs everywhere, CI included,
and fails if the folder is gone. The second half mutates a copy of the real files and sees the
guard fail on each mutation.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

PUBLIC = Path(__file__).resolve().parents[3] / "web" / "public"
FOLDER = PUBLIC / "data" / "euroleague"
K_MIN = 5  # the spec: never under 5
TEAM_CAP = 24_000
LEAGUE_CAP_PER_SEASON = 4_000
EXPECTED = "expected-points.json"  # lesson 12 (task 117): counts by zone class, no hexagon
EXPECTED_CAP = 16_000
INTERVALS = ("mix_ci", "making_ci")  # task 117b: the only lists of numbers it may hold, two each
RUNS = "runs.json"  # task 118: the biggest run and comeback, a ranking and a summary by team
RUNS_CAP = 16_000
RUNS_ROWS = 25  # a ranking is 10 and whoever ties with the 10th; a row per game would be 400
RUNS_KEYS = {
    "run": {"team", "opp", "date", "size", "from", "to"},
    "comeback": {"team", "opp", "date", "deficit", "at", "final"},
    "team": {
        "code",
        "games",
        "best_run",
        "runs_n",
        "comeback_for",
        "comeback_against",
        "wins_from_n",
    },
}
SOURCE = "EuroLeague (live.euroleague.net)"
# Every key of a row of Points, PlaybyPlay and Boxscore, as the feed spells it.
RAW_KEYS = {
    *("NUM_ANOT", "TEAM", "ID_PLAYER", "PLAYER", "ID_ACTION", "ACTION", "POINTS", "COORD_X"),
    *("COORD_Y", "ZONE", "FASTBREAK", "SECOND_CHANCE", "POINTS_OFF_TURNOVER", "MINUTE"),
    *("CONSOLE", "POINTS_A", "POINTS_B", "UTC", "CODETEAM", "COMMENT", "DORSAL", "MARKERTIME"),
    *("NUMBEROFPLAY", "PLAYER_ID", "PLAYINFO", "PLAYTYPE", "TYPE", "Rows", "PlayersStats"),
    *("FirstQuarter", "SecondQuarter", "ThirdQuarter", "ForthQuarter", "ExtraTime"),
}
# Keys that place or time one event, in any case: a row carrying them is a shot.
ROW_KEYS = {
    *("num_anot", "utc", "coord_x", "coord_y", "minute", "console", "markertime"),
    *("numberofplay", "playtype", "points_a", "points_b", "id_player", "player_id"),
    *("id_action", "dorsal", "playinfo", "x", "y"),
}
_LONG_DIGITS = re.compile(r"\d{14,}")  # a UTC of the feed is 14 digits
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TEAM_FILE = re.compile(r"^teams/[A-Z0-9]{2,4}\.json$")


def _walk(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _walk(item, f"{path}[{i}]")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_num(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _interval_problems(doc: dict[str, Any]) -> list[str]:
    """Lesson 12's intervals (task 117b): a level between 0 and 1 and a z; every team with the two
    bounds of each interval around its figure; nothing else."""
    out = []
    level, z = doc.get("level"), doc.get("z")
    if not (_is_num(level) and 0 < level < 1 and _is_num(z) and z > 0):
        out.append(f"{EXPECTED}: level {level!r} or z {z!r} is not an interval's")
    for block in doc.get("seasons", []):
        for team in block.get("teams", []):
            for field in ("mix", "making"):
                ci = team.get(f"{field}_ci")
                ok = isinstance(ci, list) and len(ci) == 2 and all(map(_is_num, ci))
                if not (ok and ci[0] <= team.get(field, math.nan) <= ci[1]):
                    out.append(
                        f"{EXPECTED} {block.get('season')} {team.get('code')}: "
                        f"{field}_ci {ci!r} is not an interval around {field}"
                    )
    return out


def _pair(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(map(_is_int, value))


def _runs_problems(doc: dict[str, Any]) -> list[str]:
    """runs.json (task 118): only the two rankings and the summary by team, the keys of the
    schema and nothing a play could hide in."""
    out = []
    for key in ("top", "run_min", "deficit_min"):
        if not (_is_int(doc.get(key)) and doc[key] > 0):
            out.append(f"{RUNS}: {key} is {doc.get(key)!r}")
    for block in doc.get("seasons", []):
        label = f"{RUNS} {block.get('season')}"
        read, played = block.get("games_read"), block.get("games_played")
        if not (_is_int(read) and _is_int(played) and 0 < read <= played):
            out.append(f"{label}: games_read {read!r} is not within games_played {played!r}")
        for kind, field in (("run", "runs"), ("comeback", "comebacks")):
            rows = block.get(field)
            if not isinstance(rows, list) or not 0 < len(rows) <= RUNS_ROWS:
                out.append(f"{label}: {field} is not a ranking of at most {RUNS_ROWS}")
                continue
            sizes = []
            for i, row in enumerate(rows):
                where = f"{label} {field}[{i}]"
                if not isinstance(row, dict) or set(row) != RUNS_KEYS[kind]:
                    out.append(f"{where}: keys are not {sorted(RUNS_KEYS[kind])}")
                    continue
                size_key = "size" if kind == "run" else "deficit"
                begin, end = ("from", "to") if kind == "run" else ("at", "final")
                if not (_is_int(row[size_key]) and row[size_key] > 0):
                    out.append(f"{where}: no {size_key}")
                    continue
                sizes.append(row[size_key])
                if not (_pair(row[begin]) and _pair(row[end])) or min(row[begin] + row[end]) < 0:
                    out.append(f"{where}: {begin} and {end} are not two scores")
                elif kind == "run" and not (
                    row["to"][0] - row["from"][0] == row["size"] and row["to"][1] == row["from"][1]
                ):
                    out.append(f"{where}: the run is not size points in a row")
                elif kind == "comeback" and not (
                    row["final"][0] > row["final"][1]
                    and row["at"][1] - row["at"][0] == row["deficit"]
                ):
                    out.append(f"{where}: not a winner that trailed by the deficit")
                if not (_DATE.match(str(row["date"])) and row["team"] != row["opp"]):
                    out.append(f"{where}: date or teams")
            if sizes != sorted(sizes, reverse=True):
                out.append(f"{label}: {field} is not in order")
        teams = block.get("teams")
        if not isinstance(teams, list) or not 0 < len(teams) <= 30:
            out.append(f"{label}: teams is not a list of at most 30")
            continue
        for team in teams:
            ok = isinstance(team, dict) and set(team) == RUNS_KEYS["team"]
            ok = ok and re.match(r"^[A-Z0-9]{2,4}$", str(team.get("code"))) is not None
            ok = ok and all(_is_int(v) and v >= 0 for k, v in team.items() if k != "code")
            ok = ok and team["runs_n"] <= team["games"] >= team["wins_from_n"]
            if not ok:
                who = team.get("code") if isinstance(team, dict) else team
                out.append(f"{label} {who}: not a team")
    return out


def _payload_problems(name: str, doc: Any, size: int) -> list[str]:
    out: list[str] = []
    if not isinstance(doc, dict):
        return [f"{name}: not an object"]
    if not _is_int(doc.get("version")):
        out.append(f"{name}: no version")
    if doc.get("source") != SOURCE:
        out.append(f"{name}: the source is not {SOURCE!r}")
    seasons = doc.get("seasons")
    if not isinstance(seasons, list) or not seasons:
        return [*out, f"{name}: no seasons"]
    for block in seasons:
        label = f"{name} {block.get('season')}"
        if not isinstance(block.get("season"), str):
            out.append(f"{label}: no season")
        if not isinstance(block.get("cutoff"), str) or not _DATE.match(block["cutoff"]):
            out.append(f"{label}: no cutoff")
        if not _is_int(block.get("games_played")) or block["games_played"] <= 0:
            out.append(f"{label}: no games_played")
    cap = LEAGUE_CAP_PER_SEASON * len(seasons) if name == "league.json" else TEAM_CAP
    cap = EXPECTED_CAP if name == EXPECTED else RUNS_CAP if name == RUNS else cap
    if size > cap:
        out.append(f"{name}: {size} B over its cap of {cap} B")
    if name == RUNS:
        out.extend(_runs_problems(doc))
        for where, value in _walk(doc):
            if isinstance(value, dict):
                out.extend(
                    f"{name}{where}: raw key {key!r}"
                    for key in value
                    if key in RAW_KEYS or key.lower() in ROW_KEYS
                )
        return out
    k: Any = doc.get("k") if name == EXPECTED else doc.get("hex", {}).get("k")
    if not _is_int(k) or k < K_MIN:
        out.append(f"{name}: k is {k!r}, under {K_MIN}")
        k = K_MIN
    if name == EXPECTED:
        out.extend(_interval_problems(doc))
    widths = set()
    for key in ("cell_fields", "player_cell_fields"):
        fields = doc.get(key)
        if fields is None and (key == "player_cell_fields" or name == EXPECTED):
            continue
        if not isinstance(fields, list) or fields[:3] != ["q", "r", "n"]:
            out.append(f"{name}: {key} does not start with q, r, n")
            continue
        widths.add(len(fields))
    for where, value in _walk(doc):
        if isinstance(value, dict):
            for key in value:
                if key in RAW_KEYS or key.lower() in ROW_KEYS:
                    out.append(f"{name}{where}: raw key {key!r}")
            if "n" in value and "made" in value:  # a count of shots: a zone class of a season
                n, made = value["n"], value["made"]
                if not (_is_int(n) and _is_int(made) and 0 <= made <= n):
                    out.append(f"{name}{where}: not a count of shots")
                elif n < max(k, K_MIN):
                    out.append(f"{name}{where}: n={n}, under k={max(k, K_MIN)}")
            if "cells" in value and isinstance(value["cells"], list):
                shown = sum(c[2] for c in value["cells"] if isinstance(c, list) and len(c) > 2)
                if value.get("shots_shown") != shown:
                    out.append(f"{name}{where}: shots_shown is not the sum of its cells")
                if not _is_int(value.get("shots_total")) or value["shots_total"] < shown:
                    out.append(f"{name}{where}: shots_total under shots_shown")
        if name == EXPECTED and isinstance(value, list) and value and all(map(_is_num, value)):
            if not (where.endswith(INTERVALS) and len(value) == 2):
                out.append(f"{name}{where}: a list of values outside an interval")
        if isinstance(value, list) and any(isinstance(item, list) for item in value):
            if not where.endswith(".cells"):
                out.append(f"{name}{where}: a list of rows outside cells")
                continue
            for i, cell in enumerate(value):
                ok = isinstance(cell, list) and len(cell) in widths
                ok = ok and all(_is_int(v) for v in cell[:5]) and 0 <= cell[3] <= cell[2]
                if not ok:
                    out.append(f"{name}{where}[{i}]: not a cell")
                elif cell[2] < max(k, K_MIN):
                    out.append(f"{name}{where}[{i}]: n={cell[2]}, under k={max(k, K_MIN)}")
    return out


def problems(folder: Path) -> list[str]:
    """What is wrong with the published folder; an empty list means the guard passes."""
    if not all((folder / f).is_file() for f in ("league.json", EXPECTED, RUNS)) or not list(
        folder.glob("teams/*.json")
    ):
        return [f"{folder}: league.json, {EXPECTED}, {RUNS} or teams/*.json missing"]
    out: list[str] = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        name = path.relative_to(folder).as_posix()
        if name not in ("league.json", EXPECTED, RUNS) and not _TEAM_FILE.match(name):
            out.append(f"{name}: not a file of the atlas")
            continue
        data = path.read_bytes()
        text = data.decode("utf-8")
        if "\r" in text:
            out.append(f"{name}: CR line ends")
        for run in _LONG_DIGITS.findall(text):
            out.append(f"{name}: {len(run)} digits in a row, the shape of a UTC")
        out.extend(_payload_problems(name, json.loads(text), len(data)))
    return out


def test_the_published_euroleague_json_holds_aggregates_only() -> None:
    assert problems(FOLDER) == []


def test_euroleague_is_not_a_download() -> None:
    assert "euroleague" not in (PUBLIC / "data" / "index.json").read_text(encoding="utf-8").lower()
    outside = [
        rel
        for p in PUBLIC.rglob("*")
        if "euroleague" in (rel := p.relative_to(PUBLIC).as_posix().lower())
        and not rel.startswith("data/euroleague")
    ]
    assert outside == []


# The guard of the guard: one mutation per rule, on a copy of the real files.


def _team(folder: Path) -> Path:
    return sorted(folder.glob("teams/*.json"))[0]


def _edit(path: Path, change: Callable[[dict[str, Any]], None]) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")


def _one_shot_cell(doc: dict[str, Any]) -> None:
    block = doc["seasons"][0]
    block["cells"].append([30, 30, 1, 1, 2, 0.5])
    block["shots_shown"] += 1
    block["shots_total"] += 1


def _shot_row(doc: dict[str, Any]) -> None:
    doc["seasons"][0]["players"][0]["shots"] = [[-12, -6, 1]]


MUTATIONS: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "a cell of one shot": (_one_shot_cell, "n=1, under k=5"),
    "k lowered to 1": (lambda d: d["hex"].update(k=1), "k is 1"),
    "a NUM_ANOT key": (lambda d: d["seasons"][0].update(NUM_ANOT=4), "raw key 'NUM_ANOT'"),
    "an x and a y": (lambda d: d["seasons"][0]["players"][0].update(x=1, y=2), "raw key 'x'"),
    "rows outside cells": (_shot_row, "a list of rows outside cells"),
    "a UTC": (lambda d: d.update(name="20250930174549"), "the shape of a UTC"),
    "no cutoff": (lambda d: d["seasons"][0].pop("cutoff"), "no cutoff"),
    "no games_played": (lambda d: d["seasons"][-1].pop("games_played"), "no games_played"),
    "shown counts a dropped cell": (
        lambda d: d["seasons"][0].update(shots_shown=d["seasons"][0]["shots_shown"] + 3),
        "shots_shown is not the sum",
    ),
    "over the cap": (lambda d: d.update(name="x" * TEAM_CAP), "over its cap"),
}


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    shutil.copytree(FOLDER, tmp_path / "euroleague")
    return tmp_path / "euroleague"


def test_the_copy_passes(copy: Path) -> None:
    assert problems(copy) == []


@pytest.mark.parametrize("mutation", list(MUTATIONS))
def test_each_mutation_fails_the_guard(copy: Path, mutation: str) -> None:
    change, expected = MUTATIONS[mutation]
    _edit(_team(copy), change)
    found = problems(copy)
    assert any(expected in p for p in found), found


def _expected_shot_row(doc: dict[str, Any]) -> None:
    doc["seasons"][0]["teams"][0]["shots"] = [[-12, -6, 1]]


def _expected_under_k(doc: dict[str, Any]) -> None:
    doc["seasons"][-1]["teams"][0]["mid"].update(n=4, made=1, pts=2)


EXPECTED_MUTATIONS: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "a row of a shot": (_expected_shot_row, "a list of rows outside cells"),
    "a zone class of four shots": (_expected_under_k, "n=4, under k=5"),
    "a COORD_X key": (lambda d: d["seasons"][0]["teams"][0].update(COORD_X=120), "raw key"),
    "k lowered to 1": (lambda d: d.update(k=1), "k is 1"),
    "more makes than shots": (
        lambda d: d["seasons"][0]["league"]["rim"].update(made=10**6),
        "not a count of shots",
    ),
    "no cutoff": (lambda d: d["seasons"][0].pop("cutoff"), "no cutoff"),
    "over the cap": (lambda d: d.update(pad="x" * EXPECTED_CAP), "over its cap"),
    # Task 117b: the intervals.
    "a team without its making interval": (
        lambda d: d["seasons"][-1]["teams"][0].pop("making_ci"),
        "making_ci None is not an interval",
    ),
    "an interval upside down": (
        lambda d: d["seasons"][0]["teams"][0]["mix_ci"].reverse(),
        "is not an interval around mix",
    ),
    "an interval of three bounds": (
        lambda d: d["seasons"][0]["teams"][0]["making_ci"].append(0.5),
        "a list of values outside an interval",
    ),
    "a value per game": (
        lambda d: d["seasons"][0]["teams"][0].update(making_by_game=[0.12, -0.3, 0.05]),
        "a list of values outside an interval",
    ),
    "no level": (lambda d: d.pop("level"), "is not an interval's"),
}


@pytest.mark.parametrize("mutation", list(EXPECTED_MUTATIONS))
def test_each_mutation_of_the_expected_points_fails_the_guard(copy: Path, mutation: str) -> None:
    change, expected = EXPECTED_MUTATIONS[mutation]
    _edit(copy / EXPECTED, change)
    found = problems(copy)
    assert any(EXPECTED in p and expected in p for p in found), found


def _run_play_rows(doc: dict[str, Any]) -> None:
    doc["seasons"][0]["runs"][0]["plays"] = [[1, 2], [3, 4]]


def _row_per_game(doc: dict[str, Any]) -> None:
    block = doc["seasons"][0]
    block["runs"] = [dict(block["runs"][-1]) for _ in range(100)]


def _run_wrong_size(doc: dict[str, Any]) -> None:
    doc["seasons"][0]["runs"][0]["size"] += 1


def _runs_out_of_order(doc: dict[str, Any]) -> None:
    doc["seasons"][0]["comebacks"].reverse()


RUNS_MUTATIONS: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "a list of plays in a row": (_run_play_rows, "keys are not"),
    "an event id": (lambda d: d["seasons"][0]["runs"][0].update(NUM_ANOT=412), "keys are not"),
    "a NUMBEROFPLAY key": (lambda d: d["seasons"][0].update(NUMBEROFPLAY=3), "raw key"),
    "a game id": (lambda d: d["seasons"][0]["comebacks"][0].update(gamecode=7), "keys are not"),
    "a row per game": (_row_per_game, "not a ranking of at most"),
    "a run that is not its size": (_run_wrong_size, "not size points in a row"),
    "a ranking out of order": (_runs_out_of_order, "is not in order"),
    "a clock in a row": (
        lambda d: d["seasons"][0]["runs"][0].update(MARKERTIME="07:17"),
        "keys are not",
    ),
    "a UTC": (lambda d: d.update(name="20250930174549"), "the shape of a UTC"),
    "no cutoff": (lambda d: d["seasons"][0].pop("cutoff"), "no cutoff"),
    "a team with a key more": (
        lambda d: d["seasons"][0]["teams"][0].update(plays=3),
        "not a team",
    ),
    "a win from behind over the games": (
        lambda d: d["seasons"][0]["teams"][0].update(wins_from_n=10**4),
        "not a team",
    ),
    "no run_min": (lambda d: d.pop("run_min"), "run_min is None"),
    "over the cap": (lambda d: d.update(pad="x" * RUNS_CAP), "over its cap"),
}


@pytest.mark.parametrize("mutation", list(RUNS_MUTATIONS))
def test_each_mutation_of_the_runs_fails_the_guard(copy: Path, mutation: str) -> None:
    change, expected = RUNS_MUTATIONS[mutation]
    _edit(copy / RUNS, change)
    found = problems(copy)
    assert any(RUNS in p and expected in p for p in found), found


def test_a_missing_runs_file_fails_the_guard(copy: Path) -> None:
    (copy / RUNS).unlink()
    assert any("missing" in p for p in problems(copy))


def test_a_missing_expected_points_fails_the_guard(copy: Path) -> None:
    (copy / EXPECTED).unlink()
    assert any("missing" in p for p in problems(copy))


def test_a_stray_file_fails_the_guard(copy: Path) -> None:
    (copy / "shots.json").write_text("{}\n", encoding="utf-8")
    assert any("not a file of the atlas" in p for p in problems(copy))


def test_a_league_over_its_cap_fails_the_guard(copy: Path) -> None:
    _edit(copy / "league.json", lambda d: d.update(pad="x" * LEAGUE_CAP_PER_SEASON * 2))
    assert any("league.json" in p and "over its cap" in p for p in problems(copy))
