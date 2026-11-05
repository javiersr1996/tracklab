"""``tracklab euroleague publish``: the aggregates of CP14a, never a shot.

Reads what ``euroleague fetch`` left under ``<data root>/euroleague/raw`` and writes
``<out>/euroleague/league.json`` and ``<out>/euroleague/teams/<CODE>.json``. The data has no
open license (docs/superpowers/specs/2026-10-31-euroleague-design.md), so only hexagon counts
leave: a cell with fewer than ``K`` shots is dropped, and no event id, clock, minute or shot
coordinate is ever written. The figures come from the probe (docs/euroleague-probe.md):

- hexagons of 1.0 m side, pointy top, axial ``(q, r)`` with the origin at the hoop, ``K`` = 5;
- ``COORD_X``/``COORD_Y`` are cm from the hoop; a field goal with a blank ``ZONE`` has no
  location (it comes as -1/-1) and is counted in ``shots_total`` but sits in no cell;
- zone class: ``three`` by ``ID_ACTION``; a two in A, B or C is ``rim``; any other two with a
  zone is ``mid`` (D to G, and the few twos the feed tags H or I); a two with no zone is
  ``unclassified``;
- players with ``PLAYER_MIN_SHOTS`` field goals or more for the team in the season.

``expected-points.json`` (P14b, task 117) is lesson 12's file: by season, the league's and each
team's attempts, makes and points in each zone class, and the points per shot they give.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = 1
SOURCE = "EuroLeague (live.euroleague.net)"
SEASONS = ("E2025", "E2026")
HEX_SIDE_M = 1.0
K = 5
PLAYER_MIN_SHOTS = 100
TEAM_CAP_BYTES = 24_000
LEAGUE_CAP_BYTES_PER_SEASON = 4_000
EXPECTED_FILE = "expected-points.json"
EXPECTED_CAP_BYTES = 16_000
RIM_ZONES = frozenset("ABC")
CLASSES = ("rim", "mid", "three")
FIELD_GOALS = {"2FGM": True, "2FGA": False, "3FGM": True, "3FGA": False}  # action -> made
QUARTERS = ("FirstQuarter", "SecondQuarter", "ThirdQuarter", "ForthQuarter", "ExtraTime")
CELL_FIELDS = ["q", "r", "n", "made", "pts"]
TEAM_CELL_FIELDS = [*CELL_FIELDS, "diff"]
_SQRT3 = math.sqrt(3.0)


class EuroleaguePublishError(RuntimeError):
    pass


def hex_cell(x_cm: float, y_cm: float, side_cm: float) -> tuple[int, int]:
    """The axial (q, r) of the pointy-top hexagon of side ``side_cm`` holding (x, y).

    Cube rounding with floor(v + 0.5), not Python's round-half-even, so a tie always goes the
    same way."""
    qf = (_SQRT3 / 3.0 * x_cm - y_cm / 3.0) / side_cm
    rf = (2.0 / 3.0 * y_cm) / side_cm
    sf = -qf - rf
    q, r, s = (math.floor(v + 0.5) for v in (qf, rf, sf))
    dq, dr, ds = abs(q - qf), abs(r - rf), abs(s - sf)
    if dq > dr and dq > ds:
        q = -r - s
    elif dr > ds:
        r = -q - s
    return q, r


def zone_class(action: str, zone: str) -> str | None:
    if action.startswith("3"):
        return "three"
    if not zone:
        return None
    return "rim" if zone in RIM_ZONES else "mid"


@dataclass(frozen=True)
class Shot:
    team: str
    player_id: str
    player: str
    made: bool
    pts: int
    cell: tuple[int, int] | None  # None: the feed gave no location
    zone_class: str | None
    fastbreak: bool


@dataclass
class Season:
    season: str
    cutoff: str
    games_played: int
    shots: list[Shot]
    names: dict[str, str]  # team code -> the name of its last game in the season
    team_games: Counter[str]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _shot(row: dict[str, Any], side_cm: float) -> Shot | None:
    action = str(row["ID_ACTION"]).strip()
    if action == "FTM":
        return None
    if action not in FIELD_GOALS:
        raise EuroleaguePublishError(f"unknown ID_ACTION {action!r}")
    made = FIELD_GOALS[action]
    zone = str(row["ZONE"]).strip()
    cell = hex_cell(float(row["COORD_X"]), float(row["COORD_Y"]), side_cm) if zone else None
    return Shot(
        team=str(row["TEAM"]).strip(),
        player_id=str(row["ID_PLAYER"]).strip(),
        player=str(row["PLAYER"]).strip(),
        made=made,
        pts=int(row["POINTS"]),
        cell=cell,
        zone_class=zone_class(action, zone),
        fastbreak=str(row["FASTBREAK"]).strip() == "1",
    )


def load_season(raw: Path, season: str, side_cm: float = HEX_SIDE_M * 100.0) -> Season:
    """Every field goal of the season's manifest, with the two teams of each game."""
    manifest_path = raw / season / "manifest.json"
    if not manifest_path.is_file():
        raise EuroleaguePublishError(f"{season}: no manifest at {manifest_path}")
    manifest = _read_json(manifest_path)
    games = sorted(manifest["games"], key=lambda g: (g["date"], g["gamecode"]))
    if len(games) != manifest["games_played"] or not games:
        raise EuroleaguePublishError(f"{season}: the manifest lists {len(games)} games")
    shots: list[Shot] = []
    names: dict[str, str] = {}
    team_games: Counter[str] = Counter()
    for game in games:
        pbp = _read_json(raw / season / game["files"]["PlaybyPlay"])
        playing = set()
        for side in ("A", "B"):
            code = str(pbp[f"CodeTeam{side}"]).strip()
            names[code] = str(pbp[f"Team{side}"]).strip()
            team_games[code] += 1
            playing.add(code)
        for row in _read_json(raw / season / game["files"]["Points"])["Rows"] or []:
            shot = _shot(row, side_cm)
            if shot is None:
                continue
            if shot.team not in playing:
                raise EuroleaguePublishError(
                    f"{season} game {game['gamecode']}: shot by {shot.team}, not playing"
                )
            shots.append(shot)
    return Season(season, str(manifest["cutoff"]), len(games), shots, names, team_games)


def _tally(shots: Iterable[Shot]) -> dict[tuple[int, int], list[int]]:
    cells: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    for shot in shots:
        if shot.cell is None:
            continue
        c = cells[shot.cell]
        c[0] += 1
        c[1] += int(shot.made)
        c[2] += shot.pts
    return cells


def _kept(cells: dict[tuple[int, int], list[int]], k: int) -> list[list[int]]:
    """The cells with k shots or more, as [q, r, n, made, pts], sorted by (q, r)."""
    return [[q, r, *v] for (q, r), v in sorted(cells.items()) if v[0] >= k]


def _r3(value: float) -> float:
    return round(value, 3) or 0.0  # never -0.0


def _hex_block(k: int, side_m: float) -> dict[str, Any]:
    return {"side_m": side_m, "layout": "pointy-top axial", "origin": "hoop", "k": k}


def _season_head(s: Season) -> dict[str, Any]:
    return {"season": s.season, "cutoff": s.cutoff, "games_played": s.games_played}


def zone_totals(shots: Iterable[Shot]) -> tuple[dict[str, dict[str, int]], int]:
    """n, made and pts by zone class, and how many shots had no class."""
    totals = {c: {"n": 0, "made": 0, "pts": 0} for c in CLASSES}
    unclassified = 0
    for shot in shots:
        if shot.zone_class is None:
            unclassified += 1
            continue
        t = totals[shot.zone_class]
        t["n"] += 1
        t["made"] += int(shot.made)
        t["pts"] += shot.pts
    return totals, unclassified


def changes(season: str, shots: list[Shot]) -> dict[str, Any]:
    """The attempt mix by zone class and the fast-break part, for "what has changed"."""
    attempts = len(shots)
    totals, unclassified = zone_totals(shots)
    fastbreak = sum(s.fastbreak for s in shots)
    return {
        "season": season,
        "attempts": attempts,
        **{c: {"n": totals[c]["n"], "share": _r3(totals[c]["n"] / attempts)} for c in CLASSES},
        "unclassified": unclassified,
        "fastbreak": {"n": fastbreak, "share": _r3(fastbreak / attempts)},
    }


def league_payload(seasons: list[Season], k: int = K, side_m: float = HEX_SIDE_M) -> dict[str, Any]:
    blocks = []
    for s in seasons:
        cells = _kept(_tally(s.shots), k)
        totals, unclassified = zone_totals(s.shots)
        blocks.append(
            {
                **_season_head(s),
                "shots_total": len(s.shots),
                "shots_shown": sum(c[2] for c in cells),
                "cells": cells,
                "zones": totals,
                "unclassified": unclassified,
                "teams": [{"code": c, "name": s.names[c]} for c in sorted(s.names)],
            }
        )
    return {
        "version": VERSION,
        "source": SOURCE,
        "hex": _hex_block(k, side_m),
        "cell_fields": CELL_FIELDS,
        "seasons": blocks,
    }


def _players(shots: list[Shot], k: int, min_shots: int) -> list[dict[str, Any]]:
    by_player: dict[str, list[Shot]] = defaultdict(list)
    for shot in shots:
        by_player[shot.player_id].append(shot)
    players = []
    for own in by_player.values():
        if len(own) < min_shots:
            continue
        cells = _kept(_tally(own), k)
        name = Counter(s.player for s in own).most_common(1)[0][0]
        players.append(
            {
                "name": name,
                "shots_total": len(own),
                "shots_shown": sum(c[2] for c in cells),
                "cells": cells,
            }
        )
    return sorted(players, key=lambda p: (-p["shots_total"], p["name"]))


def team_payloads(
    seasons: list[Season],
    k: int = K,
    side_m: float = HEX_SIDE_M,
    min_shots: int = PLAYER_MIN_SHOTS,
) -> dict[str, dict[str, Any]]:
    """One payload per team code that played in any of the seasons."""
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mixes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    names: dict[str, str] = {}
    for s in seasons:
        league = _tally(s.shots)
        by_team: dict[str, list[Shot]] = defaultdict(list)
        for shot in s.shots:
            by_team[shot.team].append(shot)
        for code in sorted(s.names):
            own = by_team.get(code, [])
            if not own:
                raise EuroleaguePublishError(f"{s.season}: {code} played and took no shot")
            cells = []
            for q, r, n, made, pts in _kept(_tally(own), k):
                ln, lmade, _ = league[(q, r)]
                cells.append([q, r, n, made, pts, _r3(made / n - lmade / ln)])
            blocks[code].append(
                {
                    **_season_head(s),
                    "name": s.names[code],
                    "team_games": s.team_games[code],
                    "shots_total": len(own),
                    "shots_shown": sum(c[2] for c in cells),
                    "cells": cells,
                    "players": _players(own, k, min_shots),
                }
            )
            mixes[code].append(changes(s.season, own))
            names[code] = s.names[code]
    return {
        code: {
            "version": VERSION,
            "source": SOURCE,
            "code": code,
            "name": names[code],
            "hex": _hex_block(k, side_m),
            "cell_fields": TEAM_CELL_FIELDS,
            "player_cell_fields": CELL_FIELDS,
            "player_min_shots": min_shots,
            "seasons": blocks[code],
            "changes": mixes[code],
        }
        for code in sorted(blocks)
    }


def _under_k(zones: dict[str, dict[str, int]], k: int) -> bool:
    return any(zones[c]["n"] < k for c in CLASSES)


def expected_split(
    zones: dict[str, dict[str, int]], league_pps: dict[str, float], league_mean: float
) -> dict[str, float]:
    """A team's points per shot, its expected points per shot (its attempts in each class at the
    league's points per shot there, over its attempts) and the two parts of the difference with
    the league: ``mix`` = xpps - mean and ``making`` = pps - xpps."""
    n = sum(zones[c]["n"] for c in CLASSES)
    pps = sum(zones[c]["pts"] for c in CLASSES) / n
    xpps = sum(zones[c]["n"] * league_pps[c] for c in CLASSES) / n
    return {
        "pps": _r3(pps),
        "xpps": _r3(xpps),
        "mix": _r3(xpps - league_mean),
        "making": _r3(pps - xpps),
    }


def expected_payload(seasons: list[Season], k: int = K) -> dict[str, Any]:
    """Expected points by zone class. A season whose league has a class under k attempts is left
    out, and so is a team with one (``teams_left_out``): no published count is under k."""
    blocks = []
    for s in seasons:
        league, unclassified = zone_totals(s.shots)
        if _under_k(league, k):
            continue
        pps = {c: league[c]["pts"] / league[c]["n"] for c in CLASSES}
        mean = sum(league[c]["pts"] for c in CLASSES) / sum(league[c]["n"] for c in CLASSES)
        by_team: dict[str, list[Shot]] = defaultdict(list)
        for shot in s.shots:
            by_team[shot.team].append(shot)
        teams = []
        for code in sorted(s.names):
            zones, _ = zone_totals(by_team[code])
            if not _under_k(zones, k):
                teams.append(
                    {
                        "code": code,
                        "name": s.names[code],
                        **zones,
                        **expected_split(zones, pps, mean),
                    }
                )
        blocks.append(
            {
                **_season_head(s),
                "league": {**league, "unclassified": unclassified},
                "pps": {c: _r3(pps[c]) for c in CLASSES},
                "mean": _r3(mean),
                "teams": teams,
                "teams_left_out": len(s.names) - len(teams),
            }
        )
    if not blocks:
        raise EuroleaguePublishError(f"{EXPECTED_FILE}: no season with {k} attempts in every class")
    return {
        "version": VERSION,
        "source": SOURCE,
        "k": k,
        "classes": list(CLASSES),
        "rim_zones": sorted(RIM_ZONES),
        "seasons": blocks,
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _cap(name: str, seasons: int) -> int:
    if name == "league.json":
        return LEAGUE_CAP_BYTES_PER_SEASON * seasons
    return EXPECTED_CAP_BYTES if name == EXPECTED_FILE else TEAM_CAP_BYTES


def build_files(raw: Path, seasons: Iterable[str]) -> dict[str, str]:
    """Published path (relative to the euroleague folder) -> text, after the byte caps."""
    loaded = [load_season(raw, s) for s in seasons]
    files = {"league.json": render(league_payload(loaded))}
    for code, payload in team_payloads(loaded).items():
        files[f"teams/{code}.json"] = render(payload)
    files[EXPECTED_FILE] = render(expected_payload(loaded))
    over = []
    for name, text in files.items():
        size = len(text.encode("utf-8"))
        cap = _cap(name, len(loaded))
        if size > cap:
            over.append(f"{name}: {size} B > {cap} B")
    if over:
        raise EuroleaguePublishError("over the byte cap, nothing written: " + "; ".join(over))
    return files


PUBLIC_SQL = Path(__file__).parents[1] / "learn" / "expected-points.sql"
TABLE_FIELDS = ("pps", "xpps", "mix", "making")


def public_sql_problems(path: Path) -> tuple[int, list[str]]:
    """Lesson 12's "Reproduce it" query run with DuckDB on a published expected-points.json: its
    rows against the file's own, every team of every season, exactly."""
    import duckdb

    sql = PUBLIC_SQL.read_text(encoding="utf-8").replace(
        "'expected-points.json'", f"'{path.resolve().as_posix()}'"
    )
    rows = duckdb.connect().execute(sql).fetchall()
    doc = _read_json(path)
    want = {
        (s["season"], t["code"]): tuple(t[f] for f in TABLE_FIELDS)
        for s in doc["seasons"]
        for t in s["teams"]
    }
    got = {(season, code): tuple(values) for season, code, *values in rows}
    problems = [
        f"{key}: query {got.get(key)}, file {want.get(key)}"
        for key in sorted(want.keys() | got.keys())
        if got.get(key) != want.get(key)
    ]
    return len(want), problems


def _on_disk(folder: Path) -> dict[str, bytes]:
    if not folder.is_dir():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*.json")}


def run_euroleague_publish(
    data_dir: Path, out_dir: Path, seasons: Iterable[str] = SEASONS, *, check: bool = False
) -> int:
    raw = data_dir / "euroleague" / "raw"
    folder = out_dir / "euroleague"
    seasons = list(seasons)
    if check and not all((raw / s / "manifest.json").is_file() for s in seasons):
        print(
            f"euroleague publish --check: PARTIAL: no downloaded data for {', '.join(seasons)} "
            f"under {raw}; nothing recomputed"
        )
        return 0
    try:
        files = build_files(raw, seasons)
    except EuroleaguePublishError as exc:
        print(f"euroleague publish: {exc}")
        return 1
    wanted = {name: text.encode("utf-8") for name, text in files.items()}
    present = _on_disk(folder)
    if check:
        differ = sorted(
            n for n in wanted.keys() | present.keys() if wanted.get(n) != present.get(n)
        )
        if differ:
            print(f"euroleague publish --check: {len(differ)} files differ: {', '.join(differ)}")
            return 1
        rows, problems = public_sql_problems(folder / EXPECTED_FILE)
        if problems:
            detail = "; ".join(problems)
            print(f"euroleague publish --check: learn/expected-points.sql differs: {detail}")
            return 1
        print(
            f"euroleague publish --check: FULL {len(wanted)}/{len(wanted)} files rebuilt; "
            f"learn/expected-points.sql gives the {rows} rows of {EXPECTED_FILE}"
        )
        return 0
    for name in present.keys() - wanted.keys():
        (folder / name).unlink()
    for name, text in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"euroleague publish: {name} ({len(wanted[name])} bytes)")
    return 0
