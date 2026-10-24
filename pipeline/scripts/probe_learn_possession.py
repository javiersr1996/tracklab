"""Probe for lesson 11, "How often does possession change hands?" (task 84). Read-only.

Football: the matches of bronze `phases_of_play` that are not held out by the fence
(`web/lib/learn/fence.json`), reading only `index, frame_start, frame_end, period,
team_in_possession_id` (never a width, a length or any other column). A run is a stretch of
consecutive phases (by `index`) of one period with the same team in possession; it spans from its
first `frame_start` to its last `frame_end`, at 10 Hz (`docs/formats/football.md`). Per match:
phases, runs, median and p90 of the run in s (`quantile_cont`) and the share of runs that span more
than one phase.

Basketball: bronze `events_possessions`, one row per possession, from `startFrame` to `endFrame`
at 25 fps. Per match: possessions, median and p90 in s.

Decided before measuring: the lesson lives if every match of both sports has at least `MIN_UNITS`
runs or possessions.

    TRACKLAB_DATA_ROOT=... uv run python scripts/probe_learn_possession.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from tracklab.paths import data_root

FOOTBALL_HZ = 10
BASKETBALL_FPS = 25
MIN_UNITS = 50
FENCE = Path(__file__).resolve().parents[2] / "web" / "lib" / "learn" / "fence.json"

FOOTBALL = f"""
WITH phase AS (
  SELECT index, frame_start, frame_end, period, team_in_possession_id AS team
  FROM read_parquet($path)
),
marked AS (
  SELECT *, (team IS DISTINCT FROM lag(team) OVER w)::INT AS starts FROM phase
  WINDOW w AS (PARTITION BY period ORDER BY index)
),
numbered AS (
  SELECT *, sum(starts) OVER (PARTITION BY period ORDER BY index) AS run FROM marked
),
runs AS (
  SELECT period, run, count(*) AS phases, (max(frame_end) - min(frame_start)) / {FOOTBALL_HZ} AS s
  FROM numbered WHERE team IS NOT NULL GROUP BY period, run
)
SELECT (SELECT count(*) FROM phase), count(*), quantile_cont(s, 0.5), quantile_cont(s, 0.9),
       avg((phases > 1)::INT)
FROM runs
"""

BASKETBALL = f"""
SELECT count(*), quantile_cont(s, 0.5), quantile_cont(s, 0.9) FROM (
  SELECT (endFrame - startFrame) / {BASKETBALL_FPS} AS s FROM read_parquet($path)
  WHERE startFrame IS NOT NULL AND endFrame IS NOT NULL
)
"""


def main() -> int:
    held_out = set(json.loads(FENCE.read_text(encoding="utf-8"))["held_out"])
    bronze = data_root() / "bronze"
    football = [
        p
        for p in sorted((bronze / "football" / "phases_of_play").glob("*.parquet"))
        if p.stem not in held_out
    ]
    basketball = sorted((bronze / "basketball" / "events_possessions").glob("*.parquet"))
    con = duckdb.connect()
    alive = len(football) == 10 and len(basketball) == 10
    print("probe possession, football: runs of same-team phases within a period")
    print("match     phases  runs  median_s  p90_s  multi_phase")
    for p in football:
        phases, runs, med, p90, multi = con.execute(FOOTBALL, {"path": p.as_posix()}).fetchone()
        print(f"{p.stem}  {phases:>6}  {runs:>4}  {med:>8.1f}  {p90:>5.1f}  {100 * multi:>10.1f}%")
        alive &= runs >= MIN_UNITS
    print("probe possession, basketball: events_possessions")
    print("match   possessions  median_s  p90_s")
    for p in basketball:
        n, med, p90 = con.execute(BASKETBALL, {"path": p.as_posix()}).fetchone()
        print(f"{p.stem}  {n:>11}  {med:>8.1f}  {p90:>5.1f}")
        alive &= n >= MIN_UNITS
    verdict = "VIVE" if alive else "MUERE"
    print(
        f"probe possession: {verdict} ({len(football)} football matches outside the held-out "
        f"ten, {len(basketball)} basketball; each needs >= {MIN_UNITS} units)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
