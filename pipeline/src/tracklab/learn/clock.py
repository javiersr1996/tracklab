"""`tracklab learn clock`: does the game clock keep the video's time (lesson 6, P9)?

Every basketball frame carries two clocks from the provider: `wallClock`, milliseconds since the
start of the video, and `gameClock`, the seconds left in the period, with `gameClockStopped`
saying whether it runs. Where it runs, a clock that keeps the video's time counts down one second
per second: against `wallClock` it is a line of slope -1. Per match, from bronze `tracking_frames`:

- the segments: runs of consecutive `frameIdx` inside one period with `gameClockStopped` false and
  a `gameClock`, of at least `MIN_FRAMES` (5 s at 25 fps);
- in each, the least-squares slope of `gameClock` (s) on `wallClock` (s), fitted about the
  segment's mean time (the slope does not depend on the origin; the arithmetic does);
- the number of segments, their frames, their one-frame steps and how many of those steps leave
  `gameClock` where it was (`held`); the median, Q1 and Q3 of the slopes (linear interpolation,
  as DuckDB's `quantile_cont`) at `DIGITS` decimals.

The lesson's figure fits the clock of two published possessions; their files carry the clock but
not its flag, so the file also gives, for each, the stretches of the possession (by `wallClock`,
the possession's `t`) where the flag says the clock is stopped.

`--check` rebuilds the file from bronze and compares its bytes, and runs `clock.sql` (the query
"Reproduce it" shows) on the public raw files, comparing its six figures with the file: `FULL n/n`
when both were done for all n matches, else `PARTIAL k/n` and what it checked.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import numpy.typing as npt

from tracklab.bronze.common import raw_root_for
from tracklab.publish.possessions import ROUND_NDIGITS
from tracklab.quality.gravity import CALIBRATION

SOURCE_ID = "opendata-basketball"
SQL_PATH = Path(__file__).with_name("clock.sql")
SQL_MATCH_ID = "114086"  # the match the public SQL is written for

FPS = 25  # the provider's dictionary: `frameIdx`, "Frame count (at 25fps)"
MIN_FRAMES = 5 * FPS
DIGITS = 5
# The figure's two possessions: one of a calibration match, one of a control match.
EXAMPLES = (
    "bb_possessions_possession-114086-1-36.json",
    "bb_possessions_possession-184439-2-38.json",
)

Floats = npt.NDArray[np.float64]


# The arithmetic.


def slope(t: Floats, clock: Floats) -> float:
    """The least-squares slope of `clock` on `t`, about the mean of `t`."""
    dt = t - t.mean()
    return float(np.sum(dt * (clock - clock.mean())) / np.sum(dt * dt))


def segments(period: npt.NDArray[np.int64], frame: npt.NDArray[np.int64]) -> list[slice]:
    """The runs of consecutive frames inside one period, rows sorted by period and frame, of at
    least `MIN_FRAMES`."""
    breaks = np.flatnonzero((np.diff(frame) != 1) | (np.diff(period) != 0)) + 1
    starts = np.concatenate([[0], breaks])
    ends = np.concatenate([breaks, [len(frame)]])
    return [slice(int(a), int(b)) for a, b in zip(starts, ends, strict=True) if b - a >= MIN_FRAMES]


def match_figures(
    period: npt.NDArray[np.int64], frame: npt.NDArray[np.int64], t: Floats, clock: Floats
) -> dict[str, Any]:
    runs = segments(period, frame)
    slopes = np.array([slope(t[r], clock[r]) for r in runs])
    frames = sum(r.stop - r.start for r in runs)
    held = sum(int(np.sum(np.diff(clock[r]) == 0)) for r in runs)
    q1, med, q3 = (
        round(float(np.quantile(slopes, q)), DIGITS) if runs else None for q in (0.25, 0.5, 0.75)
    )
    return {
        "segments": len(runs),
        "frames": frames,
        "steps": frames - len(runs),
        "held": held,
        "slope_median": med,
        "slope_q1": q1,
        "slope_q3": q3,
    }


# Reading bronze.


def read_running(path: Path) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64], Floats, Floats]:
    """(period, frameIdx, wallClock in s, gameClock in s) of every frame with the clock running,
    sorted by period and frame. A frame with no period sorts first, as one period of its own."""
    rows = (
        duckdb.connect()
        .execute(
            "SELECT coalesce(period, -1) AS period, frameIdx, wallClock, gameClock "
            "FROM read_parquet(?) WHERE gameClockStopped = false AND gameClock IS NOT NULL "
            "ORDER BY period, frameIdx",
            [path.as_posix()],
        )
        .fetchnumpy()
    )
    return (
        np.asarray(rows["period"], np.int64),
        np.asarray(rows["frameIdx"], np.int64),
        np.asarray(rows["wallClock"], np.float64) / 1000.0,
        np.asarray(rows["gameClock"], np.float64),
    )


def example_figures(bronze: Path, possession: Path) -> dict[str, Any]:
    """Where the flag says the clock is stopped during a published possession, joined to bronze
    by `wallClock`; the join is right only if the published clock is bronze's, rounded."""
    pos = json.loads(possession.read_text(encoding="utf-8"))
    native = int(pos["match"]["match_id"].removeprefix("bb:"))
    t_ms = [fr["t"] for fr in pos["frames"]]
    rows = (
        duckdb.connect()
        .execute(
            "SELECT wallClock, gameClock, gameClockStopped FROM read_parquet(?) "
            "WHERE wallClock BETWEEN ? AND ? ORDER BY wallClock",
            [(bronze / "tracking_frames" / f"{native}.parquet").as_posix(), t_ms[0], t_ms[-1]],
        )
        .fetchall()
    )
    if [r[0] for r in rows] != t_ms:
        raise ValueError(f"{possession.name}: its frames are not bronze's frames")
    published = [fr["clock"] for fr in pos["frames"]]
    if any(round(r[1], ROUND_NDIGITS) != c for r, c in zip(rows, published, strict=True)):
        raise ValueError(f"{possession.name}: its clock is not bronze's, rounded")
    stopped: list[list[int]] = []
    for wall, _, is_stopped in rows:
        if not is_stopped:
            continue
        if stopped and stopped[-1][1] == wall - 1000 // FPS:
            stopped[-1][1] = wall
        else:
            stopped.append([wall, wall])
    return {
        "possession": possession.name,
        "match_id": pos["match"]["match_id"],
        "calibration": native in CALIBRATION,
        "frames": len(t_ms),
        "stopped": stopped,
    }


def _matches(bronze: Path) -> list[int]:
    return sorted(int(p.stem) for p in (bronze / "tracking_frames").glob("*.parquet"))


def build(data_dir: Path, possessions: Path) -> dict[str, Any]:
    bronze = data_dir / "bronze" / "basketball"
    matches = _matches(bronze)
    if not matches:
        raise FileNotFoundError(f"no bronze tracking_frames under {bronze}")
    rows = [
        {
            "match_id": f"bb:{m}",
            "calibration": m in CALIBRATION,
            **match_figures(*read_running(bronze / "tracking_frames" / f"{m}.parquet")),
        }
        for m in matches
    ]
    return {
        "schema_version": 1,
        "fps": FPS,
        "min_frames": MIN_FRAMES,
        "digits": DIGITS,
        "matches": rows,
        "examples": [example_figures(bronze, possessions / name) for name in EXAMPLES],
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# The public SQL, run on the raw files.

SQL_FIELDS = ("segments", "frames", "held", "slope_median", "slope_q1", "slope_q3")


def read_sql() -> str:
    return SQL_PATH.read_bytes().decode("utf-8")


def match_sql(match_id: int) -> str:
    return read_sql().replace(SQL_MATCH_ID, str(match_id))


def run_sql(sql: str, match_dir: Path) -> tuple[Any, ...]:
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
    return (int(row[0]), int(row[1]), int(row[2]), float(row[3]), float(row[4]), float(row[5]))


def _raw_matches(data_dir: Path) -> Path | None:
    try:
        return raw_root_for(data_dir, SOURCE_ID) / "data" / "matches"
    except (FileNotFoundError, RuntimeError):
        return None


def run_learn_clock(data_dir: Path, out: Path, possessions: Path, *, check: bool = False) -> int:
    if not check:
        text = render(build(data_dir, possessions))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"learn clock: {out} ({out.stat().st_size} bytes)")
        return 0

    if read_sql().count(SQL_MATCH_ID) != 1:
        print(f"learn clock: clock.sql does not name {SQL_MATCH_ID} exactly once")
        return 1
    raw_bytes = out.read_bytes()
    if b"\r" in raw_bytes:
        print(f"learn clock --check: {out.name} has CR line ends")
        return 1
    on_disk = json.loads(raw_bytes.decode("utf-8"))
    rows = {m["match_id"]: m for m in on_disk["matches"]}
    total = len(rows)
    done: list[str] = []

    # 1. The bytes, rebuilt from bronze, when bronze holds every match the file was measured on.
    bronze = data_dir / "bronze" / "basketball"
    have = {f"bb:{m}" for m in _matches(bronze)} if (bronze / "tracking_frames").is_dir() else set()
    rebuilt = False
    if have == set(rows):
        if render(build(data_dir, possessions)).encode("utf-8") != raw_bytes:
            print(f"learn clock --check: {out.name} differs from what bronze gives")
            return 1
        rebuilt = True
        done.append(f"the bytes of {out.name} rebuilt from bronze")
    elif have:
        # A slice (the CI fixtures): the code runs on it, but its figures are not the file's.
        for match in _matches(bronze):
            fig = match_figures(*read_running(bronze / "tracking_frames" / f"{match}.parquet"))
            print(f"learn clock bb:{match} (bronze slice, not compared): {fig}")
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
            f"learn clock {native}: "
            + " ".join(f"{k}={v}" for k, v in zip(SQL_FIELDS, got, strict=True))
            + f" ({'equal' if got == want else f'DIFFERENT, {out.name}: {want}'})"
        )
        if got != want:
            different.append(match_id)
    if different:
        print(f"learn clock: {different} differ from {out.name}")
        return 1
    if compared:
        done.append(f"clock.sql on the raw files of {compared} match(es)")

    shape = _shape_problems(on_disk)
    if shape:
        print(f"learn clock --check: {shape}")
        return 1
    done.append(
        f"{out.name} has {total} matches with every field, steps = frames - segments, held <= "
        f"steps, Q1 <= median <= Q3 and the calibration flags of P3, and its {len(EXAMPLES)} "
        "examples' stops lie inside their possessions"
    )
    if rebuilt and compared == total:
        print(f"learn clock --check: FULL {total}/{total}: " + "; ".join(done))
    else:
        k = compared if rebuilt else 0
        print(f"learn clock --check: PARTIAL {k}/{total}: " + "; ".join(done))
    return 0


FIELDS = {"match_id", "calibration", *SQL_FIELDS, "steps"}


def _shape_problems(payload: dict[str, Any]) -> str:
    """What the file must hold whatever data is at hand."""
    for m in payload["matches"]:
        if set(m) != FIELDS:
            return f"{m.get('match_id')}: fields {sorted(set(m) ^ FIELDS)}"
        if m["steps"] != m["frames"] - m["segments"] or not 0 <= m["held"] <= m["steps"]:
            return f"{m['match_id']}: the steps do not add up"
        if not m["slope_q1"] <= m["slope_median"] <= m["slope_q3"]:
            return f"{m['match_id']}: the quartiles are out of order"
        if m["calibration"] != (int(m["match_id"].removeprefix("bb:")) in CALIBRATION):
            return f"{m['match_id']}: the calibration flag is not P3's"
    for ex in payload["examples"]:
        span = ex["frames"]
        if any(b < a or (b - a) // (1000 // FPS) + 1 > span for a, b in ex["stopped"]):
            return f"{ex['possession']}: a stop does not fit the possession"
    return ""
