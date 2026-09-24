"""Frame-to-frame jitter of the ball against detected players, both sports, per
`skillcorner_screens/probes/probe_u_horizontal.py` (read-only reference).

The statistic is the second difference of a horizontal position,
`x(t+1) - 2x(t) + x(t-1)` (and the same for y, combined by `hypot`), taken only
where the object is actually moving: the probe's `MOVING_FT_PER_FRAME` gate is a
per-frame distance, which does not carry across two sample rates, so here it is
read as the velocity it approximates (about 3 ft/s) and applied in m/s, the same
gate at 25 fps (basketball) and 10 fps (football). A second difference needs at
least 3 samples in a row; the probe's `MIN_RUN` (12 contiguous frames before a run
is used at all) is a frame count, ported unchanged.

Positions come from silver `frames` (metres); the ball is read unconditionally
(basketball's ball is flagged detected in 0% of frames, task 25, so requiring
`is_detected` would leave nothing to compare), players only where
`is_detected` is true, matching the probe. Basketball also reports the median
`predError` bronze declares (feet, converted here) for the ball and for detected
players, the number the ratio is checked against; football's `tracking_objects`
carries no error field (task 4), so that pair of metrics is simply absent there,
the same way `quality.gravity` omits `is_calibration` for football.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import duckdb

from tracklab.quality.common import Result

CHECK = "noise"

FT = 0.3048
MIN_RUN = 12  # contiguous frames required before a run yields a second difference
MOVING_MPS = 3.0 * FT  # ~3 ft/s, the probe's "this thing is actually moving" gate

Track = tuple[int, float, float, float]  # (frame_native, t_s, x_m, y_m)


def noise(data_dir: Path, reports_dir: Path) -> list[Result]:
    # `reports_dir` is unused: unlike `partitions`, this check reads only bronze/silver.
    balls = _tracks(data_dir, "ball")
    players = _tracks(data_dir, "player")
    pred_errors = _pred_errors(data_dir)
    results: list[Result] = []
    keys = sorted(set(balls) | set(players))
    for sport, match_id in keys:
        ball_d2 = _pooled_d2(balls.get((sport, match_id), {}))
        player_d2 = _pooled_d2(players.get((sport, match_id), {}))
        results += _results(sport, match_id, ball_d2, player_d2)
        if sport == "basketball":
            results += _pred_error_results(match_id, pred_errors.get(match_id, {}))
    return results


def _tracks(data_dir: Path, kind: str) -> dict[tuple[str, str], dict[str, list[Track]]]:
    """(sport, match_id) -> entity_id -> its samples, in frame order. Ball: every
    sample with a horizontal position. Player: only where `is_detected`."""
    glob = (data_dir / "silver" / "frames" / "**" / "*.parquet").as_posix()
    where = "entity_kind = 'ball'" if kind == "ball" else "entity_kind = 'player' AND is_detected"
    rows = (
        duckdb.connect()
        .execute(
            f"""
            SELECT sport, match_id, entity_id, frame_native, t_ms, x_m, y_m
            FROM read_parquet(?)
            WHERE {where}
            ORDER BY sport, match_id, entity_id, frame_native
            """,
            [glob],
        )
        .fetchall()
    )
    out: dict[tuple[str, str], dict[str, list[Track]]] = {}
    for sport, match_id, entity_id, frame, t_ms, x, y in rows:
        by_entity = out.setdefault((str(sport), str(match_id)), {})
        by_entity.setdefault(str(entity_id), []).append(
            (int(frame), int(t_ms) / 1000.0, float(x), float(y))
        )
    return out


def _runs(samples: list[Track]) -> list[list[Track]]:
    """Split on any gap in `frame_native`; samples arrive already frame-sorted."""
    runs: list[list[Track]] = []
    current: list[Track] = []
    prev_frame: int | None = None
    for sample in samples:
        if current and prev_frame is not None and sample[0] != prev_frame + 1:
            runs.append(current)
            current = []
        current.append(sample)
        prev_frame = sample[0]
    if current:
        runs.append(current)
    return runs


def _second_diffs(run: list[Track]) -> list[float]:
    if len(run) < MIN_RUN:
        return []
    step = []
    for a, b in zip(run, run[1:], strict=False):
        dt = b[1] - a[1]
        step.append(math.hypot(b[2] - a[2], b[3] - a[3]) / dt if dt > 0 else 0.0)
    out = []
    for k in range(len(run) - 2):
        if step[k] > MOVING_MPS and step[k + 1] > MOVING_MPS:
            x0, y0 = run[k][2], run[k][3]
            x1, y1 = run[k + 1][2], run[k + 1][3]
            x2, y2 = run[k + 2][2], run[k + 2][3]
            out.append(math.hypot(x2 - 2 * x1 + x0, y2 - 2 * y1 + y0))
    return out


def _pooled_d2(by_entity: dict[str, list[Track]]) -> list[float]:
    out: list[float] = []
    for samples in by_entity.values():
        for run in _runs(samples):
            out += _second_diffs(run)
    return out


def _pred_errors(data_dir: Path) -> dict[str, dict[str, list[float]]]:
    """Basketball match_id -> {'ball', 'player'} -> declared `predError`, in
    metres: the ball unconditionally, players only where `isDetected`, matching
    `_tracks` above."""
    glob = (data_dir / "bronze" / "basketball" / "tracking_objects" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT match_id, CASE WHEN side = 'ball' THEN 'ball' ELSE 'player' END AS kind,
                   predError
            FROM read_parquet(?)
            WHERE side = 'ball' OR isDetected
            """,
            [glob],
        )
        .fetchall()
    )
    out: dict[str, dict[str, list[float]]] = {}
    for match_id, kind, pred_error in rows:
        out.setdefault(f"bb:{match_id}", {}).setdefault(kind, []).append(float(pred_error) * FT)
    return out


def _results(
    sport: str, match_id: str, ball_d2: list[float], player_d2: list[float]
) -> list[Result]:
    out: list[Result] = []
    if ball_d2:
        out.append(
            Result(
                CHECK,
                sport,
                match_id,
                "ball_d2_median_m",
                round(statistics.median(ball_d2), 6),
                "m",
                len(ball_d2),
            )
        )
    if player_d2:
        out.append(
            Result(
                CHECK,
                sport,
                match_id,
                "player_d2_median_m",
                round(statistics.median(player_d2), 6),
                "m",
                len(player_d2),
            )
        )
    if ball_d2 and player_d2:
        ratio = statistics.median(ball_d2) / statistics.median(player_d2)
        n = min(len(ball_d2), len(player_d2))
        out.append(
            Result(CHECK, sport, match_id, "ball_player_d2_ratio", round(ratio, 4), "ratio", n)
        )
    return out


def _pred_error_results(match_id: str, by_kind: dict[str, list[float]]) -> list[Result]:
    out = []
    for kind in ("ball", "player"):
        values = by_kind.get(kind)
        if values:
            out.append(
                Result(
                    CHECK,
                    "basketball",
                    match_id,
                    f"{kind}_pred_error_median_m",
                    round(statistics.median(values), 6),
                    "m",
                    len(values),
                )
            )
    return out
