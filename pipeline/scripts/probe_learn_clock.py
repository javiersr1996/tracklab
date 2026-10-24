"""Probe for lesson 6, "Does the game clock keep the video's time?" (task 84). Read-only.

For each basketball match in bronze `tracking_frames`: the runs of frames with the game clock
running (`gameClockStopped` false, a `gameClock`) and consecutive `frameIdx` inside one period, of
at least `MIN_FRAMES` (5 s at 25 fps); in each run, the least-squares slope of `gameClock` (s) on
`wallClock` (ms, so / 1000). Per match: runs, frames in them, and the median, Q1 and Q3 of the
slope (`quantile_cont`, the linear interpolation of `statistics.quantiles(method="inclusive")`).
A clock that keeps the video's time counts down one second per second: slope -1.

Decided before measuring: the lesson lives if every match has at least `MIN_RUNS` runs, enough for
a median and quartiles per match.

    TRACKLAB_DATA_ROOT=... uv run python scripts/probe_learn_clock.py
"""

from __future__ import annotations

import duckdb

from tracklab.paths import data_root
from tracklab.quality.gravity import CALIBRATION

MIN_FRAMES = 125
MIN_RUNS = 10

SQL = """
WITH running AS (
  SELECT period, frameIdx, wallClock / 1000.0 AS t, gameClock AS clock,
         frameIdx - row_number() OVER (PARTITION BY period ORDER BY frameIdx) AS run
  FROM read_parquet(?)
  WHERE gameClockStopped = false AND gameClock IS NOT NULL
),
runs AS (
  SELECT period, run, count(*) AS frames, regr_slope(clock, t) AS slope
  FROM running GROUP BY period, run HAVING count(*) >= ?
)
SELECT count(*), sum(frames),
       quantile_cont(slope, 0.5), quantile_cont(slope, 0.25), quantile_cont(slope, 0.75)
FROM runs
"""


def main() -> int:
    folder = data_root() / "bronze" / "basketball" / "tracking_frames"
    paths = sorted(folder.glob("*.parquet"))
    con = duckdb.connect()
    alive = bool(paths)
    print(f"probe clock: runs of >= {MIN_FRAMES} frames with the game clock running")
    print("match   kind         runs  frames   median     Q1         Q3")
    for p in paths:
        runs, frames, med, q1, q3 = con.execute(SQL, [p.as_posix(), MIN_FRAMES]).fetchone()
        kind = "calibration" if int(p.stem) in CALIBRATION else "control"
        print(f"{p.stem}  {kind:<11}  {runs:>4}  {frames:>6}  {med:.5f}  {q1:.5f}  {q3:.5f}")
        alive &= runs >= MIN_RUNS
    verdict = "VIVE" if alive else "MUERE"
    print(f"probe clock: {verdict} ({len(paths)} matches; every one needs >= {MIN_RUNS} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
