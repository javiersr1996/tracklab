"""Is the clock exact, per `skillcorner_screens/probes/probe_p_clock.py` (read-only
reference)? Two independent readings, both from bronze `tracking_frames` /
`tracking_objects` (task 5 established the sample rate is exact, so this check
rebuilds that number from the artefact instead of assuming it):

1. The step between two native frames one apart. Basketball carries an
   independent millisecond field, `wallClock`, so the check is real: does
   `wallClock` actually advance by 40 ms when `frameIdx` advances by one?
   Football has no such field (`timestamp` is a period-relative string, task 4's
   own subject); the equivalent there is just native-frame contiguity, which at
   a fixed 10 fps *is* 100 ms by definition. The metric name is shared so the two
   sports sit in one table, and this asymmetry is the reason a 100% here means
   two different things for the two sports.
2. Basketball only: the provider's own `speed` against a finite difference of
   consecutive, detected positions of the same player (probe P's second
   reading). Ratio computed per pair, then the median of the ratios, exactly as
   the probe does; football's `tracking_objects` carries no `speed` column
   (task 4), so this pair of metrics is absent there.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import duckdb

from tracklab.quality.common import Result

CHECK = "clock"

FPS_ASSUMED = 25.0  # basketball, established exact in task 5
V_MIN, V_MAX = 3.0, 25.0  # ft/s gate on the finite-difference speed, probe P


def clock(data_dir: Path, reports_dir: Path) -> list[Result]:
    # `reports_dir` is unused: unlike `partitions`, this check reads only bronze.
    results: list[Result] = []
    results += _basketball_step(data_dir)
    results += _football_step(data_dir)
    results += _speed_check(data_dir)
    return results


def _basketball_step(data_dir: Path) -> list[Result]:
    """% of frameIdx-adjacent row pairs where `wallClock` advances by exactly 40 ms."""
    glob = (data_dir / "bronze" / "basketball" / "tracking_frames" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute(
            "SELECT match_id, frameIdx, wallClock FROM read_parquet(?) ORDER BY match_id, frameIdx",
            [glob],
        )
        .fetchall()
    )
    by_match: dict[str, list[tuple[int, int]]] = {}
    for native, frame, wall_clock in rows:
        by_match.setdefault(f"bb:{native}", []).append((int(frame), int(wall_clock)))
    out: list[Result] = []
    for match_id, series in sorted(by_match.items()):
        total = exact = 0
        for (f0, w0), (f1, w1) in zip(series, series[1:], strict=False):
            if f1 != f0 + 1:
                continue
            total += 1
            if w1 - w0 == 40:
                exact += 1
        if total > 0:
            out.append(
                Result(
                    CHECK,
                    "basketball",
                    match_id,
                    "clock_step_exact_pct",
                    round(100.0 * exact / total, 4),
                    "%",
                    total,
                )
            )
    return out


def _football_step(data_dir: Path) -> list[Result]:
    """% of native-frame-adjacent row pairs, football. No independent ms field
    exists here (unlike `wallClock` in basketball): a pair one native frame apart
    is 100 ms apart by the provider's declared 10 fps, not by an independent
    measurement, so this is a contiguity check rather than a clock cross-check."""
    glob = (data_dir / "bronze" / "football" / "tracking_frames" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute("SELECT match_id, frame FROM read_parquet(?) ORDER BY match_id, frame", [glob])
        .fetchall()
    )
    by_match: dict[str, list[int]] = {}
    for native, frame in rows:
        by_match.setdefault(f"fb:{native}", []).append(int(frame))
    out: list[Result] = []
    for match_id, frames in sorted(by_match.items()):
        total = len(frames) - 1
        if total <= 0:
            continue
        exact = sum(1 for a, b in zip(frames, frames[1:], strict=False) if b == a + 1)
        out.append(
            Result(
                CHECK,
                "football",
                match_id,
                "clock_step_exact_pct",
                round(100.0 * exact / total, 4),
                "%",
                total,
            )
        )
    return out


def _speed_check(data_dir: Path) -> list[Result]:
    """Basketball: the provider's `speed` against a finite difference of two
    consecutive, detected positions of the same player, gated to plausible
    running speeds (`V_MIN`, `V_MAX`, ft/s, probe P). Ratio per pair, then the
    median of the ratios (not the ratio of medians): `probe_p_clock.scan`."""
    glob = (data_dir / "bronze" / "basketball" / "tracking_objects" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT match_id, playerId, frameIdx, x, y, speed, isDetected
            FROM read_parquet(?)
            WHERE side <> 'ball'
            ORDER BY match_id, playerId, frameIdx
            """,
            [glob],
        )
        .fetchall()
    )
    by_match: dict[str, list[float]] = {}
    prev_key: tuple[str, int] | None = None
    prev_frame_xy: tuple[int, float, float] | None = None
    for match_id, player_id, frame, x, y, speed, detected in rows:
        key = (str(match_id), int(player_id))
        if key == prev_key and prev_frame_xy is not None and prev_frame_xy[0] == frame - 1:
            if detected:
                dx, dy = x - prev_frame_xy[1], y - prev_frame_xy[2]
                fd_speed = math.hypot(dx, dy) * FPS_ASSUMED
                if V_MIN < fd_speed < V_MAX:
                    by_match.setdefault(f"bb:{match_id}", []).append(float(speed) / fd_speed)
        prev_key = key
        prev_frame_xy = (int(frame), float(x), float(y))
    out: list[Result] = []
    for match_id, ratios in sorted(by_match.items()):
        median_ratio = statistics.median(ratios)
        out += [
            Result(
                CHECK,
                "basketball",
                match_id,
                "speed_ratio_median",
                round(median_ratio, 4),
                "ratio",
                len(ratios),
            ),
            Result(
                CHECK,
                "basketball",
                match_id,
                "speed_mismatch_pct",
                round(100.0 * abs(1.0 - median_ratio), 4),
                "%",
                len(ratios),
            ),
        ]
    return out
