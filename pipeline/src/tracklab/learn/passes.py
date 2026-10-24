"""`tracklab learn pass`: how fast does a pass travel (lesson 7, P9)?

The provider's passes carry a `distance`, which its dictionary defines as the distance in feet
between `passerLoc` and `receiverLoc`, the passer's and the receiver's positions at the release
of the pass. It is not what the ball covers: the ball leaves the passer's hands and reaches the
receiver's. So the lesson takes the pass's chord from the ball itself: its 3D displacement from
where it is at `startFrame` to where it is at `endFrame`, over the pass's time.

Per match, from bronze `events_passes` and the ball rows of `tracking_objects` (feet, to metres):
the complete passes with a start, an end and a `distance`; of those, the ones that end after they
start; of those, the ones with the ball at every frame from start to end (`n`). On those: the
median and 90th percentile of the chord speed (linear interpolation, as DuckDB's
`quantile_cont`), the median of the ball's path (the sum of its 3D steps) over its chord, the
median of `distance` over the same time, and the median of the chord over `distance`. And, for
`distance` itself: on how many of the `n` passes both players are tracked at the start frame, and
the largest gap between `distance` and their tracked separation there.

The example is every complete pass of the published possession the public SQL's match is shown
with; its chord, path and times are computed from the possession's published positions.

`--check` rebuilds the file from bronze and compares its bytes, and runs `pass.sql` (the query
"Reproduce it" shows) on the public raw files, comparing its six figures with the file: `FULL n/n`
when both were done for all n matches, else `PARTIAL k/n` and what it checked.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from tracklab.bronze.common import raw_root_for
from tracklab.silver.orientation import M_PER_FT

SOURCE_ID = "opendata-basketball"
SQL_PATH = Path(__file__).with_name("pass.sql")
SQL_MATCH_ID = "114099"  # the match the public SQL is written for, and the example's
SQL_NAMES = 2  # the events file and the tracking file

FPS = 25  # the provider's dictionary: `startFrame`, "Frame (at 25fps)"
SPEED_DIGITS = 2
RATIO_DIGITS = 4
EXAMPLE_FILE = "bb_possessions_possession-114099-1-41.json"

Point = tuple[float, float, float]


# The arithmetic.


def chord(a: Point, b: Point) -> float:
    return math.dist(a, b)


def path(points: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))


def pass_figures(points: list[Point], frames: int, distance_m: float) -> dict[str, float]:
    """One pass from its ball positions at every frame from start to end."""
    seconds = frames / FPS
    c = chord(points[0], points[-1])
    return {
        "chord_speed": c / seconds,
        "path_over_chord": path(points) / c if c > 0 else math.nan,
        "distance_speed": distance_m / seconds,
        "chord_over_distance": c / distance_m if distance_m > 0 else math.nan,
    }


def _q(values: list[float], q: float, digits: int) -> float | None:
    kept = [v for v in values if not math.isnan(v)]
    return round(float(np.quantile(kept, q)), digits) if kept else None


# Reading bronze.


def read_match(bronze: Path, match: int) -> dict[str, Any]:
    con = duckdb.connect()
    passes = con.execute(
        "SELECT id, startFrame, endFrame, distance * ?, passerId, receiverId "
        "FROM read_parquet(?) WHERE complete AND startFrame IS NOT NULL AND endFrame IS NOT NULL "
        "AND distance IS NOT NULL ORDER BY startFrame, id",
        [M_PER_FT, (bronze / "events_passes" / f"{match}.parquet").as_posix()],
    ).fetchall()
    objects = (bronze / "tracking_objects" / f"{match}.parquet").as_posix()
    ball: dict[int, Point] = {
        int(f): (x * M_PER_FT, y * M_PER_FT, z * M_PER_FT)
        for f, x, y, z in con.execute(
            "SELECT frameIdx, x, y, z FROM read_parquet(?) WHERE side = 'ball' "
            "AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL",
            [objects],
        ).fetchall()
    }
    forward = [p for p in passes if p[2] > p[1]]
    whole = [p for p in forward if all(f in ball for f in range(p[1], p[2] + 1))]
    figures = [
        pass_figures([ball[f] for f in range(f0, f1 + 1)], f1 - f0, d)
        for _, f0, f1, d, _, _ in whole
    ]
    starts = sorted({p[1] for p in whole})
    at: dict[tuple[int, int], tuple[float, float]] = {
        (int(f), int(pid)): (x * M_PER_FT, y * M_PER_FT)
        for f, pid, x, y in con.execute(
            "SELECT frameIdx, playerId, x, y FROM read_parquet(?) "
            "WHERE side <> 'ball' AND list_contains(?, frameIdx)",
            [objects, starts],
        ).fetchall()
    }
    gaps = [
        abs(d - math.dist(at[(f0, a)], at[(f0, b)]))
        for _, f0, _, d, a, b in whole
        if (f0, a) in at and (f0, b) in at
    ]
    by = {k: [f[k] for f in figures] for k in figures[0]} if figures else {}
    return {
        "complete": len(passes),
        "forward": len(forward),
        "n": len(whole),
        "chord_speed_median": _q(by.get("chord_speed", []), 0.5, SPEED_DIGITS),
        "chord_speed_p90": _q(by.get("chord_speed", []), 0.9, SPEED_DIGITS),
        "path_over_chord": _q(by.get("path_over_chord", []), 0.5, RATIO_DIGITS),
        "distance_speed_median": _q(by.get("distance_speed", []), 0.5, SPEED_DIGITS),
        "chord_over_distance": _q(by.get("chord_over_distance", []), 0.5, RATIO_DIGITS),
        "separation_n": len(gaps),
        "separation_gap_max": round(max(gaps), RATIO_DIGITS) if gaps else None,
    }


# The example: the passes of a published possession, from its published positions.


def example_figures(bronze: Path, possession: Path) -> dict[str, Any]:
    pos = json.loads(possession.read_text(encoding="utf-8"))
    native = int(pos["match"]["match_id"].removeprefix("bb:"))
    t_ms = [fr["t"] for fr in pos["frames"]]
    step = 1000 // FPS
    if any(b - a != step for a, b in zip(t_ms, t_ms[1:], strict=False)):
        raise ValueError(f"{possession.name}: the frames are not one {step} ms step apart")
    index = {e["entity_id"]: e["i"] for e in pos["entities"]}
    ball_i = next(e["i"] for e in pos["entities"] if e["kind"] == "ball")
    rows = (
        duckdb.connect()
        .execute(
            "SELECT id, startFrame, endFrame, distance * ?, passerId, receiverId "
            "FROM read_parquet(?) WHERE complete AND startFrame IS NOT NULL "
            "AND endFrame IS NOT NULL AND distance IS NOT NULL AND endFrame > startFrame "
            "AND startFrame * ? BETWEEN ? AND ? AND endFrame * ? <= ? ORDER BY startFrame, id",
            [
                M_PER_FT,
                (bronze / "events_passes" / f"{native}.parquet").as_posix(),
                step,
                t_ms[0],
                t_ms[-1],
                step,
                t_ms[-1],
            ],
        )
        .fetchall()
    )
    by_t = {fr["t"]: {o[0]: o for o in fr["o"]} for fr in pos["frames"]}
    passes = []
    for pid, f0, f1, d, passer, receiver in rows:
        points: list[Point] = []
        for f in range(f0, f1 + 1):
            b = by_t[f * step].get(ball_i)
            if b is None or b[3] is None:
                raise ValueError(f"{pid}: the possession lacks the ball at frame {f}")
            points.append((b[1], b[2], b[3]))
        fig = pass_figures(points, f1 - f0, d)
        passes.append(
            {
                "pass_id": pid,
                "t0": f0 * step,
                "t1": f1 * step,
                "frames": f1 - f0,
                "distance_m": round(d, RATIO_DIGITS),
                "passer": index[f"bb:{passer}"],
                "receiver": index[f"bb:{receiver}"],
                "chord_m": round(chord(points[0], points[-1]), RATIO_DIGITS),
                "path_m": round(path(points), RATIO_DIGITS),
                "chord_speed": round(fig["chord_speed"], SPEED_DIGITS),
            }
        )
    if not passes:
        raise ValueError(f"{possession.name}: no complete pass with the ball at every frame")
    return {"possession": possession.name, "match_id": pos["match"]["match_id"], "passes": passes}


def _matches(bronze: Path) -> list[int]:
    return sorted(int(p.stem) for p in (bronze / "events_passes").glob("*.parquet"))


def build(data_dir: Path, possessions: Path) -> dict[str, Any]:
    bronze = data_dir / "bronze" / "basketball"
    matches = _matches(bronze)
    if not matches:
        raise FileNotFoundError(f"no bronze events_passes under {bronze}")
    return {
        "schema_version": 1,
        "fps": FPS,
        "m_per_ft": M_PER_FT,
        "matches": [{"match_id": f"bb:{m}", **read_match(bronze, m)} for m in matches],
        "example": example_figures(bronze, possessions / EXAMPLE_FILE),
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# The public SQL, run on the raw files.

SQL_FIELDS = (
    "n",
    "chord_speed_median",
    "chord_speed_p90",
    "path_over_chord",
    "distance_speed_median",
    "chord_over_distance",
)


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
    return (int(row[0]), *(None if v is None else float(v) for v in row[1:]))


def _raw_matches(data_dir: Path) -> Path | None:
    try:
        return raw_root_for(data_dir, SOURCE_ID) / "data" / "matches"
    except (FileNotFoundError, RuntimeError):
        return None


def run_learn_pass(data_dir: Path, out: Path, possessions: Path, *, check: bool = False) -> int:
    if not check:
        text = render(build(data_dir, possessions))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"learn pass: {out} ({out.stat().st_size} bytes)")
        return 0

    named = read_sql().count(SQL_MATCH_ID)
    if named != SQL_NAMES:
        print(f"learn pass: pass.sql names {SQL_MATCH_ID} {named} times, not {SQL_NAMES}")
        return 1
    raw_bytes = out.read_bytes()
    if b"\r" in raw_bytes:
        print(f"learn pass --check: {out.name} has CR line ends")
        return 1
    on_disk = json.loads(raw_bytes.decode("utf-8"))
    rows = {m["match_id"]: m for m in on_disk["matches"]}
    total = len(rows)
    done: list[str] = []

    # 1. The bytes, rebuilt from bronze, when bronze holds every match the file was measured on.
    bronze = data_dir / "bronze" / "basketball"
    have = {f"bb:{m}" for m in _matches(bronze)} if (bronze / "events_passes").is_dir() else set()
    rebuilt = False
    if have == set(rows):
        if render(build(data_dir, possessions)).encode("utf-8") != raw_bytes:
            print(f"learn pass --check: {out.name} differs from what bronze gives")
            return 1
        rebuilt = True
        done.append(f"the bytes of {out.name} rebuilt from bronze")
    elif have:
        # A slice (the CI fixtures): the code runs on it, but its figures are not the file's.
        for match in _matches(bronze):
            fig = read_match(bronze, match)
            print(f"learn pass bb:{match} (bronze slice, not compared): {fig}")
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
            f"learn pass {native}: "
            + " ".join(f"{k}={v}" for k, v in zip(SQL_FIELDS, got, strict=True))
            + f" ({'equal' if got == want else f'DIFFERENT, {out.name}: {want}'})"
        )
        if got != want:
            different.append(match_id)
    if different:
        print(f"learn pass: {different} differ from {out.name}")
        return 1
    if compared:
        done.append(f"pass.sql on the raw files of {compared} match(es)")

    shape = _shape_problems(on_disk)
    if shape:
        print(f"learn pass --check: {shape}")
        return 1
    done.append(
        f"{out.name} has {total} matches with every field and a selection that only shrinks, and "
        "its example's chords, paths and speeds agree with one another"
    )
    if rebuilt and compared == total:
        print(f"learn pass --check: FULL {total}/{total}: " + "; ".join(done))
    else:
        k = compared if rebuilt else 0
        print(f"learn pass --check: PARTIAL {k}/{total}: " + "; ".join(done))
    return 0


FIELDS = {"match_id", "complete", "forward", *SQL_FIELDS, "separation_n", "separation_gap_max"}


def _shape_problems(payload: dict[str, Any]) -> str:
    """What the file must hold whatever data is at hand."""
    for m in payload["matches"]:
        if set(m) != FIELDS:
            return f"{m.get('match_id')}: fields {sorted(set(m) ^ FIELDS)}"
        if not m["complete"] >= m["forward"] >= m["n"] >= m["separation_n"]:
            return f"{m['match_id']}: the selection grows somewhere"
        if m["path_over_chord"] is not None and m["path_over_chord"] < 1:
            return f"{m['match_id']}: a path shorter than its chord"
    for p in payload["example"]["passes"]:
        if p["path_m"] < p["chord_m"]:
            return f"{p['pass_id']}: a path shorter than its chord"
        speed = round(p["chord_m"] / (p["frames"] / FPS), SPEED_DIGITS)
        if abs(speed - p["chord_speed"]) > 10**-SPEED_DIGITS:
            return f"{p['pass_id']}: its chord speed is not its chord over its time"
    return ""
