"""Probe for lesson 8, "How fast does a pass travel?" (task 84). Read-only.

For each basketball match in bronze: the complete passes (`events_passes`, `complete`) with a
start, an end and a `distance` (ft; it is the passer-to-receiver distance of the event's two
locations). Of those, the ones whose end is after their start, and of those the ones with a ball
row (`tracking_objects`, side `ball`, x, y and z) at every frame from start to end. On those:
chord speed = `distance` in m / ((end - start) / 25 s); the ball's path, the sum of its 3D steps
from start to end, over the chord distance. Prints per match the counts, the median and p90 of
the chord speed (`quantile_cont`) and the median path / chord.

The event's chord is not the ball's: `passerLoc` and `receiverLoc` are where the two players stand
at the start frame (printed: the median distance from each to that player's tracked position
there), so `distance` is their gap when the pass starts. The probe also prints the ball's own
chord, its 3D displacement from start to end over the same time (median and p90), and the median
of the path over that displacement, which can only be 1 or more.

Decided before measuring: the lesson lives if in every match at least `MIN_SHARE` of the complete
passes with end after start have the ball at every frame, and at least `MIN_PASSES` remain.

    TRACKLAB_DATA_ROOT=... uv run python scripts/probe_learn_pass.py
"""

from __future__ import annotations

import duckdb

from tracklab.paths import data_root

FPS = 25
FT = 0.3048
MIN_SHARE = 0.9
MIN_PASSES = 100

SQL = f"""
WITH pass AS (
  SELECT id, startFrame AS f0, endFrame AS f1, distance * {FT} AS d
  FROM read_parquet($passes)
  WHERE complete AND startFrame IS NOT NULL AND endFrame IS NOT NULL AND distance IS NOT NULL
),
ball AS (
  SELECT frameIdx AS f, x * {FT} AS x, y * {FT} AS y, z * {FT} AS z
  FROM read_parquet($objects)
  WHERE side = 'ball' AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL
),
step AS (
  SELECT f, sqrt((x - lag(x) OVER w) ^ 2 + (y - lag(y) OVER w) ^ 2 + (z - lag(z) OVER w) ^ 2) AS s,
         f - lag(f) OVER w AS df
  FROM ball WINDOW w AS (ORDER BY f)
),
flight AS (
  SELECT pass.id, any_value(f1 - f0) AS frames, any_value(d) AS d, count(*) AS rows,
         sum(s) FILTER (WHERE step.f > f0 AND df = 1) AS path
  FROM pass JOIN step ON step.f BETWEEN f0 AND f1
  WHERE f1 > f0 GROUP BY pass.id
),
whole AS (SELECT * FROM flight WHERE rows = frames + 1),
ends AS (
  SELECT whole.*, sqrt((b1.x - b0.x) ^ 2 + (b1.y - b0.y) ^ 2 + (b1.z - b0.z) ^ 2) AS disp
  FROM whole JOIN pass USING (id) JOIN ball b0 ON b0.f = f0 JOIN ball b1 ON b1.f = f1
),
loc AS (
  SELECT median(sqrt((a.x - p.passerLoc_x) ^ 2 + (a.y - p.passerLoc_y) ^ 2)) AS passer,
         median(sqrt((r.x - p.receiverLoc_x) ^ 2 + (r.y - p.receiverLoc_y) ^ 2)) AS receiver
  FROM read_parquet($passes) p
  JOIN read_parquet($objects) a ON a.frameIdx = p.startFrame AND a.playerId = p.passerId
  JOIN read_parquet($objects) r ON r.frameIdx = p.startFrame AND r.playerId = p.receiverId
  WHERE p.complete
)
SELECT (SELECT count(*) FROM pass),
       (SELECT count(*) FROM pass WHERE f1 > f0),
       (SELECT count(*) FROM whole),
       (SELECT quantile_cont(d / (frames / {FPS}), 0.5) FROM whole),
       (SELECT quantile_cont(d / (frames / {FPS}), 0.9) FROM whole),
       (SELECT quantile_cont(path / d, 0.5) FROM whole WHERE d > 0),
       (SELECT quantile_cont(disp / (frames / {FPS}), 0.5) FROM ends),
       (SELECT quantile_cont(disp / (frames / {FPS}), 0.9) FROM ends),
       (SELECT quantile_cont(path / disp, 0.5) FROM ends WHERE disp > 0),
       (SELECT passer FROM loc), (SELECT receiver FROM loc)
"""


def main() -> int:
    bronze = data_root() / "bronze" / "basketball"
    paths = sorted((bronze / "events_passes").glob("*.parquet"))
    con = duckdb.connect()
    alive = bool(paths)
    print("probe pass: complete passes, end after start, ball at every frame of the flight")
    print(
        "match   complete  end>start  whole  share  | event chord: med  p90  path/chord "
        "| ball chord: med  p90  path/chord | loc to player ft: passer receiver"
    )
    for p in paths:
        objects = bronze / "tracking_objects" / p.name
        params = {"passes": p.as_posix(), "objects": objects.as_posix()}
        row = con.execute(SQL, params).fetchone()
        n, forward, whole, med, p90, ratio, b_med, b_p90, b_ratio, at_passer, at_receiver = row
        share = whole / forward if forward else 0.0
        print(
            f"{p.stem}  {n:>8}  {forward:>9}  {whole:>5}  {share:.3f}"
            f"  |  {med:.2f}  {p90:.2f}  {ratio:.4f}  |  {b_med:.2f}  {b_p90:.2f}  {b_ratio:.4f}"
            f"  |  {at_passer:.4f}  {at_receiver:.4f}"
        )
        alive &= share >= MIN_SHARE and whole >= MIN_PASSES
    verdict = "VIVE" if alive else "MUERE"
    print(
        f"probe pass: {verdict} ({len(paths)} matches; each needs a share >= {MIN_SHARE} "
        f"and >= {MIN_PASSES} passes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
