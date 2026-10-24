"""Probe for lesson 10, "How many bounces per second?" (task 84). Read-only.

For each basketball match in bronze `events_dribbles` (one row per dribble, with its `frame` and
the `touchId` of the touch it belongs to): the intervals between consecutive dribbles of one touch
(frames / 25 s), their count, median, p10 and p90 (`quantile_cont`), and the touches with three
dribbles or more. Then the two sources side by side: for every dribble whose ball rows
(`tracking_objects`, side `ball`) cover all `2 * REACH + 1` frames around its `frame`, the offset
from the event's frame to the lowest ball z in that window (ties to the earliest), the median of
the offset and of its absolute value, and the share of dribbles whose lowest z is at the window's
edge (no minimum inside it).

Decided before measuring: the lesson lives if in every match the median absolute offset is at most
`MAX_OFFSET` frames.

    TRACKLAB_DATA_ROOT=... uv run python scripts/probe_learn_dribble.py
"""

from __future__ import annotations

import duckdb

from tracklab.paths import data_root

FPS = 25
REACH = 5
MAX_OFFSET = 3

SQL = f"""
WITH d AS (
  SELECT id, touchId, frame FROM read_parquet($dribbles) WHERE frame IS NOT NULL
),
gap AS (
  SELECT (frame - lag(frame) OVER (PARTITION BY touchId ORDER BY frame)) / {FPS} AS s
  FROM d WHERE touchId IS NOT NULL
),
ball AS (
  SELECT frameIdx AS f, z FROM read_parquet($objects) WHERE side = 'ball' AND z IS NOT NULL
),
near AS (
  SELECT d.id, ball.f - d.frame AS k, ball.z FROM d JOIN ball
  ON ball.f BETWEEN d.frame - {REACH} AND d.frame + {REACH}
),
low AS (
  SELECT id, arg_min(k, [z, k]) AS k
  FROM near GROUP BY id HAVING count(*) = {2 * REACH + 1}
)
SELECT (SELECT count(s) FROM gap),
       (SELECT quantile_cont(s, 0.5) FROM gap),
       (SELECT quantile_cont(s, 0.1) FROM gap),
       (SELECT quantile_cont(s, 0.9) FROM gap),
       (SELECT count(*) FROM (SELECT touchId FROM d WHERE touchId IS NOT NULL
                              GROUP BY touchId HAVING count(*) >= 3)),
       (SELECT count(*) FROM d),
       (SELECT count(*) FROM low),
       (SELECT quantile_cont(k, 0.5) FROM low),
       (SELECT quantile_cont(abs(k), 0.5) FROM low),
       (SELECT avg((abs(k) <= {MAX_OFFSET})::INT) FROM low),
       (SELECT avg((abs(k) = {REACH})::INT) FROM low)
"""


def main() -> int:
    bronze = data_root() / "bronze" / "basketball"
    paths = sorted((bronze / "events_dribbles").glob("*.parquet"))
    con = duckdb.connect()
    alive = bool(paths)
    print(f"probe dribble: intervals within a touch; lowest ball z within +-{REACH} frames")
    print(
        "match   intervals  median_s  p10_s  p90_s  touches>=3 | dribbles  windows  "
        f"offset_med  |offset|_med  share<={MAX_OFFSET}  at_edge"
    )
    for p in paths:
        params = {
            "dribbles": p.as_posix(),
            "objects": (bronze / "tracking_objects" / p.name).as_posix(),
        }
        n, med, p10, p90, touches, dribbles, windows, k_med, k_abs, near, edge = con.execute(
            SQL, params
        ).fetchone()
        print(
            f"{p.stem}  {n:>9}  {med:>8.2f}  {p10:>5.2f}  {p90:>5.2f}  {touches:>10} | "
            f"{dribbles:>8}  {windows:>7}  {k_med:>10.1f}  {k_abs:>12.1f}  {near:>8.3f}  {edge:.3f}"
        )
        alive &= k_abs <= MAX_OFFSET
    verdict = "VIVE" if alive else "MUERE"
    print(
        f"probe dribble: {verdict} ({len(paths)} matches; each needs a median |offset| "
        f"<= {MAX_OFFSET} frames)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
