"""Windows, placebos and the paired estimator of P5 (task 48).

One match at a time. The runs come from bronze `dynamic_events` by their native keys, the
tracking from silver `frames` (venue frame, turned to the attack frame with
`dim_team_period.attack_sign`), the goalkeepers from bronze `match_players`, the placebo
instants from `placebo.py`. Windows, rule and instrument are the protocol's: the lengths are
`protocol.py`'s constants, the definitions are `effect.py`'s.

Two doors, kept apart on purpose:

* `count_match` returns a `MatchCounts`: integers and detection fractions, nothing else. It is
  what `tracklab runs coverage` writes for the 20 matches, held-out included, because counting
  runs and frames is not an outcome. It has no way to hand back a position or an effect.
* `pair_effects` returns the displacement and line-height effects per run, and refuses a
  held-out match until `data.require_readable` lets it through. On real data nothing prints
  or stores what it returns; only synthetic matches run it end to end (task 48).

A placebo instant is admissible when `placebo.py` says so (no run of the team within 3 s) and
the tracking can support it: the runner is detected at t', and every frame from t' - V to
t' + W exists in the runner's period. The nearest admissible instant to t_c wins, ties to the
earlier one (protocol, `placebo.choice`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path

import duckdb
import numpy as np
from numpy.typing import NDArray

from tracklab.runs import effect, placebo
from tracklab.runs.data import DEFAULT_PROTOCOL, require_readable
from tracklab.runs.protocol import (
    COVERAGE_AFTER_END_S,
    COVERAGE_BEFORE_START_S,
    EFFECT_WINDOW_S,
    MIN_RUN_LENGTH_M,
    PLACEBO_EXCLUDES_TEAMMATES_RUNS,
    SAMPLE_RATE_HZ,
    VELOCITY_WINDOW_S,
)

SUBTYPES = (
    "behind",
    "coming_short",
    "cross_receiver",
    "dropping_off",
    "overlap",
    "pulling_half_space",
    "pulling_wide",
    "run_ahead_of_the_ball",
    "support",
    "underlap",
)

EFFECT_FRAMES = round(EFFECT_WINDOW_S * SAMPLE_RATE_HZ)
VELOCITY_FRAMES = round(VELOCITY_WINDOW_S * SAMPLE_RATE_HZ)
BEFORE_FRAMES = round(COVERAGE_BEFORE_START_S * SAMPLE_RATE_HZ)
AFTER_FRAMES = round(COVERAGE_AFTER_END_S * SAMPLE_RATE_HZ)
PLACEBO_RULE: placebo.Rule = "team_overlap" if PLACEBO_EXCLUDES_TEAMMATES_RUNS else "runner_overlap"

Bools = NDArray[np.bool_]


@dataclass(frozen=True)
class Run:
    """An `off_ball_run` event with its native keys."""

    match_id: int
    event_id: str
    player_id: int
    team_id: int
    period: int
    frame_start: int
    frame_end: int
    subtype: str
    possession_id: str | None

    @property
    def runner(self) -> str:
        return f"fb:{self.player_id}"

    @property
    def team(self) -> str:
        return f"fb:{self.team_id}"


@dataclass(frozen=True)
class MatchTracking:
    """The players of one match, frame by frame. `x`, `y` hold the venue frame in metres,
    NaN where the entity has no row in that frame; `detected` is the provider's flag.
    Row `i` is frame `frame0 + i`."""

    match_id: int
    frame0: int
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    detected: Bools
    entities: tuple[str, ...]
    team: tuple[str, ...]
    is_goalkeeper: Bools
    period_frames: Mapping[int, tuple[int, int]]
    attack_sign: Mapping[tuple[int, str], int]

    @property
    def n_frames(self) -> int:
        return int(self.x.shape[0])

    def row(self, frame: int) -> int | None:
        i = frame - self.frame0
        return i if 0 <= i < self.n_frames else None

    def frame_present(self, frame: int) -> bool:
        i = self.row(frame)
        return i is not None and bool(np.isfinite(self.x[i]).any())

    def entity_index(self, entity: str) -> int | None:
        try:
            return self.entities.index(entity)
        except ValueError:
            return None


@dataclass(frozen=True)
class PairEffect:
    """One run minus its placebo, in metres. Real-data instances are never printed or stored."""

    match_id: int
    run_id: str
    possession_id: str | None
    subtype: str
    marker_m: float
    line_m: float


# --- loading --------------------------------------------------------------------------------


def load_runs(data_dir: Path, match_id: int) -> list[Run]:
    football = data_dir / "bronze" / "football"
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT match_id, event_id, player_id, team_id, period, frame_start, frame_end, "
            "event_subtype, associated_player_possession_event_id "
            "FROM read_parquet($events) WHERE match_id = $m AND event_type = 'off_ball_run' "
            "ORDER BY frame_start, event_id",
            {"events": (football / "dynamic_events" / "*.parquet").as_posix(), "m": match_id},
        ).fetchall()
    finally:
        con.close()
    return [
        Run(
            int(r[0]),
            str(r[1]),
            int(r[2]),
            int(r[3]),
            int(r[4]),
            int(r[5]),
            int(r[6]),
            str(r[7]),
            None if r[8] is None else str(r[8]),
        )
        for r in rows
    ]


def load_tracking(data_dir: Path, match_id: int) -> MatchTracking:
    """The players of `match_id` from silver. A match with no football frames raises."""
    silver = data_dir / "silver"
    frames_glob = (
        silver / "frames" / "sport=football" / f"native_match_id={match_id}" / "*.parquet"
    ).as_posix()
    con = duckdb.connect()
    try:
        cur = con.execute(
            "SELECT frame_native, entity_id, team_id, x_m, y_m, is_detected "
            "FROM read_parquet($g) WHERE entity_kind = 'player'",
            {"g": frames_glob},
        )
        cols = cur.fetchnumpy()
        periods = con.execute(
            "SELECT period, frame_native_start, frame_native_end "
            "FROM read_parquet($g) WHERE match_id = $m",
            {"g": (silver / "dim_period" / "*.parquet").as_posix(), "m": f"fb:{match_id}"},
        ).fetchall()
        signs = con.execute(
            "SELECT period, team_id, attack_sign FROM read_parquet($g) WHERE match_id = $m",
            {"g": (silver / "dim_team_period" / "*.parquet").as_posix(), "m": f"fb:{match_id}"},
        ).fetchall()
        keepers = con.execute(
            "SELECT 'fb:' || id FROM read_parquet($g) "
            "WHERE match_id = $m AND player_role_name = 'Goalkeeper'",
            {
                "g": (data_dir / "bronze" / "football" / "match_players" / "*.parquet").as_posix(),
                "m": match_id,
            },
        ).fetchall()
    finally:
        con.close()
    frame = np.asarray(cols["frame_native"], dtype=np.int64)
    if frame.size == 0:
        raise ValueError(f"no football frames for match {match_id} under {silver}")
    names, code = np.unique(np.asarray(cols["entity_id"], dtype=object), return_inverse=True)
    frame0 = int(frame.min())
    n_frames = int(frame.max()) - frame0 + 1
    x = np.full((n_frames, names.size), np.nan)
    y = np.full((n_frames, names.size), np.nan)
    detected = np.zeros((n_frames, names.size), dtype=np.bool_)
    row = frame - frame0
    x[row, code] = np.asarray(cols["x_m"], dtype=np.float64)
    y[row, code] = np.asarray(cols["y_m"], dtype=np.float64)
    detected[row, code] = np.asarray(cols["is_detected"], dtype=np.bool_)
    team_of: dict[str, str] = {}
    for entity, team in zip(cols["entity_id"], cols["team_id"], strict=True):
        team_of.setdefault(str(entity), str(team))
    keeper_ids = {str(k[0]) for k in keepers}
    return MatchTracking(
        match_id=match_id,
        frame0=frame0,
        x=x,
        y=y,
        detected=detected,
        entities=tuple(str(n) for n in names),
        team=tuple(team_of[str(n)] for n in names),
        is_goalkeeper=np.array([str(n) in keeper_ids for n in names], dtype=np.bool_),
        period_frames={int(p): (int(a), int(b)) for p, a, b in periods},
        attack_sign={(int(p), str(t)): int(s) for p, t, s in signs},
    )


# --- geometry in the attack frame -------------------------------------------------------------


def _xy(t: MatchTracking, frame: int, entity: int, sign: int) -> NDArray[np.float64]:
    i = frame - t.frame0
    return np.array([sign * t.x[i, entity], sign * t.y[i, entity]])


def _opponents(t: MatchTracking, team: str) -> NDArray[np.intp]:
    return np.array([i for i, tm in enumerate(t.team) if tm != team], dtype=np.intp)


def _opponents_xy(
    t: MatchTracking, frame: int, opponents: NDArray[np.intp], sign: int
) -> NDArray[np.float64]:
    i = frame - t.frame0
    return np.stack([sign * t.x[i, opponents], sign * t.y[i, opponents]], axis=1)


def window_bounds(t: MatchTracking, run: Run) -> tuple[int, int, bool]:
    """The coverage window of a run, clipped to its period: (first frame, last frame, clipped)."""
    start, end = t.period_frames[run.period]
    lo = max(run.frame_start - BEFORE_FRAMES, start)
    hi = min(run.frame_end + AFTER_FRAMES, end)
    clipped = lo > run.frame_start - BEFORE_FRAMES or hi < run.frame_end + AFTER_FRAMES
    return lo, hi, clipped


def _frames_present(t: MatchTracking, lo: int, hi: int) -> bool:
    return all(t.frame_present(f) for f in range(lo, hi + 1))


def _runner_detected(t: MatchTracking, runner: int | None, lo: int, hi: int) -> bool:
    if runner is None:
        return False
    rows = [t.row(f) for f in range(lo, hi + 1)]
    return all(i is not None and bool(t.detected[i, runner]) for i in rows)


def run_direction(t: MatchTracking, run: Run) -> NDArray[np.float64] | None:
    """The run's direction in the attack frame; None when the runner is not at both ends or
    the run is shorter than the protocol's minimum."""
    runner = t.entity_index(run.runner)
    sign = t.attack_sign.get((run.period, run.team))
    if runner is None or sign is None:
        return None
    a, b = t.row(run.frame_start), t.row(run.frame_end)
    if a is None or b is None:
        return None
    return effect.run_direction(
        _xy(t, run.frame_start, runner, sign), _xy(t, run.frame_end, runner, sign), MIN_RUN_LENGTH_M
    )


def quantities(
    t: MatchTracking,
    run: Run,
    anchor: int,
    direction: NDArray[np.float64],
) -> tuple[float, float] | None:
    """Marker displacement and line-height residual around `anchor` (t_c for the run, t' for
    its placebo), in metres. The marker is the opponent nearest to the runner at the anchor.
    None when any input of the formulas is missing."""
    runner = t.entity_index(run.runner)
    sign = t.attack_sign.get((run.period, run.team))
    if runner is None or sign is None:
        return None
    before, after = anchor - VELOCITY_FRAMES, anchor + EFFECT_FRAMES
    if any(t.row(f) is None for f in (before, anchor, after)):
        return None
    opponents = _opponents(t, run.team)
    runner_xy = _xy(t, anchor, runner, sign)
    marker = effect.nearest_opponent(runner_xy, _opponents_xy(t, anchor, opponents, sign))
    if marker is None:
        return None
    m = int(opponents[marker])
    p_before, p_at, p_after = (_xy(t, f, m, sign) for f in (before, anchor, after))
    residual = effect.residual_displacement(
        p_before, p_at, p_after, window_s=EFFECT_WINDOW_S, velocity_s=VELOCITY_WINDOW_S
    )
    heights = []
    for f in (before, anchor, after):
        i = f - t.frame0
        heights.append(effect.line_height(sign * t.x[i, opponents], t.is_goalkeeper[opponents]))
    line = effect.residual_scalar(*heights, window_s=EFFECT_WINDOW_S, velocity_s=VELOCITY_WINDOW_S)
    marker_m = effect.project(residual, direction)
    if not (math.isfinite(marker_m) and math.isfinite(line)):
        return None
    return marker_m, line


# --- placebos against the tracking ----------------------------------------------------------


def placebo_supported(t: MatchTracking, run: Run, period: int, instant: int) -> bool:
    """The tracking can carry a placebo at `instant`: the runner is detected there and every
    frame from t' - V to t' + W exists inside the period."""
    runner = t.entity_index(run.runner)
    bounds = t.period_frames.get(period)
    if runner is None or bounds is None:
        return False
    lo, hi = instant - VELOCITY_FRAMES, instant + EFFECT_FRAMES
    if lo < bounds[0] or hi > bounds[1]:
        return False
    i = t.row(instant)
    return i is not None and bool(t.detected[i, runner]) and _frames_present(t, lo, hi)


def choose_placebo(t: MatchTracking, run: Run, candidates: Sequence[tuple[int, int]]) -> int | None:
    """The supported instant nearest to t_c; ties go to the earlier one."""
    supported = [
        instant for period, instant in candidates if placebo_supported(t, run, period, instant)
    ]
    if not supported:
        return None
    return min(supported, key=lambda s: (abs(s - run.frame_start), s))


# --- counts: the door that returns no tracking value ----------------------------------------


@dataclass(frozen=True)
class MatchCounts:
    """Coverage of one match: runs, windows, detection and placebos. Integers, and fractions
    of detected opponent positions: no coordinate, no displacement."""

    match_id: int
    runs: int
    by_subtype: tuple[int, ...]
    complete_windows: int
    clipped_windows: int
    runner_absent: int
    runner_detected: int
    clean: int
    opp_detected_p50: float
    opp_detected_p10: float
    placebo_found: int
    analysis_set: int


COUNT_FIELDS = tuple(f.name for f in fields(MatchCounts) if f.name != "by_subtype")


def count_match(
    t: MatchTracking,
    runs: Sequence[Run],
    instants: Mapping[tuple[int, str], Sequence[tuple[int, int]]],
) -> MatchCounts:
    """Everything `runs_coverage.csv` holds for one match. Nothing in the result is a position
    or an effect; the analysis set is a count of the pairs the estimator can form."""
    by_subtype = {s: 0 for s in SUBTYPES}
    complete = clipped_n = absent = detected_n = clean = found = analysis = 0
    fractions: list[float] = []
    for run in runs:
        by_subtype[run.subtype] = by_subtype.get(run.subtype, 0) + 1
        lo, hi, clipped = window_bounds(t, run)
        clipped_n += clipped
        runner = t.entity_index(run.runner)
        absent += runner is None
        is_complete = _frames_present(t, lo, hi)
        complete += is_complete
        runner_ok = _runner_detected(t, runner, run.frame_start, run.frame_end)
        detected_n += runner_ok
        is_clean = is_complete and runner_ok
        clean += is_clean
        opponents = _opponents(t, run.team)
        window = slice(lo - t.frame0, hi - t.frame0 + 1)
        present = np.isfinite(t.x[window][:, opponents])
        if present.sum():
            fractions.append(float(t.detected[window][:, opponents][present].mean()))
        pick = choose_placebo(t, run, instants.get((t.match_id, run.event_id), ()))
        found += pick is not None
        if is_clean and pick is not None:
            direction = run_direction(t, run)
            if direction is not None:
                own = quantities(t, run, run.frame_start, direction)
                other = quantities(t, run, pick, direction)
                analysis += own is not None and other is not None
    p50, p10 = (
        (float(np.quantile(fractions, q)) for q in (0.5, 0.1)) if fractions else (math.nan,) * 2
    )
    return MatchCounts(
        match_id=t.match_id,
        runs=len(runs),
        by_subtype=tuple(by_subtype[s] for s in SUBTYPES),
        complete_windows=complete,
        clipped_windows=clipped_n,
        runner_absent=absent,
        runner_detected=detected_n,
        clean=clean,
        opp_detected_p50=p50,
        opp_detected_p10=p10,
        placebo_found=found,
        analysis_set=analysis,
    )


# --- effects: the door that returns values ----------------------------------------------------


def pair_effects(
    t: MatchTracking,
    runs: Sequence[Run],
    instants: Mapping[tuple[int, str], Sequence[tuple[int, int]]],
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
) -> list[PairEffect]:
    """One `PairEffect` per clean run with a direction and a supported placebo: the quantities
    at t_c minus the same quantities at t', both along the run's direction. Refuses a held-out
    match until the protocol is frozen in a clean tree. Never call it on real data to print."""
    require_readable(t.match_id, protocol_path)
    out: list[PairEffect] = []
    for run in runs:
        lo, hi, _ = window_bounds(t, run)
        runner = t.entity_index(run.runner)
        if not (
            _frames_present(t, lo, hi)
            and _runner_detected(t, runner, run.frame_start, run.frame_end)
        ):
            continue
        direction = run_direction(t, run)
        pick = choose_placebo(t, run, instants.get((t.match_id, run.event_id), ()))
        if direction is None or pick is None:
            continue
        own = quantities(t, run, run.frame_start, direction)
        other = quantities(t, run, pick, direction)
        if own is None or other is None:
            continue
        out.append(
            PairEffect(
                match_id=t.match_id,
                run_id=run.event_id,
                possession_id=run.possession_id,
                subtype=run.subtype,
                marker_m=own[0] - other[0],
                line_m=own[1] - other[1],
            )
        )
    return out
