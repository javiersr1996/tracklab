"""The four partitions no field in either bundle declares, one row per match,
read from artefacts tasks 4, 5, 7 and 9 already produced (the brief for this
check: read versioned artefacts, do not recompute the underlying analysis by
hand). Three of the four sit in a CSV already on disk; the fourth has none of
its own -- task 5's HECHO entry only prints an ad hoc table in `tasks/todo.md`,
never written to a report -- so it is derived here straight from bronze
`tracking_frames` with the same formula that table used (missing frames =
`max(frameIdx) + 1 - count(*)`), which is a two-line count over an artefact
task 5 already built, not a re-analysis of the raw bundle. That gap is real
and is noted again in `dagster_defs.assets_quality`, whose `READS` cannot name
a `reports/basketball_format.csv` dependency because no such report exists.

1. Football tracking layout (task 4, `reports/football_format.csv`,
   `frames_outside_periods`): 5 of the 20 matches carry 11,059-13,459 frames of
   warm-up, half-time and post-match footage outside their two periods; the
   other 15 only a 9-29 frame kickoff pause. `FOOTBALL_LAYOUT_THRESHOLD` sits
   anywhere in the two-orders-of-magnitude gap between the two groups.
2. Basketball frame-loss regime (task 5, bronze `tracking_frames`): the five
   114xxx matches drop 1.39-3.28% of their native frames, the other five
   0.002-0.06% (a factor of 148 between the medians). `BASKETBALL_FRAME_LOSS_THRESHOLD`
   sits in that gap.
3 & 4. Football `players[]` shape (task 7) and event-coordinate precision
   (task 9), both already columns of `reports/orientation_football.csv`:
   `players_last_modified` (match.json's own regime) and `attack_median_m`
   (the event/tracking residual). Task 9 found these are the same 10-and-10
   split; this check reports both paths per match plus whether they agree, and
   a test asserts they always do.
"""

from __future__ import annotations

import csv
from pathlib import Path

import duckdb

from tracklab.quality.common import Result

CHECK = "partitions"

FOOTBALL_LAYOUT_THRESHOLD = 1000.0  # frames outside a period; the gap is 29 vs 11,059+
BASKETBALL_FRAME_LOSS_THRESHOLD = 0.5  # %; the gap is 0.06 vs 1.39
FOOTBALL_EVENT_COORD_THRESHOLD = 0.01  # m; the gap is 0.0 exactly vs 0.134+


def partitions(data_dir: Path, reports_dir: Path) -> list[Result]:
    results: list[Result] = []
    results += _football_layout(reports_dir)
    results += _basketball_frame_loss(data_dir)
    results += _football_players_and_events(reports_dir)
    return results


def _football_layout(reports_dir: Path) -> list[Result]:
    path = reports_dir / "football_format.csv"
    out: list[Result] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            match_id = f"fb:{row['match_id']}"
            outside = float(row["frames_outside_periods"])
            n_frames = int(row["n_frames"])
            out.append(
                Result(
                    CHECK,
                    "football",
                    match_id,
                    "layout_frames_outside_periods",
                    outside,
                    "count",
                    n_frames,
                )
            )
            flag = 1.0 if outside >= FOOTBALL_LAYOUT_THRESHOLD else 0.0
            out.append(Result(CHECK, "football", match_id, "layout_extra_footage", flag, "flag", 1))
    return out


def _basketball_frame_loss(data_dir: Path) -> list[Result]:
    glob = (data_dir / "bronze" / "basketball" / "tracking_frames" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT match_id, count(*) AS n_frames, max(frameIdx) + 1 AS span
            FROM read_parquet(?)
            GROUP BY match_id
            """,
            [glob],
        )
        .fetchall()
    )
    out: list[Result] = []
    for native, n_frames, span in sorted(rows):
        match_id = f"bb:{native}"
        missing = int(span) - int(n_frames)
        pct = 100.0 * missing / int(span)
        out.append(
            Result(CHECK, "basketball", match_id, "frame_loss_pct", round(pct, 4), "%", int(span))
        )
        flag = 1.0 if pct >= BASKETBALL_FRAME_LOSS_THRESHOLD else 0.0
        out.append(Result(CHECK, "basketball", match_id, "frame_loss_regime_high", flag, "flag", 1))
    return out


def _football_players_and_events(reports_dir: Path) -> list[Result]:
    path = reports_dir / "orientation_football.csv"
    out: list[Result] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            match_id = f"fb:{row['match_id']}"
            players_flag = 1.0 if row["players_last_modified"] == "yes" else 0.0
            attack_median = float(row["attack_median_m"])
            n_matched = int(row["pp_matched"])
            event_flag = 1.0 if attack_median < FOOTBALL_EVENT_COORD_THRESHOLD else 0.0
            agree = 1.0 if players_flag == event_flag else 0.0
            out += [
                Result(
                    CHECK, "football", match_id, "players_last_modified", players_flag, "flag", 1
                ),
                Result(
                    CHECK,
                    "football",
                    match_id,
                    "attack_median_m",
                    round(attack_median, 4),
                    "m",
                    n_matched,
                ),
                Result(
                    CHECK, "football", match_id, "event_coords_exact", event_flag, "flag", n_matched
                ),
                Result(CHECK, "football", match_id, "partitions_agree", agree, "flag", 1),
            ]
    return out
