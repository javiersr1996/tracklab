"""Entry angle of a made basketball shot: what the bundle's z reports against what
the geometry of the flight requires, per `skillcorner_screens/probes/probe_q2_entry_angle.py`
and `probes/probe_t_ordering.py` (both read-only references, ported here in metres).

The time of flight never touches z: horizontal speed is constant in a projectile,
and x, y are the axes nothing else here has questioned. `v_h` is measured over the
first `V_H_FRAMES` samples after the shot starts, `T = D / v_h` from the release
point to the rim centre, and then, with true gravity and the rim at a known
3.048 m (10 ft):

    v_z0 = (RIM_HEIGHT - z0 + g*T**2 / 2) / T,  required angle = atan(|v_z0 - g*T| / v_h)

against the angle the bundle's own z curvature implies near the arrival frame
(a straight line through the last few samples before `T`). Only made, unblocked
shots with a start, an end and a distance are used (`probe_q2.made_shots`); the
ball's trajectory comes from silver `frames` (reused from `quality.gravity`) and
the shot list from bronze `events_shots`.

Two numbers per match, as `skillcorner_screens` measured them: the median gap
(required minus reported) and the share of shot pairs the two angles order
differently, computed exactly over every pair (not `probe_t`'s 200,000-draw
Monte-Carlo estimate: each match has at most a few dozen shots, so the exact
count is both simpler and exact).
"""

from __future__ import annotations

import bisect
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from tracklab.quality.common import Result
from tracklab.quality.flight import G
from tracklab.quality.gravity import CALIBRATION, FT, RIM_X, Sample, _ball_samples

CHECK = "entry_angle"

RIM_HEIGHT = 10.0 * FT  # 3.048 m
V_H_FRAMES = 8  # samples used to measure horizontal speed, probe Q2
V_H_MIN = 4.0 * FT  # m/s; below this the finite difference is noise, not a shot
T_MIN, T_MAX = 0.6, 1.6  # s; sanity range for the reconstructed flight time
TAIL_BACK, TAIL_MIN_INDEX = 6, 2  # the arrival-frame tail fit is samples [k-6, k]
SEARCH_OFFSET = 2  # frames after startFrame the search for the flight begins
SEG_LEN = 40  # samples examined for a contiguous run
MIN_CONTIG = V_H_FRAMES + 4  # shortest run accepted, probe Q2
DT = 1.0 / 25.0  # basketball's fps, verified exact in task 5 (wallClock == frameIdx*40)

REASONS = ("no_window", "short_run", "slow_ball", "bad_flight_time", "arrival_beyond_run")


@dataclass
class Tally:
    excluded: dict[str, int]
    candidates: int = 0
    pairs: list[tuple[float, float]] = field(default_factory=list)


def entry_angle(data_dir: Path, reports_dir: Path) -> list[Result]:
    # `reports_dir` is unused: unlike `partitions`, this check reads only bronze/silver.
    balls = _ball_samples(data_dir)
    shots = _made_shots(data_dir)
    results: list[Result] = []
    for (sport, native), by_frame in sorted(balls.items()):
        if sport != "basketball" or native not in shots:
            continue
        match_id = next(iter(by_frame.values()))[0]
        samples = [sample for _, (_, _, sample, _) in sorted(by_frame.items())]
        tally = _match(samples, shots[native])
        results += _results(match_id, native, tally)
    return results


def _made_shots(data_dir: Path) -> dict[int, list[int]]:
    """(native match id) -> start frames of every made, unblocked shot with a start,
    an end and a distance, `probe_q2_entry_angle.made_shots`."""
    glob = (data_dir / "bronze" / "basketball" / "events_shots" / "*.parquet").as_posix()
    rows = (
        duckdb.connect()
        .execute(
            """
            SELECT match_id, startFrame
            FROM read_parquet(?)
            WHERE outcome AND NOT blocked
              AND startFrame IS NOT NULL AND endFrame IS NOT NULL AND distance IS NOT NULL
            ORDER BY match_id, startFrame
            """,
            [glob],
        )
        .fetchall()
    )
    out: dict[int, list[int]] = {}
    for native, start in rows:
        out.setdefault(int(native), []).append(int(start))
    return out


def _match(samples: list[Sample], starts: list[int]) -> Tally:
    tally = Tally(dict.fromkeys(REASONS, 0))
    frames = [s[0] for s in samples]
    for start in starts:
        tally.candidates += 1
        i0 = bisect.bisect_left(frames, start + SEARCH_OFFSET)
        if i0 + SEG_LEN >= len(samples):
            tally.excluded["no_window"] += 1
            continue
        seg = samples[i0 : i0 + SEG_LEN]
        n = _contig_len([s[0] for s in seg])
        if n < MIN_CONTIG:
            tally.excluded["short_run"] += 1
            continue
        run = seg[:n]
        pair = _angles(run)
        if isinstance(pair, str):
            tally.excluded[pair] += 1
            continue
        tally.pairs.append(pair)
    return tally


def _contig_len(frames: list[int]) -> int:
    """`np.sum(np.diff(fi) == 1) + 1`: how many of the segment's samples chain by
    exactly one native frame, counted over the whole segment (not stopped at the
    first gap), exactly as `probe_q2_entry_angle.collect` computes it."""
    return sum(1 for a, b in zip(frames, frames[1:], strict=False) if b - a == 1) + 1


def _angles(run: list[Sample]) -> tuple[float, float] | str:
    """(reported, required) entry angle in degrees, or the exclusion reason."""
    x0, y0 = run[0][2], run[0][3]
    rim_x = RIM_X if x0 > 0 else -RIM_X
    first = run[:V_H_FRAMES]
    steps = []
    for a, b in zip(first, first[1:], strict=False):
        dt = b[1] - a[1]
        steps.append(math.hypot(b[2] - a[2], b[3] - a[3]) / dt if dt > 0 else 0.0)
    v_h = statistics.median(steps)
    if v_h < V_H_MIN:
        return "slow_ball"
    dist = math.hypot(rim_x - x0, -y0)
    t_flight = dist / v_h
    if not (T_MIN <= t_flight <= T_MAX):
        return "bad_flight_time"
    k = round(t_flight / DT)
    if k >= len(run):
        return "arrival_beyond_run"
    z0 = run[0][4]
    tail = run[max(k - TAIL_BACK, TAIL_MIN_INDEX) : k + 1]
    t_tail = [s[1] - tail[0][1] for s in tail]
    z_tail = [s[4] for s in tail]
    v_z_rep = _slope(t_tail, z_tail)
    ang_rep = math.degrees(math.atan2(abs(v_z_rep), v_h))
    v_z0 = (RIM_HEIGHT - z0 + 0.5 * G * t_flight * t_flight) / t_flight
    ang_req = math.degrees(math.atan2(abs(v_z0 - G * t_flight), v_h))
    return ang_rep, ang_req


def _slope(t: list[float], z: list[float]) -> float:
    """The slope of the least-squares line through (t, z): `np.polyfit(t, z, 1)[0]`."""
    n = len(t)
    tbar, zbar = sum(t) / n, sum(z) / n
    num = sum((ti - tbar) * (zi - zbar) for ti, zi in zip(t, z, strict=True))
    den = sum((ti - tbar) ** 2 for ti in t)
    if den == 0:
        raise ValueError("degenerate tail: every sample at the same time")
    return num / den


def _pair_reorder(reps: list[float], reqs: list[float]) -> tuple[int, int]:
    """(pairs ordered differently, pairs compared); ties on either side are dropped,
    `probe_t_ordering.inversions` computed exactly instead of by Monte-Carlo draw."""
    disagree = total = 0
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            a, b = reps[i] - reps[j], reqs[i] - reqs[j]
            if a == 0 or b == 0:
                continue
            total += 1
            if (a > 0) != (b > 0):
                disagree += 1
    return disagree, total


def _results(match_id: str, native: int, tally: Tally) -> list[Result]:
    n = len(tally.pairs)
    out = [
        Result(
            CHECK,
            "basketball",
            match_id,
            "candidates",
            float(tally.candidates),
            "count",
            tally.candidates,
        )
    ]
    out += [
        Result(CHECK, "basketball", match_id, f"excluded_{r}", float(k), "count", tally.candidates)
        for r, k in tally.excluded.items()
    ]
    out.append(Result(CHECK, "basketball", match_id, "shots", float(n), "count", tally.candidates))
    if n >= 1:
        reps = [r for r, _ in tally.pairs]
        reqs = [q for _, q in tally.pairs]
        gaps = [q - r for r, q in tally.pairs]
        out += [
            Result(
                CHECK,
                "basketball",
                match_id,
                "angle_reported_median_deg",
                round(statistics.median(reps), 4),
                "deg",
                n,
            ),
            Result(
                CHECK,
                "basketball",
                match_id,
                "angle_required_median_deg",
                round(statistics.median(reqs), 4),
                "deg",
                n,
            ),
            Result(
                CHECK,
                "basketball",
                match_id,
                "gap_median_deg",
                round(statistics.median(gaps), 4),
                "deg",
                n,
            ),
        ]
        if n >= 2:
            disagree, total = _pair_reorder(reps, reqs)
            if total > 0:
                out.append(
                    Result(
                        CHECK,
                        "basketball",
                        match_id,
                        "pairs_reordered_pct",
                        round(100.0 * disagree / total, 4),
                        "%",
                        total,
                    )
                )
    out.append(
        Result(
            CHECK,
            "basketball",
            match_id,
            "is_calibration",
            1.0 if native in CALIBRATION else 0.0,
            "flag",
            tally.candidates,
        )
    )
    return out
