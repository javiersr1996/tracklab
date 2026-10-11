"""Windows, placebos and the paired estimator of P5 (task 48).

One match at a time. The runs come from bronze `dynamic_events` by their native keys, the
tracking from silver `frames` (venue frame, turned to the attack frame with
`dim_team_period.attack_sign`), the goalkeepers from bronze `match_players`, the placebo
instants from `placebo.py`. Windows, rule and instrument are the protocol's: the lengths are
`protocol.py`'s constants, the definitions are `effect.py`'s.

Two doors, kept apart on purpose (hardened in the second and third reviews of 47-48):

* a tracking leaves this module in one shape, `MatchTracking`, which passes
  `data.require_readable` as it is built, hand-built or loaded: `load_tracking` runs the guard
  before it reads a byte, and `run_direction`, `run_length`, `line_height_at`, `quantities`
  and `pair_effects`, the functions that return values of a tracking, take nothing else. On
  real data only task 49's probe (`probe.py`, calibration half) prints what they return, and
  never per subtype; the synthetic matches run them end to end (task 48).
* `count_tracking` reads the frames of a match of either half, counts and drops them inside
  its own scope, from the runs and instants it loads itself (a caller hands it nothing that
  runs while the frames are live): it returns a `MatchCounts` of integers and detection
  fractions, computed from booleans, for the 20 matches, held-out included, because counting
  runs and frames is not an outcome. A failure re-raises as a `RuntimeError` of type and
  message only, with no frame holding an array. No handle and no flag: the silver frames are
  read in `_read_tracking` alone, whose two callers are `load_tracking` and `count_tracking`,
  and no public function hands a caller the tracking of a match the guard refuses.

A placebo instant is admissible when `placebo.py` says so (no run of the team within 3 s) and
the tracking can support it: the runner is detected at t', and every frame from t' - V to
t' + W exists in the candidate's period. The nearest admissible instant to t_c wins, ties to
the earlier one (protocol, `placebo.choice`). A placebo may fall in the other half of the
match, where the team attacks the other way: each leg of a pair is turned to the attack frame
by the sign of its own period, the run's at t_c and the placebo's at t'.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path

import duckdb
import numpy as np
from numpy.typing import NDArray

from tracklab.runs import effect, placebo
from tracklab.runs.data import require_readable
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


def whole_frames(seconds: float) -> int:
    """`seconds` as a count of frames, which must be whole: the formulas divide by the seconds
    a window names, so a window rounded to the nearest frame would be measured over another
    span than the one it divides by."""
    n = seconds * SAMPLE_RATE_HZ
    if n != int(n):
        raise ValueError(f"{seconds} s is not a whole number of frames at {SAMPLE_RATE_HZ} Hz")
    return int(n)


EFFECT_FRAMES = whole_frames(EFFECT_WINDOW_S)
VELOCITY_FRAMES = whole_frames(VELOCITY_WINDOW_S)
BEFORE_FRAMES = whole_frames(COVERAGE_BEFORE_START_S)
AFTER_FRAMES = whole_frames(COVERAGE_AFTER_END_S)
PLACEBO_RULE: placebo.Rule = "team_overlap" if PLACEBO_EXCLUDES_TEAMMATES_RUNS else "runner_overlap"

Bools = NDArray[np.bool_]
Leg = tuple[int, int]  # (period, instant): the run's at t_c, the placebo's at t'


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
class _Tracking:
    """The players of one match, frame by frame. `x`, `y` hold the venue frame in metres,
    NaN where the entity has no row in that frame; `detected` is the provider's flag.
    Row `i` is frame `frame0 + i`.

    No guard: `count_tracking` builds one for a match of either half and drops it with its
    scope. What a caller gets to hold is a `MatchTracking`."""

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
class MatchTracking(_Tracking):
    """A tracking a caller may hold: built, it passes `data.require_readable` for its match,
    whoever builds it, so a held-out match has none until the committed protocol is frozen in
    a clean tree. `dataclasses.replace` builds again, so relabelling runs the guard too. The
    functions that return values of a tracking take this class and nothing else."""

    def __post_init__(self) -> None:
        require_readable(self.match_id)


@dataclass(frozen=True)
class PairEffect:
    """One run minus its placebo, in metres, with the keys task 49 clusters by (the
    possession, the runner and the placebo instant) and the placebo leg alone, whose sd is
    the protocol's unit. Real-data instances are never printed or stored."""

    match_id: int
    run_id: str
    possession_id: str | None
    subtype: str
    player_id: int
    t_c: int
    placebo_period: int
    placebo_instant: int
    marker_m: float
    line_m: float
    placebo_marker_m: float
    placebo_line_m: float


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


def _read_tracking(data_dir: Path, match_id: int) -> _Tracking:
    """The players of `match_id` from silver, unguarded: the one place the frames are read,
    for `load_tracking` (past the guard) and `count_tracking` (counts alone). A match with no
    football frames raises."""
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
    return _Tracking(
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


def load_tracking(data_dir: Path, match_id: int) -> MatchTracking:
    """The players of `match_id` from silver, as a `MatchTracking`: the guard runs before a
    byte is read, and again as the tracking is built."""
    require_readable(match_id)
    raw = _read_tracking(data_dir, match_id)
    return MatchTracking(**{f.name: getattr(raw, f.name) for f in fields(raw)})


# --- geometry in the attack frame -------------------------------------------------------------


def _xy(t: _Tracking, frame: int, entity: int, sign: int) -> NDArray[np.float64]:
    i = frame - t.frame0
    return np.array([sign * t.x[i, entity], sign * t.y[i, entity]])


def _opponents(t: _Tracking, team: str) -> NDArray[np.intp]:
    return np.array([i for i, tm in enumerate(t.team) if tm != team], dtype=np.intp)


def _opponents_xy(
    t: _Tracking, frame: int, opponents: NDArray[np.intp], sign: int
) -> NDArray[np.float64]:
    i = frame - t.frame0
    return np.stack([sign * t.x[i, opponents], sign * t.y[i, opponents]], axis=1)


def window_bounds(t: _Tracking, run: Run) -> tuple[int, int, bool]:
    """The coverage window of a run, clipped to its period: (first frame, last frame, clipped)."""
    start, end = t.period_frames[run.period]
    lo = max(run.frame_start - BEFORE_FRAMES, start)
    hi = min(run.frame_end + AFTER_FRAMES, end)
    clipped = lo > run.frame_start - BEFORE_FRAMES or hi < run.frame_end + AFTER_FRAMES
    return lo, hi, clipped


def _frames_present(t: _Tracking, lo: int, hi: int) -> bool:
    return all(t.frame_present(f) for f in range(lo, hi + 1))


def _runner_detected(t: _Tracking, runner: int | None, lo: int, hi: int) -> bool:
    if runner is None:
        return False
    rows = [t.row(f) for f in range(lo, hi + 1)]
    return all(i is not None and bool(t.detected[i, runner]) for i in rows)


def _direction(t: _Tracking, run: Run) -> NDArray[np.float64] | None:
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


def run_direction(t: MatchTracking, run: Run) -> NDArray[np.float64] | None:
    """The run's direction in the attack frame of its period; None when the runner is not at
    both ends or the run is shorter than the protocol's minimum. A value: takes a
    `MatchTracking`, which passed the guard as it was built."""
    return _direction(t, run)


def run_length(t: MatchTracking, run: Run) -> float | None:
    """Metres between the runner's tracked positions at frame_start and frame_end, whatever
    the protocol's minimum (task 49 reports the lengths against it); None when the runner is
    not at both ends. A value: takes a `MatchTracking`."""
    runner = t.entity_index(run.runner)
    a, b = t.row(run.frame_start), t.row(run.frame_end)
    if runner is None or a is None or b is None:
        return None
    length = float(np.hypot(t.x[b, runner] - t.x[a, runner], t.y[b, runner] - t.y[a, runner]))
    return length if math.isfinite(length) else None


def line_height_at(t: MatchTracking, run: Run) -> float | None:
    """L(t_c) of the run's leg: the protocol's line height in the attack frame of the run's
    period, at frame_start, for task 49's contrast with the provider's
    `last_defensive_line_height_start`. None when the frame or the sign is missing or fewer
    than two outfield opponents have a position. A value: takes a `MatchTracking`."""
    sign = t.attack_sign.get((run.period, run.team))
    i = t.row(run.frame_start)
    if sign is None or i is None:
        return None
    opponents = _opponents(t, run.team)
    height = effect.line_height(sign * t.x[i, opponents], t.is_goalkeeper[opponents])
    return height if math.isfinite(height) else None


@dataclass(frozen=True)
class _LegInputs:
    """What the formulas of one leg read, as indices: the attack sign of the leg's period, the
    rows of t - V, t and t + W, the opponents and the marker among them. No position."""

    sign: int
    rows: tuple[int, int, int]
    opponents: NDArray[np.intp]
    marker: int


def _leg(t: _Tracking, run: Run, period: int, instant: int) -> _LegInputs | None:
    """The inputs of one leg, the run's (its period, t_c) or the placebo's (the candidate's
    period, t'), or None when any is missing: the runner and the attack sign of that period,
    the three frames inside it, a marker (nearest opponent at the instant) with a position at
    the three frames, and two outfield opponents with a position at each of them. Booleans and
    indices only, so `count_match` can ask it about a held-out match."""
    runner = t.entity_index(run.runner)
    sign = t.attack_sign.get((period, run.team))
    bounds = t.period_frames.get(period)
    if runner is None or sign is None or bounds is None:
        return None
    before, after = instant - VELOCITY_FRAMES, instant + EFFECT_FRAMES
    if before < bounds[0] or after > bounds[1]:
        return None
    rows = tuple(t.row(f) for f in (before, instant, after))
    if any(r is None for r in rows):
        return None
    i_before, i_at, i_after = (int(r) for r in rows if r is not None)
    opponents = _opponents(t, run.team)
    marker = effect.nearest_opponent(
        _xy(t, instant, runner, sign), _opponents_xy(t, instant, opponents, sign)
    )
    if marker is None:
        return None
    m = int(opponents[marker])
    if not all(np.isfinite(t.x[i, m]) and np.isfinite(t.y[i, m]) for i in (i_before, i_after)):
        return None
    outfield = opponents[~t.is_goalkeeper[opponents]]
    if any(np.isfinite(t.x[i, outfield]).sum() < 2 for i in (i_before, i_at, i_after)):
        return None
    return _LegInputs(sign, (i_before, i_at, i_after), opponents, m)


def quantities(
    t: MatchTracking,
    run: Run,
    period: int,
    instant: int,
    direction: NDArray[np.float64],
) -> tuple[float, float] | None:
    """Marker displacement and line-height residual of one leg, in metres: the run's at
    (run.period, t_c) or its placebo's at (candidate's period, t'), each turned to the attack
    frame by the sign of its own period. The marker is the opponent nearest to the runner at
    the instant. None when any input of the formulas is missing (`_leg`). A value: takes a
    `MatchTracking`, which passed the guard as it was built."""
    leg = _leg(t, run, period, instant)
    if leg is None:
        return None
    sign, (i_before, i_at, i_after), opponents, m = leg.sign, leg.rows, leg.opponents, leg.marker
    p_before, p_at, p_after = (_xy(t, t.frame0 + i, m, sign) for i in (i_before, i_at, i_after))
    residual = effect.residual_displacement(
        p_before, p_at, p_after, window_s=EFFECT_WINDOW_S, velocity_s=VELOCITY_WINDOW_S
    )
    heights = [
        effect.line_height(sign * t.x[i, opponents], t.is_goalkeeper[opponents])
        for i in (i_before, i_at, i_after)
    ]
    line = effect.residual_scalar(*heights, window_s=EFFECT_WINDOW_S, velocity_s=VELOCITY_WINDOW_S)
    marker_m = effect.project(residual, direction)
    if not (math.isfinite(marker_m) and math.isfinite(line)):
        return None
    return marker_m, line


# --- placebos against the tracking ----------------------------------------------------------


def placebo_supported(t: _Tracking, run: Run, period: int, instant: int) -> bool:
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


def choose_placebo(t: _Tracking, run: Run, candidates: Sequence[Leg]) -> Leg | None:
    """The supported (period, instant) nearest to t_c; ties go to the earlier one. The period
    travels with the instant: the placebo's leg is turned by the sign of its own period."""
    supported = [
        (period, instant)
        for period, instant in candidates
        if placebo_supported(t, run, period, instant)
    ]
    if not supported:
        return None
    return min(supported, key=lambda leg: (abs(leg[1] - run.frame_start), leg[1]))


def choose_second_placebo(
    t: _Tracking, run: Run, candidates: Sequence[Leg], first: Leg
) -> Leg | None:
    """The second placebo of task 49's real null (its review): among the candidates other
    than `first`, the one `choose_placebo` would pick next (supported by the tracking, nearest
    to t_c, ties to the earlier), whose leg the formulas can read (`_leg`, as both legs of a
    pair must) and whose window [t' - V, t' + W] is disjoint from the first's: in another
    period, or more than V + W frames from it. Booleans and indices only, like
    `choose_placebo`, so it runs on the unguarded tracking of either half."""
    span = VELOCITY_FRAMES + EFFECT_FRAMES
    admissible = [
        (period, instant)
        for period, instant in candidates
        if (period, instant) != first
        and (period != first[0] or abs(instant - first[1]) > span)
        and placebo_supported(t, run, period, instant)
        and _leg(t, run, period, instant) is not None
    ]
    if not admissible:
        return None
    return min(admissible, key=lambda leg: (abs(leg[1] - run.frame_start), leg[1]))


# --- the unit of the null: pairs that move together ------------------------------------------

UnitKey = tuple[str | None, tuple[int, int]]  # (possession id, (runner player_id, t'))


def components(keys: Sequence[Iterable[Hashable]]) -> list[int]:
    """One label per item, the connected component of the items that share any key, in order
    of first appearance: union-find over the keys. The unit of the null (`unit_labels`) and
    the blocks of task 49's real null are both built on it."""
    parent = list(range(len(keys)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first: dict[Hashable, int] = {}
    for i, own in enumerate(keys):
        for key in own:
            j = first.setdefault(key, i)
            if j != i:
                parent[find(i)] = find(j)
    labels: dict[int, int] = {}
    return [labels.setdefault(find(i), len(labels)) for i in range(len(keys))]


def unit_labels(keys: Sequence[UnitKey]) -> list[int]:
    """One label per pair, the connected component of the pairs that share a possession
    (`associated_player_possession_event_id`) or a placebo instant (same runner, same t'),
    in order of first appearance. The keys of one match only: possession ids and frames repeat
    across matches, so a caller never mixes matches here (task 49's null never does)."""
    return components(
        [
            ((("p", possession),) if possession is not None else ()) + (("i", instant),)
            for possession, instant in keys
        ]
    )


# --- counts: the door that returns no tracking value ----------------------------------------


@dataclass(frozen=True)
class MatchCounts:
    """Coverage of one match: runs, windows, detection and placebos. Integers, and fractions
    of detected opponent positions: no coordinate, no displacement. `analysis_units` (task
    49) holds, per subtype, the sizes of the groups the subtype's pairs form inside the
    null's units (`unit_labels` over the whole analysis set), sorted: the clustering the
    power needs of the half whose values stay closed."""

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
    analysis_units: tuple[tuple[int, ...], ...]


COUNT_FIELDS = tuple(
    f.name for f in fields(MatchCounts) if f.name not in ("by_subtype", "analysis_units")
)


def units_by_subtype(
    subtypes: Sequence[str], keys: Sequence[UnitKey]
) -> tuple[tuple[int, ...], ...]:
    """`MatchCounts.analysis_units` from the subtype and the unit key of each pair of one
    match: for each protocol subtype, the sorted sizes of its pairs per unit."""
    labels = unit_labels(keys)
    sizes: dict[str, dict[int, int]] = {s: {} for s in SUBTYPES}
    for subtype, label in zip(subtypes, labels, strict=True):
        per_unit = sizes.setdefault(subtype, {})
        per_unit[label] = per_unit.get(label, 0) + 1
    return tuple(tuple(sorted(sizes[s].values())) for s in SUBTYPES)


def count_match(
    t: _Tracking,
    runs: Sequence[Run],
    instants: Mapping[tuple[int, str], Sequence[Leg]],
) -> MatchCounts:
    """Everything `runs_coverage.csv` holds for one match, from booleans and integers: no
    value function is called, so it runs on the unguarded tracking of either half. The
    analysis set counts the pairs the estimator can form, with the same tests `pair_effects`
    applies (`_leg` on both legs, a direction of the minimum length)."""
    by_subtype = {s: 0 for s in SUBTYPES}
    complete = clipped_n = absent = detected_n = clean = found = analysis = 0
    fractions: list[float] = []
    in_set: list[tuple[str, UnitKey]] = []  # (subtype, unit key) of each analysis-set run
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
        if (
            is_clean
            and pick is not None
            and _direction(t, run) is not None
            and _leg(t, run, run.period, run.frame_start) is not None
            and _leg(t, run, *pick) is not None
        ):
            analysis += 1
            in_set.append((run.subtype, (run.possession_id, (run.player_id, pick[1]))))
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
        analysis_units=units_by_subtype([s for s, _ in in_set], [k for _, k in in_set]),
    )


def count_tracking(data_dir: Path, match_id: int) -> MatchCounts:
    """`count_match` on the tracking of `match_id` read from silver, for a match of either
    half. It loads the runs and the placebo instants itself, so a caller hands it no object
    that is called while the frames are live, and it counts nothing but what the warehouse
    holds. The frames live in this call alone and what returns is integers and detection
    fractions. A failure leaves no frame behind either: the exception is caught inside the
    scope, only its type and message are kept, and a fresh `RuntimeError` is raised outside,
    with no traceback frame that holds an array and no `__context__`."""
    msg: str | None = None
    counts: MatchCounts | None = None
    t: _Tracking | None = None
    try:
        t = _read_tracking(data_dir, match_id)
        runs = load_runs(data_dir, match_id)
        instants = placebo.placebo_instants(data_dir, [match_id], PLACEBO_RULE)
        counts = count_match(t, runs, instants)
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
    finally:
        t = None
    if counts is None:
        raise RuntimeError(f"counting match {match_id} failed: {msg}") from None
    return counts


# --- effects: the door that returns values ----------------------------------------------------


def pair_effects(
    t: MatchTracking,
    runs: Sequence[Run],
    instants: Mapping[tuple[int, str], Sequence[Leg]],
) -> list[PairEffect]:
    """One `PairEffect` per clean run with a direction and a supported placebo: the quantities
    of the run's leg at t_c minus those of the placebo's leg at t', each in the attack frame of
    its own period, both along the run's direction. A value: takes a `MatchTracking`, which
    passed the guard as it was built, so a held-out match has none until the protocol
    committed in HEAD is frozen in a clean tree (`data`, which takes no path: the committed
    protocol is the only one asked). Never call it on real data to print."""
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
        own = quantities(t, run, run.period, run.frame_start, direction)
        other = quantities(t, run, *pick, direction)
        if own is None or other is None:
            continue
        out.append(
            PairEffect(
                match_id=t.match_id,
                run_id=run.event_id,
                possession_id=run.possession_id,
                subtype=run.subtype,
                player_id=run.player_id,
                t_c=run.frame_start,
                placebo_period=pick[0],
                placebo_instant=pick[1],
                marker_m=own[0] - other[0],
                line_m=own[1] - other[1],
                placebo_marker_m=other[0],
                placebo_line_m=other[1],
            )
        )
    return out


def pair_unit_key(pair: PairEffect) -> UnitKey:
    """The key `unit_labels` clusters a pair by: what `count_match` builds for the same run,
    so the units of the open half (from pairs) and of the closed one (from counts) agree."""
    return (pair.possession_id, (pair.player_id, pair.placebo_instant))
