"""`tracklab learn rebound`: who gets to the rebound first (lesson 4, P8).

For every rebound a player took after a missed field goal, the ten players are frozen at the
shot's `endFrame` (the provider's "end of the shot"): their positions, and their velocities as
the central difference of the frames either side (lesson 2). The target is the rebound's
`location`, which the provider defines as the rebounder's. Two rules name who gets there first:

- the nearest player, in distance, with no model at all;
- the time to arrive: for `REACTION_S` the player carries the velocity they have, then covers
  the rest at `TOP_SPEED` (Shaw's simplification of Spearman 2018), and the smallest time wins.

Per match it writes, to `web/public/data/learn/rebound.json`, how many rebounds pass each rule of
selection, how often each rule names the rebounder, how often they name the same player, the
model's hits for every reaction time of `REACTIONS`, the mean chance the model gives its own pick
of being first under Spearman's logistic spread `SPREAD_S`, and the median wait from the shot's
end to the rebound. The example is the first rebound, in frame order, of the match the public SQL
is written for in which the two rules name different players; it is published at `DIGITS`
decimals and its picks and chances are computed from those published values.

`--check` rebuilds the file from bronze and compares its bytes, and runs `rebound.sql` (the query
"Reproduce it" shows) on the public raw files, comparing its counts with the file: `FULL n/n`
when both were done for all n matches, else `PARTIAL k/n` and what it checked.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import numpy.typing as npt

from tracklab.bronze.common import raw_root_for
from tracklab.silver.orientation import M_PER_FT

SOURCE_ID = "opendata-basketball"
SQL_PATH = Path(__file__).with_name("rebound.sql")
SQL_MATCH_ID = "114086"  # the match the public SQL is written for, and the example's
SQL_NAMES = 3  # the events file twice (rebounds, shots) and the tracking file once

FPS = 25  # the provider's dictionary: "Frame (at 25fps)"
REACTION_S = 0.7  # Shaw, Metrica_PitchControl.py at 7ed3ff8, line 190
TOP_SPEED = 5.0  # m/s: Spearman (2018), section 3.1.1; Shaw, line 189
SPREAD_S = 0.54  # s: Spearman (2018), Table 1, the MAP of s
REACTIONS = tuple(round(0.1 * k, 1) for k in range(16))
PLAYERS = 10
GRID = 40.0  # the chance of being first integrates over +-GRID logistic scales
STEP = 0.02  # ... in steps of STEP scales
DIGITS = 2  # the example's positions (m) and velocities (m/s)

Floats = npt.NDArray[np.float64]


@dataclass(frozen=True)
class Race:
    """One rebound, frozen at the end of its shot. Metres and m/s; `rebounder` indexes `player`."""

    rebound_id: str
    frame: int
    end_frame: int
    target: Floats  # (2,)
    player: npt.NDArray[np.int64]  # (PLAYERS,), sorted
    pos: Floats  # (PLAYERS, 2)
    vel: Floats  # (PLAYERS, 2)
    rebounder: int


# The model.


def arrival(race: Race, reaction: float = REACTION_S, top_speed: float = TOP_SPEED) -> Floats:
    """Each player's time to arrive at the target: the reaction carries the current velocity,
    then the rest of the way is run at the top speed."""
    rest = race.target - race.pos - race.vel * reaction
    return np.asarray(reaction + np.hypot(rest[:, 0], rest[:, 1]) / top_speed, np.float64)


def nearest(race: Race) -> int:
    gap = race.target - race.pos
    return int(np.argmin(np.hypot(gap[:, 0], gap[:, 1])))


def first(race: Race, reaction: float = REACTION_S) -> int:
    return int(np.argmin(arrival(race, reaction)))


def chance_first(times: Floats, spread: float = SPREAD_S) -> Floats:
    """The chance each player is first when every arrival is logistic around its time with
    standard deviation `spread` (Spearman's equation 4): the integral over t of one player's
    density times every other player's chance of not having arrived yet."""
    scale = math.sqrt(3.0) * spread / math.pi
    t = float(times.min()) + scale * np.arange(-GRID, GRID + STEP / 2, STEP)
    arrived = 0.5 * (1.0 + np.tanh((t[None, :] - times[:, None]) / scale / 2.0))
    density = arrived * (1.0 - arrived) / scale
    out = np.empty(len(times))
    for i in range(len(times)):
        others = np.prod(np.delete(1.0 - arrived, i, axis=0), axis=0)
        out[i] = float(np.sum(density[i] * others) * STEP * scale)
    return out


# Reading bronze.


@dataclass(frozen=True)
class Funnel:
    """How many rebounds pass each rule of selection, in order."""

    rebounds: int
    by_player: int
    field_goal: int
    located: int
    after_end: int


def read_match(bronze: Path, match: int) -> tuple[Funnel, list[Race]]:
    con = duckdb.connect()
    rows = con.execute(
        "SELECT r.id, r.frame, r.rebounded AND r.rebounderId IS NOT NULL, r.rebounderId, "
        "s.id IS NOT NULL, r.location_x, r.location_y, s.endFrame "
        "FROM read_parquet(?) r LEFT JOIN read_parquet(?) s ON s.id = r.shotId "
        "ORDER BY r.frame, r.id",
        [
            (bronze / "events_rebounds" / f"{match}.parquet").as_posix(),
            (bronze / "events_shots" / f"{match}.parquet").as_posix(),
        ],
    ).fetchall()
    by_player = [r for r in rows if r[2]]
    field_goal = [r for r in by_player if r[4]]
    located = [r for r in field_goal if r[5] is not None and r[6] is not None]
    after = [r for r in located if r[1] > r[7]]
    funnel = Funnel(len(rows), len(by_player), len(field_goal), len(located), len(after))

    frames = sorted({r[7] + k for r in after for k in (-1, 0, 1)})
    at: dict[int, dict[int, tuple[float, float]]] = {}
    if frames:
        for f, p, x, y in con.execute(
            "SELECT frameIdx, playerId, x, y FROM read_parquet(?) "
            "WHERE side <> 'ball' AND list_contains(?, frameIdx)",
            [(bronze / "tracking_objects" / f"{match}.parquet").as_posix(), frames],
        ).fetchall():
            at.setdefault(f, {})[p] = (x * M_PER_FT, y * M_PER_FT)

    races: list[Race] = []
    for rid, frame, _, rebounder, _, lx, ly, end in after:
        before, now, next_ = at.get(end - 1, {}), at.get(end, {}), at.get(end + 1, {})
        ids = sorted(set(now) & set(before) & set(next_))
        if len(now) != PLAYERS or len(ids) != PLAYERS or rebounder not in ids:
            continue
        pos = np.array([now[i] for i in ids])
        vel = (np.array([next_[i] for i in ids]) - np.array([before[i] for i in ids])) * FPS / 2
        target = np.array([lx, ly]) * M_PER_FT
        player = np.array(ids, np.int64)
        races.append(Race(rid, frame, end, target, player, pos, vel, ids.index(rebounder)))
    return funnel, races


# The figures.


def match_figures(funnel: Funnel, races: list[Race]) -> dict[str, Any]:
    picks = [(first(r), nearest(r)) for r in races]
    sure = [chance_first(arrival(r))[m] for r, (m, _) in zip(races, picks, strict=True)]
    waits = [(r.frame - r.end_frame) / FPS for r in races]
    return {
        "rebounds": funnel.rebounds,
        "by_player": funnel.by_player,
        "field_goal": funnel.field_goal,
        "located": funnel.located,
        "after_end": funnel.after_end,
        "n": len(races),
        "model": sum(m == r.rebounder for r, (m, _) in zip(races, picks, strict=True)),
        "nearest": sum(n == r.rebounder for r, (_, n) in zip(races, picks, strict=True)),
        "same": sum(m == n for m, n in picks),
        "by_reaction": [sum(first(r, tau) == r.rebounder for r in races) for tau in REACTIONS],
        "confidence": round(float(np.mean(sure)), 3) if races else None,
        "median_wait_s": round(float(np.median(waits)), 2) if races else None,
    }


def rounded(race: Race) -> Race:
    """The race as the example publishes it."""
    return Race(
        race.rebound_id,
        race.frame,
        race.end_frame,
        np.round(race.target, DIGITS),
        race.player,
        np.round(race.pos, DIGITS),
        np.round(race.vel, DIGITS),
        race.rebounder,
    )


def example_race(races: list[Race]) -> Race:
    """The rule: the first rebound, in frame order, where the two rules name different players."""
    race = next(r for r in races if first(r) != nearest(r))
    shown = rounded(race)
    if (first(shown), nearest(shown)) != (first(race), nearest(race)):
        raise ValueError(f"{race.rebound_id}: rounding to {DIGITS} decimals changes a pick")
    return shown


def example_figures(bronze: Path, match: int, race: Race) -> dict[str, Any]:
    con = duckdb.connect()
    shot = con.execute(
        "SELECT s.id, s.offTeamId, s.location_x FROM read_parquet(?) r "
        "JOIN read_parquet(?) s ON s.id = r.shotId WHERE r.id = ?",
        [
            (bronze / "events_rebounds" / f"{match}.parquet").as_posix(),
            (bronze / "events_shots" / f"{match}.parquet").as_posix(),
            race.rebound_id,
        ],
    ).fetchone()
    assert shot is not None
    team = dict(
        con.execute(
            "SELECT playerId, teamId FROM read_parquet(?)",
            [(bronze / "game_players" / f"{match}.parquet").as_posix()],
        ).fetchall()
    )
    jersey = dict(
        con.execute(
            "SELECT playerId, jersey FROM read_parquet(?) WHERE frameIdx = ? AND side <> 'ball'",
            [(bronze / "tracking_objects" / f"{match}.parquet").as_posix(), race.end_frame],
        ).fetchall()
    )
    times = arrival(race)
    chance = chance_first(times)
    players = [
        {
            "jersey": jersey[int(p)],
            "team": "shooting" if team[int(p)] == shot[1] else "defending",
            "x": float(race.pos[i, 0]),
            "y": float(race.pos[i, 1]),
            "vx": float(race.vel[i, 0]),
            "vy": float(race.vel[i, 1]),
        }
        for i, p in enumerate(race.player)
    ]
    order = sorted(
        range(PLAYERS),
        key=lambda i: (players[i]["team"] != "shooting", _jersey_key(players[i]["jersey"])),
    )
    index = {old: new for new, old in enumerate(order)}
    return {
        "match_id": f"bb:{match}",
        "rebound_id": race.rebound_id,
        "shot_id": shot[0],
        "end_frame": race.end_frame,
        "frame": race.frame,
        "wait_s": round((race.frame - race.end_frame) / FPS, 2),
        "basket_side": 1 if shot[2] > 0 else -1,
        "target": [float(v) for v in race.target],
        "players": [players[i] for i in order],
        "rebounder": index[race.rebounder],
        "nearest": index[nearest(race)],
        "model": index[first(race)],
        "times": [round(float(times[i]), 3) for i in order],
        "chance_first": [round(float(chance[i]), 3) for i in order],
    }


def _jersey_key(jersey: str) -> tuple[int, str]:
    return (int(jersey), jersey) if jersey.isdigit() else (1000, jersey)


def _matches(bronze: Path) -> list[int]:
    return sorted(int(p.stem) for p in (bronze / "events_rebounds").glob("*.parquet"))


def build(data_dir: Path) -> dict[str, Any]:
    bronze = data_dir / "bronze" / "basketball"
    matches = _matches(bronze)
    if not matches:
        raise FileNotFoundError(f"no bronze events_rebounds under {bronze}")
    rows = []
    example: dict[str, Any] = {}
    for match in matches:
        funnel, races = read_match(bronze, match)
        rows.append({"match_id": f"bb:{match}", **match_figures(funnel, races)})
        if str(match) == SQL_MATCH_ID:
            example = example_figures(bronze, match, example_race(races))
    if not example:
        raise ValueError(f"match {SQL_MATCH_ID}, the example's, is not in bronze")
    return {
        "schema_version": 1,
        "fps": FPS,
        "players": PLAYERS,
        "reaction_s": REACTION_S,
        "top_speed": TOP_SPEED,
        "spread_s": SPREAD_S,
        "reactions": list(REACTIONS),
        "digits": DIGITS,
        "matches": rows,
        "example": example,
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# The public SQL, run on the raw files.

SqlFigures = tuple[int, int, int]  # (n, model, nearest)


def read_sql() -> str:
    return SQL_PATH.read_bytes().decode("utf-8")


def match_sql(match_id: int) -> str:
    return read_sql().replace(SQL_MATCH_ID, str(match_id))


def run_sql(sql: str, match_dir: Path) -> SqlFigures:
    """The SQL run from `match_dir`, where its file names are relative."""
    here = Path.cwd()
    os.chdir(match_dir)
    try:
        con = duckdb.connect()
        con.execute("SET enable_progress_bar = false")
        row = con.execute(sql).fetchone()
    finally:
        os.chdir(here)
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def _raw_matches(data_dir: Path) -> Path | None:
    try:
        return raw_root_for(data_dir, SOURCE_ID) / "data" / "matches"
    except (FileNotFoundError, RuntimeError):
        return None


def run_learn_rebound(data_dir: Path, out: Path, *, check: bool = False) -> int:
    if not check:
        text = render(build(data_dir))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"learn rebound: {out} ({out.stat().st_size} bytes)")
        return 0

    named = read_sql().count(SQL_MATCH_ID)
    if named != SQL_NAMES:
        print(f"learn rebound: rebound.sql names {SQL_MATCH_ID} {named} times, not {SQL_NAMES}")
        return 1
    raw_bytes = out.read_bytes()
    if b"\r" in raw_bytes:
        print(f"learn rebound --check: {out.name} has CR line ends")
        return 1
    on_disk = json.loads(raw_bytes.decode("utf-8"))
    rows = {m["match_id"]: m for m in on_disk["matches"]}
    total = len(rows)
    done: list[str] = []

    # 1. The bytes, rebuilt from bronze, when bronze holds every match the file was measured on.
    bronze = data_dir / "bronze" / "basketball"
    have = {f"bb:{m}" for m in _matches(bronze)} if (bronze / "events_rebounds").is_dir() else set()
    rebuilt = False
    if have == set(rows):
        if render(build(data_dir)).encode("utf-8") != raw_bytes:
            print(f"learn rebound --check: {out.name} differs from what bronze gives")
            return 1
        rebuilt = True
        done.append(f"the bytes of {out.name} rebuilt from bronze")
    elif have:
        # A slice (the CI fixtures): the code runs on it, but its figures are not the file's.
        for match in _matches(bronze):
            fig = match_figures(*read_match(bronze, match))
            print(
                f"learn rebound bb:{match} (bronze slice, not compared): "
                f"rebounds={fig['rebounds']} "
                f"after_end={fig['after_end']} n={fig['n']} model={fig['model']} "
                f"nearest={fig['nearest']}"
            )
        done.append(f"the code ran on the bronze of {len(have)} match(es) not compared")

    # 2. The public SQL on the raw files.
    matches = _raw_matches(data_dir)
    compared = 0
    different: list[str] = []
    for match_id, row in sorted(rows.items()):
        native = int(match_id.removeprefix("bb:"))
        if matches is None or not (matches / str(native)).is_dir():
            continue
        got = run_sql(match_sql(native), matches / str(native))
        compared += 1
        want = (row["n"], row["model"], row["nearest"])
        print(
            f"learn rebound {native}: rebounds={got[0]} model_first={got[1]} "
            f"nearest_first={got[2]} ({out.name}: {want[0]}, {want[1]}, {want[2]}) "
            f"{'equal' if got == want else 'DIFFERENT'}"
        )
        if got != want:
            different.append(match_id)
    if different:
        print(f"learn rebound: {different} differ from {out.name}")
        return 1
    if compared:
        done.append(f"rebound.sql on the raw files of {compared} match(es)")

    shape = _shape_problems(on_disk)
    if shape:
        print(f"learn rebound --check: {shape}")
        return 1
    done.append(
        f"{out.name} has {total} matches with every field and counts that add up, its example "
        f"has {PLAYERS} players whose picks and chances follow from its published values, and "
        f"rebound.sql names its match id in its {SQL_NAMES} file names"
    )
    if rebuilt and compared == total:
        print(f"learn rebound --check: FULL {total}/{total}: " + "; ".join(done))
    else:
        k = compared if rebuilt else 0
        print(f"learn rebound --check: PARTIAL {k}/{total}: " + "; ".join(done))
    return 0


FIELDS = {
    "match_id",
    "rebounds",
    "by_player",
    "field_goal",
    "located",
    "after_end",
    "n",
    "model",
    "nearest",
    "same",
    "by_reaction",
    "confidence",
    "median_wait_s",
}


def _shape_problems(payload: dict[str, Any]) -> str:
    """What the file must hold whatever data is at hand."""
    for m in payload["matches"]:
        if set(m) != FIELDS:
            return f"{m.get('match_id')}: fields {sorted(set(m) ^ FIELDS)}"
        funnel = [
            m[k] for k in ("rebounds", "by_player", "field_goal", "located", "after_end", "n")
        ]
        if funnel != sorted(funnel, reverse=True):
            return f"{m['match_id']}: the selection grows somewhere: {funnel}"
        if len(m["by_reaction"]) != len(payload["reactions"]):
            return f"{m['match_id']}: by_reaction is not over {payload['reactions']}"
        if m["by_reaction"][payload["reactions"].index(0.0)] != m["nearest"]:
            return f"{m['match_id']}: with no reaction the model is not the nearest player"
    ex = payload["example"]
    if len(ex["players"]) != PLAYERS:
        return f"the example has {len(ex['players'])} players"
    pos = np.array([[p["x"], p["y"]] for p in ex["players"]])
    vel = np.array([[p["vx"], p["vy"]] for p in ex["players"]])
    race = Race(
        ex["rebound_id"],
        ex["frame"],
        ex["end_frame"],
        np.array(ex["target"]),
        np.arange(PLAYERS, dtype=np.int64),
        pos,
        vel,
        ex["rebounder"],
    )
    times = arrival(race, payload["reaction_s"], payload["top_speed"])
    if (first(race, payload["reaction_s"]), nearest(race)) != (ex["model"], ex["nearest"]):
        return "the example's picks do not follow from its published values"
    if [round(float(t), 3) for t in times] != ex["times"]:
        return "the example's times do not follow from its published values"
    return ""
