"""`tracklab learn dribble`: how many bounces per second (lesson 9, P9)?

The provider's basketball events list every dribble with its `frame` and the `touchId` of the touch
it belongs to: one player's continuous control of the ball. The tracking gives the ball's height
at every frame. The lesson reads the two as two witnesses of one rhythm: the events as points in
time, the height as a signal that falls to the floor and rises again.

Per match, from bronze `events_dribbles` and the ball rows of `tracking_objects` (feet, to metres):

- the dribbles with a frame; the intervals between consecutive dribbles of one touch (frames over
  25, in s) and their median, 10th and 90th percentiles (linear interpolation, as DuckDB's
  `quantile_cont`); the touches with `TOUCH_MIN` dribbles or more;
- for every dribble whose ball rows cover all `2 * REACH + 1` frames around its `frame` (a
  window), the offset in frames from the event to the ball's lowest height in that window (ties
  to the earliest frame); the median offset and the median of its size; the share of windows whose
  lowest point is at most `NEAR` frames from the event and the share at the window's edge; the
  median of the lowest heights;
- the pairs of consecutive dribbles of a touch that both have a window, and how many of those
  pairs share their lowest frame: two events on one low point.

The example is the touch with the most dribbles inside a published possession; its offsets are
computed from the possession's published heights, the ones the page reads.

`--check` rebuilds the file from bronze and compares its bytes, and runs `dribble.sql` (the query
"Reproduce it" shows) on the public raw files, comparing its figures with the file: `FULL n/n` when
both were done for all n matches, else `PARTIAL k/n` and what it checked.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from tracklab.bronze.common import raw_root_for
from tracklab.silver.orientation import M_PER_FT

SOURCE_ID = "opendata-basketball"
SQL_PATH = Path(__file__).with_name("dribble.sql")
SQL_MATCH_ID = "114086"  # the match the public SQL is written for, and the example's
SQL_NAMES = 2  # the events file and the tracking file

FPS = 25  # the provider's dictionary: `frame`, "Frame (at 25fps) of the dribble"
REACH = 5  # frames either side of the event
NEAR = 3  # frames: a lowest point this close to the event counts as near it
TOUCH_MIN = 3  # dribbles: a touch with this many or more is counted
SECONDS_DIGITS = 4
OFFSET_DIGITS = 4
PCT_DIGITS = 2
Z_DIGITS = 3
EXAMPLE_FILE = "bb_possessions_possession-114086-1-36.json"


# The arithmetic.


def lowest(z: dict[int, float], frame: int) -> tuple[int, float] | None:
    """The offset from `frame` to the lowest height within `REACH` frames, ties to the earliest,
    and that height; None when a frame of the window has no height."""
    window = [(z.get(frame + k), k) for k in range(-REACH, REACH + 1)]
    if any(h is None for h, _ in window):
        return None
    h, k = min((h, k) for h, k in window if h is not None)
    return k, h


def _q(values: list[float], q: float, digits: int) -> float | None:
    return round(float(np.quantile(values, q)), digits) if values else None


def _pct(flags: list[bool]) -> float | None:
    return round(100 * sum(flags) / len(flags), PCT_DIGITS) if flags else None


def match_figures(
    dribbles: list[tuple[str, str | None, int]], z: dict[int, float]
) -> dict[str, Any]:
    """Every figure of one match from its dribbles (id, touch, frame) and the ball's heights (m)
    by frame."""
    touches: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for did, touch, frame in dribbles:
        if touch is not None:
            touches[touch].append((frame, did))
    for frames in touches.values():
        frames.sort()
    intervals = [
        (b - a) / FPS
        for frames in touches.values()
        for (a, _), (b, _) in zip(frames, frames[1:], strict=False)
    ]
    low = {did: lowest(z, frame) for did, _, frame in dribbles}
    found = {did: v for did, v in low.items() if v is not None}
    offsets = [k for k, _ in found.values()]
    pairs = [
        (found[a], found[b], fa + found[a][0] == fb + found[b][0])
        for frames in touches.values()
        for (fa, a), (fb, b) in zip(frames, frames[1:], strict=False)
        if a in found and b in found
    ]
    return {
        "dribbles": len(dribbles),
        "intervals": len(intervals),
        "interval_median_s": _q(intervals, 0.5, SECONDS_DIGITS),
        "interval_p10_s": _q(intervals, 0.1, SECONDS_DIGITS),
        "interval_p90_s": _q(intervals, 0.9, SECONDS_DIGITS),
        "touches_3": sum(len(f) >= TOUCH_MIN for f in touches.values()),
        "windows": len(found),
        "offset_median": _q([float(k) for k in offsets], 0.5, OFFSET_DIGITS),
        "offset_abs_median": _q([float(abs(k)) for k in offsets], 0.5, OFFSET_DIGITS),
        "near_pct": _pct([abs(k) <= NEAR for k in offsets]),
        "edge_pct": _pct([abs(k) == REACH for k in offsets]),
        "low_z_median": _q([h for _, h in found.values()], 0.5, Z_DIGITS),
        "pairs": len(pairs),
        "shared_low": sum(shared for _, _, shared in pairs),
    }


# Reading bronze.


def read_match(bronze: Path, match: int) -> dict[str, Any]:
    con = duckdb.connect()
    dribbles = [
        (str(i), None if t is None else str(t), int(f))
        for i, t, f in con.execute(
            "SELECT id, touchId, frame FROM read_parquet(?) WHERE frame IS NOT NULL "
            "ORDER BY frame, id",
            [(bronze / "events_dribbles" / f"{match}.parquet").as_posix()],
        ).fetchall()
    ]
    z = {
        int(f): h * M_PER_FT
        for f, h in con.execute(
            "SELECT frameIdx, z FROM read_parquet(?) WHERE side = 'ball' AND z IS NOT NULL",
            [(bronze / "tracking_objects" / f"{match}.parquet").as_posix()],
        ).fetchall()
    }
    return match_figures(dribbles, z)


# The example: the touch with the most dribbles in a published possession, from its heights.


def example_figures(bronze: Path, possession: Path) -> dict[str, Any]:
    pos = json.loads(possession.read_text(encoding="utf-8"))
    native = int(pos["match"]["match_id"].removeprefix("bb:"))
    step = 1000 // FPS
    t_ms = [fr["t"] for fr in pos["frames"]]
    if any(b - a != step for a, b in zip(t_ms, t_ms[1:], strict=False)):
        raise ValueError(f"{possession.name}: the frames are not one {step} ms step apart")
    ball_i = next(e["i"] for e in pos["entities"] if e["kind"] == "ball")
    z: dict[int, float] = {}
    for fr in pos["frames"]:
        b = next((o for o in fr["o"] if o[0] == ball_i), None)
        if b is not None and b[3] is not None:
            z[fr["t"] // step] = b[3]
    f0, f1 = t_ms[0] // step, t_ms[-1] // step
    con = duckdb.connect()
    rows = con.execute(
        "SELECT touchId, frame, id FROM read_parquet(?) WHERE frame BETWEEN ? AND ? "
        "AND touchId IS NOT NULL ORDER BY frame, id",
        [(bronze / "events_dribbles" / f"{native}.parquet").as_posix(), f0 + REACH, f1 - REACH],
    ).fetchall()
    by_touch: dict[str, list[int]] = defaultdict(list)
    for touch, frame, _ in rows:
        by_touch[touch].append(int(frame))
    if not by_touch:
        raise ValueError(f"{possession.name}: no dribble of a touch inside the possession")
    # The most dribbles; ties to the earliest touch.
    touch = max(by_touch, key=lambda t: (len(by_touch[t]), -by_touch[t][0]))
    start, end = con.execute(
        "SELECT startFrame, endFrame FROM read_parquet(?) WHERE id = ?",
        [(bronze / "events_touches" / f"{native}.parquet").as_posix(), touch],
    ).fetchone() or (None, None)
    if start is None or end is None or not f0 <= start <= end <= f1:
        raise ValueError(f"{touch}: the touch is not inside {possession.name}")
    dribbles = []
    for frame in by_touch[touch]:
        found = lowest(z, frame)
        if found is None:
            raise ValueError(f"{touch}: the possession lacks the ball near frame {frame}")
        dribbles.append({"t": frame * step, "offset": found[0], "low_z": found[1]})
    return {
        "possession": possession.name,
        "match_id": pos["match"]["match_id"],
        "touch_id": touch,
        "t0": int(start) * step,
        "t1": int(end) * step,
        "dribbles": dribbles,
    }


def _matches(bronze: Path) -> list[int]:
    return sorted(int(p.stem) for p in (bronze / "events_dribbles").glob("*.parquet"))


def build(data_dir: Path, possessions: Path) -> dict[str, Any]:
    bronze = data_dir / "bronze" / "basketball"
    matches = _matches(bronze)
    if not matches:
        raise FileNotFoundError(f"no bronze events_dribbles under {bronze}")
    return {
        "schema_version": 1,
        "fps": FPS,
        "reach": REACH,
        "near": NEAR,
        "touch_min": TOUCH_MIN,
        "m_per_ft": M_PER_FT,
        "matches": [{"match_id": f"bb:{m}", **read_match(bronze, m)} for m in matches],
        "example": example_figures(bronze, possessions / EXAMPLE_FILE),
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# The public SQL, run on the raw files.

SQL_FIELDS = (
    "dribbles",
    "intervals",
    "interval_median_s",
    "interval_p10_s",
    "interval_p90_s",
    "touches_3",
    "windows",
    "offset_median",
    "offset_abs_median",
    "near_pct",
    "edge_pct",
    "low_z_median",
    "pairs",
    "shared_low",
)
COUNTS = {"dribbles", "intervals", "touches_3", "windows", "pairs", "shared_low"}


def read_sql() -> str:
    return SQL_PATH.read_bytes().decode("utf-8")


def match_sql(match_id: int) -> str:
    return read_sql().replace(SQL_MATCH_ID, str(match_id))


def run_sql(sql: str, match_dir: Path) -> tuple[Any, ...]:
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
    return tuple(
        None if v is None else int(v) if k in COUNTS else float(v)
        for k, v in zip(SQL_FIELDS, row, strict=True)
    )


def _raw_matches(data_dir: Path) -> Path | None:
    try:
        return raw_root_for(data_dir, SOURCE_ID) / "data" / "matches"
    except (FileNotFoundError, RuntimeError):
        return None


def run_learn_dribble(data_dir: Path, out: Path, possessions: Path, *, check: bool = False) -> int:
    if not check:
        text = render(build(data_dir, possessions))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"learn dribble: {out} ({out.stat().st_size} bytes)")
        return 0

    named = read_sql().count(SQL_MATCH_ID)
    if named != SQL_NAMES:
        print(f"learn dribble: dribble.sql names {SQL_MATCH_ID} {named} times, not {SQL_NAMES}")
        return 1
    raw_bytes = out.read_bytes()
    if b"\r" in raw_bytes:
        print(f"learn dribble --check: {out.name} has CR line ends")
        return 1
    on_disk = json.loads(raw_bytes.decode("utf-8"))
    rows = {m["match_id"]: m for m in on_disk["matches"]}
    total = len(rows)
    done: list[str] = []

    # 1. The bytes, rebuilt from bronze, when bronze holds every match the file was measured on.
    bronze = data_dir / "bronze" / "basketball"
    have = {f"bb:{m}" for m in _matches(bronze)} if (bronze / "events_dribbles").is_dir() else set()
    rebuilt = False
    if have == set(rows):
        if render(build(data_dir, possessions)).encode("utf-8") != raw_bytes:
            print(f"learn dribble --check: {out.name} differs from what bronze gives")
            return 1
        rebuilt = True
        done.append(f"the bytes of {out.name} rebuilt from bronze")
    elif have:
        # A slice (the CI fixtures): the code runs on it, but its figures are not the file's.
        for match in _matches(bronze):
            fig = read_match(bronze, match)
            print(f"learn dribble bb:{match} (bronze slice, not compared): {fig}")
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
        want = tuple(row[k] for k in SQL_FIELDS)
        compared += 1
        print(
            f"learn dribble {native}: "
            + " ".join(f"{k}={v}" for k, v in zip(SQL_FIELDS, got, strict=True))
            + f" ({'equal' if got == want else f'DIFFERENT, {out.name}: {want}'})"
        )
        if got != want:
            different.append(match_id)
    if different:
        print(f"learn dribble: {different} differ from {out.name}")
        return 1
    if compared:
        done.append(f"dribble.sql on the raw files of {compared} match(es)")

    shape = _shape_problems(on_disk)
    if shape:
        print(f"learn dribble --check: {shape}")
        return 1
    done.append(
        f"{out.name} has {total} matches with every field and counts that only shrink, and its "
        "example's dribbles sit inside its touch with an offset inside the window"
    )
    if rebuilt and compared == total:
        print(f"learn dribble --check: FULL {total}/{total}: " + "; ".join(done))
    else:
        k = compared if rebuilt else 0
        print(f"learn dribble --check: PARTIAL {k}/{total}: " + "; ".join(done))
    return 0


FIELDS = {"match_id", *SQL_FIELDS}


def _shape_problems(payload: dict[str, Any]) -> str:
    """What the file must hold whatever data is at hand."""
    for m in payload["matches"]:
        if set(m) != FIELDS:
            return f"{m.get('match_id')}: fields {sorted(set(m) ^ FIELDS)}"
        if not (m["dribbles"] >= m["windows"] >= m["pairs"] >= m["shared_low"]):
            return f"{m['match_id']}: a count grows somewhere"
        if m["dribbles"] < m["intervals"]:
            return f"{m['match_id']}: more intervals than dribbles"
    ex = payload["example"]
    for d in ex["dribbles"]:
        if not ex["t0"] <= d["t"] <= ex["t1"] or abs(d["offset"]) > payload["reach"]:
            return f"{ex['touch_id']}: a dribble outside its touch or its window"
    return ""
