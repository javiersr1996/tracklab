"""`tracklab learn speed`: where the provider's speed comes from (lesson 2, P8).

The basketball files give every player a `speed` (ft/s, says the provider's dictionary) next to
`x, y` (ft) at 25 fps. This module puts that field next to finite differences of the same
player's positions, match by match, from bronze `tracking_objects` (players only, every row, no
filter on any flag), and writes `web/public/data/learn/speed.json`:

- on every *triple* (a row whose player has the frames just before and just after it): the
  correlation of `speed` with the central difference, the median and 99th percentile of their
  gap, and the median gap of the forward and backward differences on the same rows;
- on every row with five such frames each side: the median gap of a moving average of `k`
  central differences, for each `k` of `WINDOWS`, and of Shaw's recipe (backward difference,
  Savitzky-Golay of window 7 and order 1, which is a moving average of 7, after dropping any
  raw speed over 12 m/s);
- the largest `speed` and how many rows pass 12 m/s, over all rows and over triples;
- the example: the provider's speed of `bb:59191` over the 341 frames of the published
  possession 114099-1-41 (whose positions are published at 1 cm), and the gap of the central
  difference at full precision over its inner frames.

Every gap is |speed - estimate| in m/s; the estimate's speed is the length of its velocity.
`--check` rebuilds the file from bronze and compares its bytes, and runs `speed.sql` (the query
"Reproduce it" shows) on the public raw files, comparing its triples, r and median gap with the
file: `FULL n/n` when both were done for all n matches, else `PARTIAL k/n` and what it checked.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import numpy.typing as npt

from tracklab.bronze.common import raw_root_for
from tracklab.publish.possessions import ROUND_NDIGITS
from tracklab.silver.orientation import M_PER_FT

SOURCE_ID = "opendata-basketball"
SQL_PATH = Path(__file__).with_name("speed.sql")
SQL_MATCH_ID = "114099"  # the id the public SQL is written for: the example's match

FPS = 25  # the provider's dictionary, `frameIdx`: "Frame count (at 25fps)"
H = 1.0 / FPS
MAX_SPEED = 12.0  # m/s: Shaw's `maxspeed`, Metrica_Velocities.py at 7ed3ff8, line 16
SHAW_WINDOW = 7  # Shaw's `window`, same line; with `polyorder=1` it is a moving average
WINDOWS = (1, 3, 5, 7, 9)
REACH = (max(WINDOWS) - 1) // 2 + 1  # frames each side a moving average of WINDOWS reads

EXAMPLE_FILE = "bb_possessions_possession-114099-1-41.json"
EXAMPLE_ENTITY = "bb:59191"
RESOLUTION_M = 10.0**-ROUND_NDIGITS  # how finely the possessions publish a position

Floats = npt.NDArray[np.float64]
Weights = dict[int, float]  # frame offset -> weight on the position at that offset


@dataclass(frozen=True)
class Track:
    """The player rows of one match, sorted by player and frame; metres and m/s."""

    player: npt.NDArray[np.int64]
    frame: npt.NDArray[np.int64]
    x: Floats
    y: Floats
    speed: Floats


def read_track(path: Path) -> Track:
    rows = (
        duckdb.connect()
        .execute(
            "SELECT playerId, frameIdx, x, y, speed FROM read_parquet(?) "
            "WHERE side <> 'ball' ORDER BY playerId, frameIdx",
            [path.as_posix()],
        )
        .fetchnumpy()
    )
    p, f, x, y, s = (rows[k] for k in ("playerId", "frameIdx", "x", "y", "speed"))
    return Track(
        np.asarray(p, np.int64),
        np.asarray(f, np.int64),
        np.asarray(x, np.float64) * M_PER_FT,
        np.asarray(y, np.float64) * M_PER_FT,
        np.asarray(s, np.float64) * M_PER_FT,
    )


def contiguous(t: Track, reach: int) -> npt.NDArray[np.bool_]:
    """Rows whose player is in the file at every frame from `reach` before to `reach` after.

    The rows are sorted by player and frame, so row i + j is frame f + j of the same player
    exactly when its player is the same and its frame is f + j."""
    n = len(t.frame)
    ok = np.zeros(n, np.bool_)
    if n <= 2 * reach:
        return ok
    ok[reach : n - reach] = True
    for j in range(1, reach + 1):
        ahead = (t.player[j:] == t.player[:-j]) & (t.frame[j:] - t.frame[:-j] == j)
        ok[reach : n - reach] &= ahead[reach : n - reach] & ahead[reach - j : n - reach - j]
    return ok


def difference(after: int, before: int) -> Weights:
    """The finite difference from `before` frames back to `after` frames ahead, per second."""
    span = (after + before) * H
    return {after: 1.0 / span, -before: -1.0 / span}


CENTRAL = difference(1, 1)
FORWARD = difference(1, 0)
BACKWARD = difference(0, 1)


def smoothed(weights: Weights, k: int) -> Weights:
    """A centred moving average of `k` (odd) copies of a difference: the weights add up, so
    the inner positions cancel and a moving average of differences is one longer difference."""
    half = (k - 1) // 2
    out: Weights = {}
    for j in range(-half, half + 1):
        for offset, w in weights.items():
            out[offset + j] = out.get(offset + j, 0.0) + w / k
    return {o: w for o, w in sorted(out.items()) if abs(w) > 1e-12}


def estimate(t: Track, rows: npt.NDArray[np.intp], weights: Weights) -> Floats:
    """The speed of the velocity `weights` give at `rows` (each row's offsets must exist)."""
    vx = np.zeros(len(rows))
    vy = np.zeros(len(rows))
    for o, w in weights.items():
        vx += w * t.x[rows + o]
        vy += w * t.y[rows + o]
    return np.asarray(np.hypot(vx, vy), np.float64)


def shaw_rows(t: Track, rows: npt.NDArray[np.intp]) -> npt.NDArray[np.intp]:
    """Shaw drops every raw (backward) speed over `MAX_SPEED` before smoothing, so a window of
    `SHAW_WINDOW` that holds one has no smoothed value: those rows go."""
    half = (SHAW_WINDOW - 1) // 2
    keep = np.ones(len(rows), np.bool_)
    for j in range(-half, half + 1):
        keep &= estimate(t, rows + j, BACKWARD) <= MAX_SPEED
    return rows[keep]


def median_gap(speed: Floats, est: Floats) -> float:
    return float(np.median(np.abs(speed - est)))


def match_figures(t: Track) -> dict[str, Any]:
    triple = np.flatnonzero(contiguous(t, 1))
    wide = np.flatnonzero(contiguous(t, REACH))
    s3 = t.speed[triple]
    central = estimate(t, triple, CENTRAL)
    gap = np.abs(s3 - central)
    shaw = shaw_rows(t, wide)
    return {
        "rows": len(t.speed),
        "triples": len(triple),
        "r": round(float(np.corrcoef(s3, central)[0, 1]), 5),
        "median_gap": round(float(np.median(gap)), 4),
        "p99_gap": round(float(np.quantile(gap, 0.99)), 3),
        "median_gap_forward": round(median_gap(s3, estimate(t, triple, FORWARD)), 4),
        "median_gap_backward": round(median_gap(s3, estimate(t, triple, BACKWARD)), 4),
        "max_speed": round(float(t.speed.max()), 2),
        "max_speed_triples": round(float(s3.max()), 2),
        "over_max": int((t.speed > MAX_SPEED).sum()),
        "over_max_triples": int((s3 > MAX_SPEED).sum()),
        "window_rows": len(wide),
        "by_window": {
            str(k): round(median_gap(t.speed[wide], estimate(t, wide, smoothed(CENTRAL, k))), 4)
            for k in WINDOWS
        },
        "shaw_rows": len(shaw),
        "median_gap_shaw": round(
            median_gap(t.speed[shaw], estimate(t, shaw, smoothed(BACKWARD, SHAW_WINDOW))), 4
        ),
    }


def example_figures(data_dir: Path, possession: Path) -> dict[str, Any]:
    """The example player's speed over the published possession, joined to bronze by
    `wallClock` (the possession's `t`), and the central gap at full precision."""
    pos = json.loads(possession.read_text(encoding="utf-8"))
    entity = next(e for e in pos["entities"] if e["entity_id"] == EXAMPLE_ENTITY)
    native = int(pos["match"]["match_id"].removeprefix("bb:"))
    player = int(EXAMPLE_ENTITY.removeprefix("bb:"))
    t_ms = [fr["t"] for fr in pos["frames"]]
    if any(b - a != 1000 // FPS for a, b in zip(t_ms, t_ms[1:], strict=False)):
        raise ValueError(f"{possession.name}: the frames are not one {1000 // FPS} ms step apart")
    published = [next(o for o in fr["o"] if o[0] == entity["i"]) for fr in pos["frames"]]
    bronze = data_dir / "bronze" / "basketball"
    rows = (
        duckdb.connect()
        .execute(
            "SELECT fr.wallClock, o.x, o.y, o.speed "
            "FROM read_parquet(?) o JOIN read_parquet(?) fr USING (frameIdx) "
            "WHERE o.playerId = ? AND fr.wallClock BETWEEN ? AND ? ORDER BY fr.wallClock",
            [
                (bronze / "tracking_objects" / f"{native}.parquet").as_posix(),
                (bronze / "tracking_frames" / f"{native}.parquet").as_posix(),
                player,
                t_ms[0],
                t_ms[-1],
            ],
        )
        .fetchall()
    )
    if [r[0] for r in rows] != t_ms:
        raise ValueError(f"{EXAMPLE_ENTITY} is not in bronze at every frame of {possession.name}")
    x = np.array([r[1] for r in rows]) * M_PER_FT
    y = np.array([r[2] for r in rows]) * M_PER_FT
    speed = np.array([r[3] for r in rows]) * M_PER_FT
    # The join is right only if the published positions are bronze's, rounded.
    off = max(max(abs(p[1] - a), abs(p[2] - b)) for p, a, b in zip(published, x, y, strict=True))
    if off > RESOLUTION_M / 2 + 1e-9:
        raise ValueError(f"{possession.name}: published positions {off:.4f} m from bronze")
    inner = Track(np.zeros(len(x), np.int64), np.arange(len(x), dtype=np.int64), x, y, speed)
    rows_in = np.arange(1, len(x) - 1)
    gap = np.abs(speed[rows_in] - estimate(inner, rows_in, CENTRAL))
    return {
        "possession": EXAMPLE_FILE,
        "possession_id": pos["possession_id"],
        "match_id": pos["match"]["match_id"],
        "entity_id": EXAMPLE_ENTITY,
        "t0_ms": t_ms[0],
        "frames": len(t_ms),
        "speed": [round(float(v), 3) for v in speed],
        "full_precision": {
            "frames": len(rows_in),
            "median_gap": round(float(np.median(gap)), 4),
            "max_gap": round(float(gap.max()), 4),
        },
    }


def build(data_dir: Path, possessions: Path) -> dict[str, Any]:
    folder = data_dir / "bronze" / "basketball" / "tracking_objects"
    paths = sorted(folder.glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"no bronze tracking_objects under {folder}")
    return {
        "schema_version": 1,
        "fps": FPS,
        "m_per_ft": M_PER_FT,
        "max_speed": MAX_SPEED,
        "shaw_window": SHAW_WINDOW,
        "windows": list(WINDOWS),
        "resolution_m": RESOLUTION_M,
        "matches": [{"match_id": f"bb:{p.stem}", **match_figures(read_track(p))} for p in paths],
        "example": example_figures(data_dir, possessions / EXAMPLE_FILE),
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# The public SQL, run on the raw files.

SqlFigures = tuple[int, float, float]  # (triples, r, median_gap)


def read_sql() -> str:
    return SQL_PATH.read_bytes().decode("utf-8")


def match_sql(match_id: int) -> str:
    return read_sql().replace(SQL_MATCH_ID, str(match_id))


def run_sql(sql: str, match_dir: Path) -> SqlFigures:
    """The SQL run from `match_dir`, where its file name is relative."""
    here = Path.cwd()
    os.chdir(match_dir)
    try:
        con = duckdb.connect()
        con.execute("SET enable_progress_bar = false")
        row = con.execute(sql).fetchone()
    finally:
        os.chdir(here)
    assert row is not None
    return int(row[0]), float(row[1]), float(row[2])


def _sql_agrees(got: SqlFigures, row: dict[str, Any]) -> bool:
    # One unit of the last decimal either way: the two sides round independently computed sums.
    return bool(
        got[0] == row["triples"]
        and abs(got[1] - row["r"]) <= 1e-5 + 1e-12
        and abs(got[2] - row["median_gap"]) <= 1e-4 + 1e-12
    )


def _raw_matches(data_dir: Path) -> Path | None:
    try:
        return raw_root_for(data_dir, SOURCE_ID) / "data" / "matches"
    except (FileNotFoundError, RuntimeError):
        return None


def run_learn_speed(data_dir: Path, out: Path, possessions: Path, *, check: bool = False) -> int:
    if not check:
        text = render(build(data_dir, possessions))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"learn speed: {out} ({out.stat().st_size} bytes)")
        return 0

    named = read_sql().count(SQL_MATCH_ID)
    if named != 1:
        print(f"learn speed: speed.sql names {SQL_MATCH_ID} {named} times, not once")
        return 1
    raw_bytes = out.read_bytes()
    if b"\r" in raw_bytes:
        print(f"learn speed --check: {out.name} has CR line ends")
        return 1
    on_disk = json.loads(raw_bytes.decode("utf-8"))
    rows = {m["match_id"]: m for m in on_disk["matches"]}
    total = len(rows)
    done: list[str] = []

    # 1. The bytes, rebuilt from bronze, when bronze holds every match the file was measured on.
    bronze = data_dir / "bronze" / "basketball" / "tracking_objects"
    have = {f"bb:{p.stem}" for p in bronze.glob("*.parquet")} if bronze.is_dir() else set()
    rebuilt = False
    if have == set(rows):
        text = render(build(data_dir, possessions))
        if text.encode("utf-8") != raw_bytes:
            print(f"learn speed --check: {out.name} differs from what bronze gives")
            return 1
        rebuilt = True
        done.append(f"the bytes of {out.name} rebuilt from bronze")
    elif have:
        # A slice (the CI fixtures): the code runs on it, but its figures are not the file's.
        for p in sorted(bronze.glob("*.parquet")):
            fig = match_figures(read_track(p))
            print(
                f"learn speed bb:{p.stem} (bronze slice, not compared): rows={fig['rows']} "
                f"triples={fig['triples']} r={fig['r']} median_gap={fig['median_gap']}"
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
        same = _sql_agrees(got, row)
        print(
            f"learn speed {native}: triples={got[0]} r={got[1]} median_gap={got[2]} "
            f"({out.name}: {row['triples']}, {row['r']}, {row['median_gap']}) "
            f"{'equal' if same else 'DIFFERENT'}"
        )
        if not same:
            different.append(match_id)
    if different:
        print(f"learn speed: {different} differ from {out.name}")
        return 1
    if compared:
        done.append(f"speed.sql on the raw files of {compared} match(es)")

    shape = _shape_problems(on_disk, possessions)
    if shape:
        print(f"learn speed --check: {shape}")
        return 1
    done.append(
        f"{out.name} has {total} matches with every field, its example spans the published "
        f"possession's frames and player, and speed.sql names its match id once"
    )
    if rebuilt and compared == total:
        print(f"learn speed --check: FULL {total}/{total}: " + "; ".join(done))
    else:
        k = compared if rebuilt else 0
        print(f"learn speed --check: PARTIAL {k}/{total}: " + "; ".join(done))
    return 0


FIELDS = {
    "match_id",
    "rows",
    "triples",
    "r",
    "median_gap",
    "p99_gap",
    "median_gap_forward",
    "median_gap_backward",
    "max_speed",
    "max_speed_triples",
    "over_max",
    "over_max_triples",
    "window_rows",
    "by_window",
    "shaw_rows",
    "median_gap_shaw",
}


def _shape_problems(payload: dict[str, Any], possessions: Path) -> str:
    """What the file must hold whatever data is at hand."""
    for m in payload["matches"]:
        if set(m) != FIELDS:
            return f"{m.get('match_id')}: fields {sorted(set(m) ^ FIELDS)}"
        if [int(k) for k in m["by_window"]] != payload["windows"]:
            return f"{m['match_id']}: by_window is not over {payload['windows']}"
    ex = payload["example"]
    pos = json.loads((possessions / ex["possession"]).read_text(encoding="utf-8"))
    if pos["frames"][0]["t"] != ex["t0_ms"] or len(pos["frames"]) != ex["frames"]:
        return f"the example does not start and end with {ex['possession']}"
    if len(ex["speed"]) != ex["frames"]:
        return f"the example has {len(ex['speed'])} speeds for {ex['frames']} frames"
    if not any(e["entity_id"] == ex["entity_id"] for e in pos["entities"]):
        return f"{ex['entity_id']} is not in {ex['possession']}"
    return ""
