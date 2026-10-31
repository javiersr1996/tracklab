"""The guard of the EuroLeague JSON (P14, task 115): aggregates only, read from the published files.

The data has no open license (docs/superpowers/specs/2026-10-31-euroleague-design.md), so every
file under `web/public/data/euroleague/` must hold counts of hexagons and nothing that rebuilds a
shot. This reads those files as the browser gets them and never calls the code that writes them:
its constants (k, the byte caps of docs/euroleague-probe.md, the keys of the raw feed) are its
own. The folder is in git, so it runs everywhere, CI included, and fails if the folder is gone.
The second half mutates a copy of the real files and sees the guard fail on each mutation.
"""

from __future__ import annotations

import json
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
    if size > cap:
        out.append(f"{name}: {size} B over its cap of {cap} B")
    k = doc.get("hex", {}).get("k")
    if not _is_int(k) or k < K_MIN:
        out.append(f"{name}: k is {k!r}, under {K_MIN}")
        k = K_MIN
    widths = set()
    for key in ("cell_fields", "player_cell_fields"):
        fields = doc.get(key)
        if fields is None and key == "player_cell_fields":
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
            if "cells" in value and isinstance(value["cells"], list):
                shown = sum(c[2] for c in value["cells"] if isinstance(c, list) and len(c) > 2)
                if value.get("shots_shown") != shown:
                    out.append(f"{name}{where}: shots_shown is not the sum of its cells")
                if not _is_int(value.get("shots_total")) or value["shots_total"] < shown:
                    out.append(f"{name}{where}: shots_total under shots_shown")
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
    if not (folder / "league.json").is_file() or not list(folder.glob("teams/*.json")):
        return [f"{folder}: league.json or teams/*.json missing"]
    out: list[str] = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        name = path.relative_to(folder).as_posix()
        if name != "league.json" and not _TEAM_FILE.match(name):
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


def test_a_stray_file_fails_the_guard(copy: Path) -> None:
    (copy / "shots.json").write_text("{}\n", encoding="utf-8")
    assert any("not a file of the atlas" in p for p in problems(copy))


def test_a_league_over_its_cap_fails_the_guard(copy: Path) -> None:
    _edit(copy / "league.json", lambda d: d.update(pad="x" * LEAGUE_CAP_PER_SEASON * 2))
    assert any("league.json" in p and "over its cap" in p for p in problems(copy))
