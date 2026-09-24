"""Apparent gravity of the ball per match: the g its free flights fall with.

The estimator is `flight.apparent_g`, a parabola fitted over a window centred on the
apex of each flight; each match reports its number of flights and the median, Q1 and
Q3 of g, and the median's bias against 9.80665 m/s^2. The count of flights each
filter drops is reported too, so a median can be read against what was left out.

Basketball: one flight per shot of bronze `events_shots`, ported from
`skillcorner_screens/probes/probe_i_gravity.py` and converted to metres (1 ft = 0.3048 m).
The apex is the highest ball sample from 10 frames before `startFrame` to 19 after
`endFrame` (`startFrame` + 25 when there is no end), the window is the apex +-10
frames (0.8 s at 25 fps) and every frame of it must be tracked. Dropped, in this order:
blocked shots; shots without that window; flights that rebound inside the window, that
is, after the apex the ball comes within 0.762 m (2.5 ft) of either rim axis or drops
below 2.8956 m (9.5 ft), the free-flight cuts of `probe_l_redo.py`; and fits whose
vertical residual RMS reaches 0.3048 m (1 ft, probe I). The rebound cut looks only
after the apex: `probe_k_freeflight.py` applied the same cuts from the release, the
floor fired on flights released below 9.5 ft, and the survivors were a biased sample
of long, high shots; `probe_l_redo.py` withdrew that version and moved the cuts after
the apex. Every constant was set by `skillcorner_screens` on its five calibration
games, which each match here is flagged as (`is_calibration`); the other five are its
held-out control. With the rebound cut switched off, the calibration games give back
probe I's flight count and median g per game exactly (task 27).

Football: the ball's flights are found in `frames`, a run of consecutive frames of one
period with the ball above 1 m that starts and ends next to a tracked frame at or below
1 m; the apex is the run's highest sample. The window is the apex +-6 frames (1.2 s at
10 fps) and must lie inside the run. Dropped, in this order: windows that leave the
run; windows with a sample whose `is_detected` is false (an extrapolated position, not
a measured one); windows holding the first or last frame of a player possession of
silver `events` (a touch: the ball is not in free flight across it); and the same
residual cut. Why +-6: with the truth kept only every 5 frames and interpolated in
between (the treatment of task 26), `flight.knots_every` at 10 fps moves g by -2.60% to
+8.23% across the five phases with +-4 frames, -12.59% to +7.23% with +-5 and -4.60%
to +4.90% with +-6. Football reports the number only: its `z_ball_status` is
`unverified`. Basketball has no detection cut: its ball is never flagged detected
(task 25), and its filters were frozen on the calibration games.
"""

from __future__ import annotations

import bisect
import math
import statistics
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from tracklab.quality.common import Result
from tracklab.quality.flight import G, apparent_g, fit_quadratic
from tracklab.silver.stats import table_glob

CHECK = "gravity"

FT = 0.3048
# skillcorner_screens' calibration games (probes/probe_d_screen.py); the rest is control.
CALIBRATION = frozenset({114243, 114234, 114169, 114099, 114086})

BB_BEFORE, BB_AFTER, BB_END_IF_MISSING = 10, 20, 25  # frame range searched for the apex
BB_HALF = 10
RIM_X = (91.86 / 2 - 5.17) * FT  # rim axis on the court's long axis, probe D
RIM_CLEAR = 2.5 * FT
FLOOR = 9.5 * FT
MAX_RMS = 1.0 * FT

FB_HALF = 6
FB_FLIGHT_Z = 1.0

# (frame_native, t in seconds, x, y, z) of one ball sample.
Sample = tuple[int, float, float, float, float]
# A ball sample in its match: (match_id, period, sample, is_detected).
Tracked = tuple[str, int, Sample, bool]


@dataclass
class Tally:
    """What happened to each candidate flight of a match, and the g of those kept."""

    excluded: dict[str, int]
    candidates: int = 0
    g: list[float] = field(default_factory=list)


BB_REASONS = ("blocked", "no_window", "rebound", "residual")
FB_REASONS = ("window_leaves_flight", "undetected", "player_possession", "residual")


def gravity(data_dir: Path, reports_dir: Path) -> list[Result]:
    # `reports_dir` is unused: unlike `partitions`, this check reads only bronze/silver.
    balls = _ball_samples(data_dir)
    touches = _possession_bounds(data_dir)
    results: list[Result] = []
    for (native, match_id), shots in _shots(data_dir).items():
        tally = _basketball(balls.get(("basketball", native), {}), shots)
        results += _results("basketball", match_id, tally, "shots")
        split = 1.0 if native in CALIBRATION else 0.0
        results.append(
            Result(CHECK, "basketball", match_id, "is_calibration", split, "flag", tally.candidates)
        )
    for (sport, native), by_frame in sorted(balls.items()):
        if sport == "football":
            match_id = next(iter(by_frame.values()))[0]
            tally = _football(by_frame, touches.get(native, []))
            results += _results(sport, match_id, tally, "flights_detected")
    return results


# Reading.


def _ball_samples(data_dir: Path) -> dict[tuple[str, int], dict[int, Tracked]]:
    """(sport, native match id) -> frame -> (match_id, period, sample, is_detected)."""
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT sport, native_match_id, match_id, period, frame_native, t_ms, x_m, y_m, z_m,
                   coalesce(is_detected, false)
            FROM read_parquet(?)
            WHERE entity_kind = 'ball' AND z_m IS NOT NULL
            ORDER BY sport, native_match_id, frame_native
            """,
            [table_glob(data_dir, "frames")],
        )
        .fetchall()
    )
    out: dict[tuple[str, int], dict[int, Tracked]] = {}
    for sport, native, match_id, period, frame, t_ms, x, y, z, detected in rows:
        sample = (int(frame), int(t_ms) / 1000.0, float(x), float(y), float(z))
        by_frame = out.setdefault((str(sport), int(native)), {})
        by_frame[int(frame)] = (str(match_id), int(period), sample, bool(detected))
    return out


def _possession_bounds(data_dir: Path) -> dict[int, list[int]]:
    """Football native match id -> sorted first and last frames of its player
    possessions (silver `events`, every row of the native `player_possession` family)."""
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT native_match_id, frame
            FROM (
                SELECT native_match_id, unnest([frame_start, frame_end]) AS frame
                FROM read_parquet(?)
                WHERE sport = 'football' AND native_family = 'player_possession'
            )
            WHERE frame IS NOT NULL
            ORDER BY native_match_id, frame
            """,
            [table_glob(data_dir, "events")],
        )
        .fetchall()
    )
    out: dict[int, list[int]] = {}
    for native, frame in rows:
        out.setdefault(int(native), []).append(int(frame))
    return out


def _shots(data_dir: Path) -> dict[tuple[int, str], list[tuple[int, int | None, bool]]]:
    """(native match id, silver match id) -> (startFrame, endFrame, blocked) per shot."""
    shots_glob = (data_dir / "bronze" / "basketball" / "events_shots" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT match_id, startFrame, endFrame, coalesce(blocked, false)
            FROM read_parquet(?)
            WHERE startFrame IS NOT NULL
            ORDER BY match_id, startFrame, id
            """,
            [shots_glob],
        )
        .fetchall()
    )
    out: dict[tuple[int, str], list[tuple[int, int | None, bool]]] = {}
    for native, start, end, blocked in rows:
        key = (int(native), f"bb:{int(native)}")
        out.setdefault(key, []).append(
            (int(start), None if end is None else int(end), bool(blocked))
        )
    return out


# Basketball.


def _basketball(ball: dict[int, Tracked], shots: list[tuple[int, int | None, bool]]) -> Tally:
    tally = Tally(dict.fromkeys(BB_REASONS, 0))
    for start, end, blocked in shots:
        tally.candidates += 1
        if blocked:
            tally.excluded["blocked"] += 1
            continue
        window = _shot_window(ball, start, end)
        if window is None:
            tally.excluded["no_window"] += 1
            continue
        if any(_rebounds(s) for s in window[BB_HALF + 1 :]):
            tally.excluded["rebound"] += 1
            continue
        _fit_or_drop(tally, window)
    return tally


def _shot_window(ball: dict[int, Tracked], start: int, end: int | None) -> list[Sample] | None:
    """The apex +-BB_HALF frames of a shot, or None if any of them is not tracked inside
    the range searched for the apex (an apex at its edge may not be the flight's)."""
    last = end if end is not None else start + BB_END_IF_MISSING
    near = {f: ball[f][2] for f in range(start - BB_BEFORE, last + BB_AFTER) if f in ball}
    if len(near) < 2 * BB_HALF + 1:
        return None
    apex = max(near.values(), key=lambda s: s[4])[0]
    frames = range(apex - BB_HALF, apex + BB_HALF + 1)
    if any(f not in near for f in frames):
        return None
    return [near[f] for f in frames]


def _rebounds(s: Sample) -> bool:
    """The ball at the ring or below it: no longer the shot's free flight."""
    _, _, x, y, z = s
    return min(math.hypot(x - RIM_X, y), math.hypot(x + RIM_X, y)) < RIM_CLEAR or z < FLOOR


# Football.


def _football(ball: dict[int, Tracked], touches: list[int]) -> Tally:
    """`touches`: the sorted first and last frames of the match's player possessions."""
    tally = Tally(dict.fromkeys(FB_REASONS, 0))
    for run in _flights(ball):
        tally.candidates += 1
        apex = max(range(len(run)), key=lambda i: run[i][4])
        if apex - FB_HALF < 0 or apex + FB_HALF >= len(run):
            tally.excluded["window_leaves_flight"] += 1
            continue
        window = run[apex - FB_HALF : apex + FB_HALF + 1]
        if not all(ball[s[0]][3] for s in window):
            tally.excluded["undetected"] += 1
            continue
        first = bisect.bisect_left(touches, window[0][0])
        if first < len(touches) and touches[first] <= window[-1][0]:
            tally.excluded["player_possession"] += 1
            continue
        _fit_or_drop(tally, window)
    return tally


def _flights(ball: dict[int, Tracked]) -> Iterator[list[Sample]]:
    """Runs of consecutive frames above FB_FLIGHT_Z, bounded on both sides by a tracked
    frame of the same period at or below it: the ball went up and came back down."""
    run: list[Sample] | None = None  # None until a take-off has been seen
    prev: tuple[int, int, float] | None = None  # (frame, period, z) of the last sample
    for frame in sorted(ball):
        _, period, s, _ = ball[frame]
        joined = prev is not None and prev[0] == frame - 1 and prev[1] == period
        if not joined:
            run = None  # a gap: whatever was in the air was not seen landing
        if s[4] > FB_FLIGHT_Z:
            if run is not None:
                run.append(s)
            elif prev is not None and joined and prev[2] <= FB_FLIGHT_Z:
                run = [s]
        else:
            if run:
                yield run
            run = None
        prev = (frame, period, s[4])


# Shared.


def _fit_or_drop(tally: Tally, window: list[Sample]) -> None:
    t = [s[1] for s in window]
    z = [s[4] for s in window]
    c, b, a = fit_quadratic(t, z)
    residuals = [zi - (c + b * ti + a * ti * ti) for ti, zi in zip(t, z, strict=True)]
    rms = math.sqrt(statistics.fmean(r * r for r in residuals))
    if rms >= MAX_RMS:
        tally.excluded["residual"] += 1
        return
    tally.g.append(apparent_g(t, z))


def _results(sport: str, match_id: str, tally: Tally, candidates: str) -> list[Result]:
    n = len(tally.g)
    out = [
        Result(
            CHECK, sport, match_id, candidates, float(tally.candidates), "count", tally.candidates
        )
    ]
    out += [
        Result(CHECK, sport, match_id, f"excluded_{reason}", float(k), "count", tally.candidates)
        for reason, k in tally.excluded.items()
    ]
    out.append(Result(CHECK, sport, match_id, "flights", float(n), "count", tally.candidates))
    if n >= 2:
        q1, median, q3 = statistics.quantiles(tally.g, n=4, method="inclusive")
        bias = 100 * (median / G - 1)
        out += [
            Result(CHECK, sport, match_id, "g_median", round(median, 4), "m/s^2", n),
            Result(CHECK, sport, match_id, "g_q1", round(q1, 4), "m/s^2", n),
            Result(CHECK, sport, match_id, "g_q3", round(q3, 4), "m/s^2", n),
            Result(CHECK, sport, match_id, "g_median_bias_pct", round(bias, 4), "%", n),
        ]
    return out
