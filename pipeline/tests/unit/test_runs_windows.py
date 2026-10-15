"""Windows, placebos and the estimator, validated on synthetic matches (task 48).

The estimator is run end to end only here, on matches fabricated with a known effect: real
data produces counts (`runs_coverage.csv`) and nothing else. The generator writes positions
from geometry it owns (an explicit marker 2 m from the runner, an explicit line of two
defenders, a goalkeeper behind them) and never calls the estimator, so the two cannot share
a defect. Since the second review of 47-48 the match has two periods with opposite attack
signs, the defence drifts the same way in the run scene and in the placebo scene (the placebo
baseline is not zero, so a placebo leg turned the wrong way shows), half the runs find their
placebo in the other half of the match, every run has four candidates of which one is the
right one, and one test writes the match as silver and bronze parquet and loads it back
through `load_tracking` and `load_runs`.

Mutations recorded in tasks/todo.md: the sign of the run direction flipped in
`effect.run_direction` fails the planted-effect test; the marker taken at t_c + 1 s in
`windows.quantities` fails the test that pins it at t_c; the placebo leg turned by the run's
period (`sign = t.attack_sign[(run.period, ...)]` in `_leg`) fails the planted-effect tests
and the two-period test; the placebo leg's sign flipped fails the planted-effect tests. Since
the third review, each condition of `count_match` and each rule of `_leg` fails the sabotaged
matches, and the guard is a shape (`MatchTracking`) rather than a flag: the held-out test
walks what every public name of `runs.*` returns.
"""

from __future__ import annotations

import csv
import importlib
import inspect
import math
import pkgutil
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from types import ModuleType

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tracklab.paths import data_root
from tracklab.runs import candidates as effect_probe
from tracklab.runs import coverage, data, effect, placebo, probe, protocol, windows
from tracklab.runs.coverage import COVERAGE_NAME, HEADER, _row, coverage_rows, run_runs_coverage
from tracklab.runs.data import (
    HeldOutLocked,
    counting_match_ids,
    load_half,
    match_halves,
    require_readable,
)
from tracklab.runs.protocol import (
    COVERAGE_AFTER_END_S,
    COVERAGE_BEFORE_START_S,
    EFFECT_WINDOW_S,
    MIN_RUN_LENGTH_M,
    PLACEBO_EXCLUDES_TEAMMATES_RUNS,
    SAMPLE_RATE_HZ,
    STAGE_DESIGN,
    VELOCITY_WINDOW_S,
    read_protocol,
    render,
    seal,
)
from tracklab.runs.windows import (
    AFTER_FRAMES,
    BEFORE_FRAMES,
    EFFECT_FRAMES,
    PLACEBO_RULE,
    SUBTYPES,
    VELOCITY_FRAMES,
    MatchCounts,
    MatchTracking,
    Run,
    choose_placebo,
    choose_second_placebo,
    count_match,
    count_tracking,
    load_runs,
    load_tracking,
    pair_effects,
    placebo_supported,
    quantities,
    run_direction,
    whole_frames,
    window_bounds,
)

PIPELINE = Path(__file__).resolve().parents[2]
REPORTS = PIPELINE / "reports"
PROTOCOL = REPORTS / "runs_protocol.json"
FIXTURES = PIPELINE / "tests" / "fixtures" / "data"
CI_FIXTURE_MATCH = 1874553
HELD_OUT_MATCH = 1899585

BLOCK = 100
ANCHOR = 30  # offset of t_c inside a scene: W + V frames before it, for the pre-trend leg
RUN_FRAMES = 20
APPROACH_M_PER_FRAME = 0.1  # the runner walks towards t_c along d: a direction at t_c (task 50)
BALL_BEHIND_M = 8.0  # the ball sits 8 m behind the runner's start, along -x_att
PLANTED_MARKER_M = 2.0
PLANTED_LINE_M = 1.0
# What the defence does anyway, in the run scene and in the placebo scene alike: the placebo
# baseline. Zero would let a placebo leg turned the wrong way pass unseen.
BASELINE_MARKER_M = 1.0
BASELINE_LINE_M = 1.0
TEAM, OTHER = "fb:100", "fb:200"
# The runner's team attacks towards -x in the venue frame in period 1 and towards +x in
# period 2, so x_att = SIGN[period] * x_m.
SIGN = {1: -1, 2: 1}


def test_the_windows_are_the_protocols() -> None:
    assert EFFECT_FRAMES == whole_frames(EFFECT_WINDOW_S) == 20
    assert VELOCITY_FRAMES == whole_frames(VELOCITY_WINDOW_S) == 5
    assert BEFORE_FRAMES == whole_frames(COVERAGE_BEFORE_START_S) == 10
    assert AFTER_FRAMES == whole_frames(COVERAGE_AFTER_END_S) == 30
    windows_ = read_protocol(PROTOCOL)["design"]["windows"]
    assert windows_["effect_s"][1] == EFFECT_WINDOW_S
    assert windows_["velocity_s"] == VELOCITY_WINDOW_S
    assert PLACEBO_RULE == ("team_overlap" if PLACEBO_EXCLUDES_TEAMMATES_RUNS else "runner_overlap")


def test_a_window_must_be_a_whole_number_of_frames() -> None:
    """The residual divides by the seconds a window names (`effect.residual_displacement`),
    while the positions are taken `round(W * fs)` frames apart: the two agree only when
    `W * fs` is whole, so a window that is not is refused instead of rounded."""
    assert whole_frames(2.0) == 20
    assert whole_frames(0.5) == 5
    with pytest.raises(ValueError, match="whole number of frames"):
        whole_frames(0.25)  # 2.5 frames at 10 Hz
    with pytest.raises(ValueError, match="whole number of frames"):
        whole_frames(0.33)
    for seconds in (
        EFFECT_WINDOW_S,
        VELOCITY_WINDOW_S,
        COVERAGE_BEFORE_START_S,
        COVERAGE_AFTER_END_S,
    ):
        assert float(seconds * SAMPLE_RATE_HZ).is_integer()


# --- pure functions -------------------------------------------------------------------------


def test_run_direction_points_from_start_to_end_and_has_a_minimum() -> None:
    d = effect.run_direction(np.array([0.0, 0.0]), np.array([3.0, 4.0]), MIN_RUN_LENGTH_M)
    assert d is not None
    assert d.tolist() == pytest.approx([0.6, 0.8])
    assert (
        effect.run_direction(np.array([0.0, 0.0]), np.array([0.5, 0.0]), MIN_RUN_LENGTH_M) is None
    )
    assert effect.run_direction(np.array([0.0, 0.0]), np.array([np.nan, 0.0]), 1.0) is None


def test_residual_removes_what_the_velocity_predicted() -> None:
    # 1 m/s along +x for 0.5 s before, then 1 m/s for 2 s: the residual is zero.
    steady = effect.residual_displacement(
        np.array([0.0, 0.0]),
        np.array([0.5, 0.0]),
        np.array([2.5, 0.0]),
        window_s=2.0,
        velocity_s=0.5,
    )
    assert steady.tolist() == pytest.approx([0.0, 0.0])
    # The same, plus a 1.5 m push along +y during the window.
    pushed = effect.residual_displacement(
        np.array([0.0, 0.0]),
        np.array([0.5, 0.0]),
        np.array([2.5, 1.5]),
        window_s=2.0,
        velocity_s=0.5,
    )
    assert effect.project(pushed, np.array([0.0, 1.0])) == pytest.approx(1.5)
    assert effect.project(pushed, np.array([0.0, -1.0])) == pytest.approx(-1.5)


def test_line_height_is_the_two_deepest_outfield_opponents() -> None:
    x = np.array([50.0, 30.0, 28.0, 10.0, -5.0])
    keeper = np.array([True, False, False, False, False])
    assert effect.line_height(x, keeper) == pytest.approx(29.0)
    assert effect.line_height(x[:2], keeper[:2]) != effect.line_height(x[:2], keeper[:2])  # NaN
    assert effect.residual_scalar(29.0, 29.0, 30.0, window_s=2.0, velocity_s=0.5) == pytest.approx(
        1.0
    )


def test_standardise_and_mean_and_se() -> None:
    assert effect.standardise(np.array([2.0, -1.0]), 2.0).tolist() == [1.0, -0.5]
    with pytest.raises(ValueError):
        effect.standardise(np.array([1.0]), 0.0)
    mean, se = effect.mean_and_se(np.array([1.0, 2.0, 3.0, np.nan]))
    assert mean == pytest.approx(2.0)
    assert se == pytest.approx(1.0 / math.sqrt(3))


# --- the synthetic match --------------------------------------------------------------------


def _scene(
    rng: np.random.Generator,
    direction_angle: float,
    marker_push: float,
    line_push: float,
    pre_push: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One scene of BLOCK frames in the attack frame: runner (BLOCK, 2), opponents
    (BLOCK, 12, 2), ball (BLOCK, 2). Opponent 0 is the marker, 1 and 2 the two deepest
    outfield players, 3 to 10 the rest of the line-up, 11 the goalkeeper. `marker_push` and
    `line_push` are the whole residual of the scene (planted effect plus baseline);
    `pre_push` moves the marker along d over [t_c - W, t_c], before the runner starts (task
    50: a planted pre-trend, M3). The runner walks slowly along d before t_c, so his
    direction at t_c exists, and the ball sits behind him along -x."""
    k = np.arange(BLOCK) - ANCHOR  # frames relative to t_c
    d = np.array([math.cos(direction_angle), math.sin(direction_angle)])
    start = np.array([rng.uniform(-22.0, -14.0), rng.uniform(-3.0, 3.0)])
    run_progress = np.clip(k, 0, RUN_FRAMES) * 0.5  # 5 m/s: 10 m over the run
    approach = np.clip(k, None, 0) * APPROACH_M_PER_FRAME  # 1 m/s before t_c, 0 at t_c
    runner = start + (run_progress + approach)[:, None] * d
    ball = np.tile(start - np.array([BALL_BEHIND_M, 0.0]), (BLOCK, 1))

    opponents = np.zeros((BLOCK, 12, 2))
    ramp = np.clip(k, 0, EFFECT_FRAMES) / EFFECT_FRAMES
    pre_ramp = (
        np.clip(k + EFFECT_FRAMES, 0, EFFECT_FRAMES) / EFFECT_FRAMES
    )  # 0 at t_c - W, 1 at t_c
    # the marker: 2 m from the runner at t_c, its own velocity and acceleration, plus the push
    around = rng.uniform(0, 2 * math.pi)
    at_anchor = start + 2.0 * np.array([math.cos(around), math.sin(around)])
    v0 = rng.normal(0.0, 1.0, 2) / SAMPLE_RATE_HZ
    dv = rng.normal(0.0, 0.25, 2) / SAMPLE_RATE_HZ
    own = at_anchor + np.outer(k, v0) + np.outer(np.clip(k, 0, None), dv)
    opponents[:, 0] = own + (marker_push * ramp + pre_push * pre_ramp)[:, None] * d
    # the rest: static far from the runner, the two deepest at x = 30 and 28, keeper at 50
    rest = [(30.0, 8.0), (28.0, -8.0)] + [
        (rng.uniform(2.0, 20.0), rng.uniform(-25.0, 25.0)) for _ in range(8)
    ]
    for j, (x0, y0) in enumerate(rest, start=1):
        opponents[:, j] = (x0, y0)
    opponents[:, 11] = (50.0, 0.0)
    opponents[:, 1, 0] += line_push * ramp
    opponents[:, 2, 0] += line_push * ramp
    opponents += rng.normal(0.0, 0.05, opponents.shape)  # measurement jitter
    return runner, opponents, ball, d


Instants = dict[tuple[int, str], list[tuple[int, int]]]


def _per_subtype(value: float | Mapping[str, float], subtype: str) -> float:
    return value if isinstance(value, float | int) else value.get(subtype, 0.0)


def _synthetic_raw(
    n_runs: int,
    marker_push: float,
    line_push: float,
    seed: int,
    match_id: int = CI_FIXTURE_MATCH,
    *,
    pre_push: float | Mapping[str, float] = 0.0,
    baseline_sd: float = 0.0,
    extrapolated: Mapping[str, float] | None = None,
) -> tuple[windows._Tracking, list[Run], Instants]:
    """`n_runs` runs, each with one placebo scene, in blocks of BLOCK frames: blocks 0 to
    n - 1 hold the run scenes, n to 2n - 1 the placebo scenes. Period 1 ends after the first
    half of the run scenes, so those runs find their placebo in the other half of the match
    (attack sign -1 against +1) and the rest in their own. Both scenes carry the baseline
    drift; the run scene carries the planted effect on top. Every run gets four candidates:
    a nearer instant where the runner is undetected, the placebo instant, a farther supported
    instant of the same scene, and the placebo instant labelled with the wrong period.
    Unguarded, as `count_tracking` sees a match: `_synthetic` wraps it in a `MatchTracking`.

    Task 50's knobs, all off by default: `pre_push` (a float, or per subtype) moves the
    marker before the runner starts, over [t_c - W, t_c] of the run scene; `baseline_sd`
    draws a baseline per run, shared by its two scenes, so the placebo sd grows while the
    pair sd does not (a few pairs become a probable subtype); `extrapolated` replaces the
    planted push by its value on the second run of each named subtype in the match and
    flags that run's marker undetected over its window, so the effect of the fully detected
    pairs is smaller than the effect of every pair (M4)."""
    rng = np.random.default_rng(seed)
    n_blocks = 2 * n_runs
    n_frames = n_blocks * BLOCK
    n_period1 = n_runs // 2
    period_frames = {1: (0, n_period1 * BLOCK - 1), 2: (n_period1 * BLOCK, n_frames - 1)}

    def period_of(block: int) -> int:
        return 1 if block < n_period1 else 2

    x = np.full((n_frames, 13), np.nan)
    y = np.full((n_frames, 13), np.nan)
    ball_x = np.full(n_frames, np.nan)
    ball_y = np.full(n_frames, np.nan)
    detected = np.ones((n_frames, 13), dtype=np.bool_)
    runs: list[Run] = []
    instants: Instants = {}
    for i in range(n_runs):
        subtype = SUBTYPES[i % len(SUBTYPES)]
        angle = rng.uniform(-math.pi / 3, math.pi / 3)
        baseline = rng.normal(0.0, baseline_sd) if baseline_sd > 0.0 else 0.0
        push = marker_push
        undetected = (extrapolated or {}).get(subtype) is not None and (i // len(SUBTYPES)) % 3 == 1
        if undetected and extrapolated is not None:
            push = extrapolated[subtype]
        scenes = (
            (i, (push + BASELINE_MARKER_M + baseline, line_push + BASELINE_LINE_M)),
            (n_runs + i, (BASELINE_MARKER_M + baseline, BASELINE_LINE_M)),
        )
        for block, (marker, line) in scenes:
            pre = _per_subtype(pre_push, subtype) if block == i else 0.0
            runner, opponents, ball, _ = _scene(rng, angle, marker, line, pre)
            sign = SIGN[period_of(block)]
            rows = slice(block * BLOCK, (block + 1) * BLOCK)
            x[rows, 0], y[rows, 0] = (sign * runner).T
            for j in range(12):
                x[rows, 1 + j], y[rows, 1 + j] = (sign * opponents[:, j]).T
            ball_x[rows], ball_y[rows] = (sign * ball).T
        t_c = i * BLOCK + ANCHOR
        t_p = (n_runs + i) * BLOCK + ANCHOR
        if undetected:
            detected[t_c - VELOCITY_FRAMES : t_c + EFFECT_FRAMES + 1, 1] = False
        run = Run(
            match_id,
            f"r{i}",
            7,
            100,
            period_of(i),
            t_c,
            t_c + RUN_FRAMES,
            subtype,
            f"p{i}",
        )
        runs.append(run)
        detected[t_p - 10, 0] = False
        instants[(match_id, run.event_id)] = [(2, t_p + 30), (2, t_p - 10), (1, t_p), (2, t_p)]
    tracking = windows._Tracking(
        match_id=match_id,
        frame0=0,
        x=x,
        y=y,
        detected=detected,
        entities=("fb:7", *(f"fb:{300 + j}" for j in range(12))),
        team=(TEAM, *([OTHER] * 12)),
        is_goalkeeper=np.array([False] * 12 + [True], dtype=np.bool_),
        period_frames=period_frames,
        attack_sign={
            (1, TEAM): SIGN[1],
            (2, TEAM): SIGN[2],
            (1, OTHER): -SIGN[1],
            (2, OTHER): -SIGN[2],
        },
        ball_x=ball_x,
        ball_y=ball_y,
    )
    return tracking, runs, instants


def _guarded(raw: windows._Tracking) -> MatchTracking:
    return MatchTracking(**{f.name: getattr(raw, f.name) for f in fields(raw)})


def _synthetic(
    n_runs: int,
    marker_push: float,
    line_push: float,
    seed: int,
    match_id: int = CI_FIXTURE_MATCH,
) -> tuple[MatchTracking, list[Run], Instants]:
    """`_synthetic_raw` as a `MatchTracking`: refused as it is built when `match_id` is held
    out and the committed protocol is in design."""
    raw, runs, instants = _synthetic_raw(n_runs, marker_push, line_push, seed, match_id)
    return _guarded(raw), runs, instants


def _placebo_instant(run: Run, instants: Instants) -> tuple[int, int]:
    return instants[(run.match_id, run.event_id)][-1]


def _parquet(path: Path, table: pa.Table) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _provider_lines(
    tracking: windows._Tracking, runs: list[Run], pitch_length: float
) -> tuple[list[float], list[float]]:
    """What the provider would write as `last_defensive_line_x_start` and
    `last_defensive_line_height_start`: the mean x_att at t_c of the two deepest outfield
    opponents, straight from the arrays (opponents are columns 1 to 11, the keeper 12), and
    its height from the defending goal line of a pitch of `pitch_length`. The provider's own
    identity, x + height = pitch_length / 2, by construction; never 52.5 unless the pitch is
    105 m, which no fixture match is, so a reader converting the height with a fixed 52.5
    lands 0.5 m or more off."""
    xs, heights = [], []
    for run in runs:
        x_att = SIGN[run.period] * tracking.x[run.frame_start, 1:12]
        x = float(np.sort(x_att)[-2:].mean())
        xs.append(x)
        heights.append(pitch_length / 2.0 - x)
    return xs, heights


def _write_warehouse(
    root: Path,
    tracking: windows._Tracking,
    runs: list[Run],
    instants: Instants | None = None,
    pitch_length: float = 104.0,
) -> None:
    """The synthetic match as the silver and bronze files `load_tracking`, `load_runs`,
    `placebo` and the probe read, in their layout and with their columns: `frames` (plus a
    ball row, which the player filter must drop), `dim_period`, `dim_team_period`,
    `match_players`, `match` (the pitch length, never 105 m: see `_provider_lines`),
    `dynamic_events` and `phases_of_play`. Without `instants` the events are the runs alone,
    so no placebo candidate comes from them; with them, each run gets its candidates as the
    SQL of `placebo.py` produces them (task 49): a teammate's `player_possession` at t' in
    its own phase, of the run's own phase type, so `placebo_instants` returns exactly the
    given list per run."""
    assert pitch_length != 105.0
    m = tracking.match_id
    provider_x, provider_height = _provider_lines(tracking, runs, pitch_length)
    present = np.isfinite(tracking.x)
    rows, cols = np.nonzero(present)
    frames = pa.table(
        {
            "frame_native": pa.array(tracking.frame0 + rows, pa.int64()),
            "entity_id": [tracking.entities[j] for j in cols],
            "entity_kind": ["player"] * len(rows),
            "team_id": [tracking.team[j] for j in cols],
            "x_m": tracking.x[rows, cols],
            "y_m": tracking.y[rows, cols],
            "is_detected": tracking.detected[rows, cols],
        }
    )
    if tracking.ball_x is not None and tracking.ball_y is not None:
        (ball_rows,) = np.nonzero(np.isfinite(tracking.ball_x))
        ball_xy = (tracking.ball_x[ball_rows], tracking.ball_y[ball_rows])
    else:  # one ball row, which the player filter must drop
        ball_rows, ball_xy = np.zeros(1, dtype=np.int64), (np.zeros(1), np.zeros(1))
    ball = pa.table(
        {
            "frame_native": pa.array(tracking.frame0 + ball_rows, pa.int64()),
            "entity_id": ["fb:ball"] * len(ball_rows),
            "entity_kind": ["ball"] * len(ball_rows),
            "team_id": pa.array([None] * len(ball_rows), pa.string()),
            "x_m": ball_xy[0],
            "y_m": ball_xy[1],
            "is_detected": [True] * len(ball_rows),
        }
    )
    _parquet(
        root / "silver" / "frames" / "sport=football" / f"native_match_id={m}" / "data.parquet",
        pa.concat_tables([frames, ball]),
    )
    _parquet(
        root / "silver" / "dim_period" / f"{m}.parquet",
        pa.table(
            {
                "match_id": [f"fb:{m}"] * len(tracking.period_frames),
                "period": list(tracking.period_frames),
                "frame_native_start": [a for a, _ in tracking.period_frames.values()],
                "frame_native_end": [b for _, b in tracking.period_frames.values()],
            }
        ),
    )
    _parquet(
        root / "silver" / "dim_team_period" / f"{m}.parquet",
        pa.table(
            {
                "match_id": [f"fb:{m}"] * len(tracking.attack_sign),
                "period": [p for p, _ in tracking.attack_sign],
                "team_id": [t for _, t in tracking.attack_sign],
                "attack_sign": list(tracking.attack_sign.values()),
            }
        ),
    )
    _parquet(
        root / "bronze" / "football" / "match_players" / f"{m}.parquet",
        pa.table(
            {
                "id": [int(e.removeprefix("fb:")) for e in tracking.entities],
                "match_id": [m] * len(tracking.entities),
                "player_role_name": [
                    "Goalkeeper" if keeper else "Defender" for keeper in tracking.is_goalkeeper
                ],
            }
        ),
    )
    _parquet(
        root / "bronze" / "football" / "match" / f"{m}.parquet",
        pa.table({"match_id": [m], "pitch_length": [pitch_length], "pitch_width": [68.0]}),
    )
    # the events: the runs, each with its phase type and the frame of its own possession,
    # then (with `instants`) a teammate's possession per candidate, in a phase of its own
    events: dict[str, list[object]] = {
        "match_id": [r.match_id for r in runs],
        "event_id": [r.event_id for r in runs],
        "event_type": ["off_ball_run"] * len(runs),
        "event_subtype": [r.subtype for r in runs],
        "player_id": [r.player_id for r in runs],
        "team_id": [r.team_id for r in runs],
        "period": [r.period for r in runs],
        "frame_start": [r.frame_start for r in runs],
        "frame_end": [r.frame_end for r in runs],
        "associated_player_possession_event_id": [r.possession_id for r in runs],
        "phase_index": [r.period for r in runs],
        "team_in_possession_phase_type": [f"type_{r.event_id}" for r in runs],
        "associated_player_possession_frame_start": [
            r.frame_start if instants else None for r in runs
        ],
        "last_defensive_line_x_start": provider_x,
        "last_defensive_line_height_start": provider_height,
    }
    phases: dict[str, list[object]] = {
        "match_id": [m] * len(tracking.period_frames),
        "index": list(tracking.period_frames),
        "period": list(tracking.period_frames),
        "frame_start": [a for a, _ in tracking.period_frames.values()],
        "frame_end": [b for _, b in tracking.period_frames.values()],
    }
    phase_index = 1000
    for run in runs:
        for period, instant in (instants or {}).get((m, run.event_id), ()):
            phase_index += 1
            events["match_id"].append(m)
            events["event_id"].append(f"pp_{phase_index}")
            events["event_type"].append("player_possession")
            events["event_subtype"].append(None)
            events["player_id"].append(8)  # a teammate, never the runner
            events["team_id"].append(run.team_id)
            events["period"].append(period)
            events["frame_start"].append(instant)
            events["frame_end"].append(instant + 1)
            events["associated_player_possession_event_id"].append(None)
            events["phase_index"].append(phase_index)
            events["team_in_possession_phase_type"].append(f"type_{run.event_id}")
            events["associated_player_possession_frame_start"].append(None)
            events["last_defensive_line_x_start"].append(None)
            events["last_defensive_line_height_start"].append(None)
            phases["match_id"].append(m)
            phases["index"].append(phase_index)
            phases["period"].append(period)
            phases["frame_start"].append(instant - 1)
            phases["frame_end"].append(instant + 1)
    schema = pa.schema(
        [
            ("match_id", pa.int64()),
            ("event_id", pa.string()),
            ("event_type", pa.string()),
            ("event_subtype", pa.string()),
            ("player_id", pa.int64()),
            ("team_id", pa.int64()),
            ("period", pa.int64()),
            ("frame_start", pa.int64()),
            ("frame_end", pa.int64()),
            ("associated_player_possession_event_id", pa.string()),
            ("phase_index", pa.int64()),
            ("team_in_possession_phase_type", pa.string()),
            ("associated_player_possession_frame_start", pa.int64()),
            ("last_defensive_line_x_start", pa.float64()),
            ("last_defensive_line_height_start", pa.float64()),
        ]
    )
    _parquet(
        root / "bronze" / "football" / "dynamic_events" / f"{m}.parquet",
        pa.table(events, schema=schema),
    )
    _parquet(root / "bronze" / "football" / "phases_of_play" / f"{m}.parquet", pa.table(phases))


def _recovered(push: float, line: float, seed: int) -> tuple[float, float, float, float, int]:
    tracking, runs, instants = _synthetic(3000, push, line, seed)
    pairs = pair_effects(tracking, runs, instants)
    marker = np.array([p.marker_m for p in pairs])
    line_m = np.array([p.line_m for p in pairs])
    (m_mean, m_se), (l_mean, l_se) = effect.mean_and_se(marker), effect.mean_and_se(line_m)
    return m_mean, m_se, l_mean, l_se, len(pairs)


def test_the_estimator_recovers_a_planted_effect() -> None:
    m_mean, m_se, l_mean, l_se, n = _recovered(PLANTED_MARKER_M, PLANTED_LINE_M, seed=48)
    assert n == 3000
    assert abs(m_mean - PLANTED_MARKER_M) / PLANTED_MARKER_M < 0.05
    assert abs(l_mean - PLANTED_LINE_M) / PLANTED_LINE_M < 0.05
    # and the error is small against the noise, so 5 % is not luck
    assert m_se < 0.02 * PLANTED_MARKER_M
    assert l_se < 0.02 * PLANTED_LINE_M


def test_the_estimator_gives_zero_within_two_standard_errors_without_an_effect() -> None:
    m_mean, m_se, l_mean, l_se, n = _recovered(0.0, 0.0, seed=49)
    assert n == 3000
    assert m_se > 0.0 and l_se > 0.0
    assert abs(m_mean) <= 2 * m_se
    assert abs(l_mean) <= 2 * l_se


def test_a_push_against_the_run_reads_negative() -> None:
    m_mean, _, _, _, _ = _recovered(-PLANTED_MARKER_M, 0.0, seed=50)
    assert m_mean == pytest.approx(-PLANTED_MARKER_M, rel=0.05)


def test_the_placebo_baseline_is_not_zero_and_half_the_placebos_cross_the_half_time() -> None:
    """What makes the generator sensitive to a placebo leg turned the wrong way: the placebo
    quantities themselves are the baseline, not zero, and half the runs are in period 1 with
    their placebo in period 2."""
    tracking, runs, instants = _synthetic(400, PLANTED_MARKER_M, PLANTED_LINE_M, seed=53)
    crossing = [r for r in runs if _placebo_instant(r, instants)[0] != r.period]
    assert len(crossing) == 200 and all(r.period == 1 for r in crossing)
    placebo_marker, placebo_line = [], []
    for run in runs:
        d = run_direction(tracking, run)
        assert d is not None
        got = quantities(tracking, run, *_placebo_instant(run, instants), d)
        assert got is not None
        placebo_marker.append(got[0])
        placebo_line.append(got[1])
    assert float(np.mean(placebo_marker)) == pytest.approx(BASELINE_MARKER_M, rel=0.1)
    assert float(np.mean(placebo_line)) == pytest.approx(BASELINE_LINE_M, rel=0.1)


def test_the_line_ignores_the_goalkeeper() -> None:
    tracking, runs, instants = _synthetic(200, 0.0, PLANTED_LINE_M, seed=51)
    keeper_counts_as_outfield = MatchTracking(
        **{
            **{f.name: getattr(tracking, f.name) for f in fields(MatchTracking)},
            "is_goalkeeper": np.zeros(13, dtype=np.bool_),
        }
    )
    with_keeper = pair_effects(keeper_counts_as_outfield, runs, instants)
    without = pair_effects(tracking, runs, instants)
    mean_with = float(np.mean([p.line_m for p in with_keeper]))
    mean_without = float(np.mean([p.line_m for p in without]))
    assert mean_without == pytest.approx(PLANTED_LINE_M, rel=0.1)
    assert abs(mean_with - PLANTED_LINE_M) > 0.3


def test_every_run_picks_its_placebo_among_the_four_candidates() -> None:
    tracking, runs, instants = _synthetic(60, PLANTED_MARKER_M, PLANTED_LINE_M, seed=54)
    for run in runs:
        candidates = instants[(run.match_id, run.event_id)]
        assert len(candidates) == 4
        assert choose_placebo(tracking, run, candidates) == _placebo_instant(run, instants)
    counts = count_match(tracking, runs, instants)
    assert counts.placebo_found == counts.analysis_set == counts.clean == 60


def test_the_loading_path_reproduces_the_synthetic_match(tmp_path: Path) -> None:
    """The match written as silver and bronze parquet and read back through `load_tracking`
    and `load_runs` is the match in memory: same geometry per entity (silver sorts the entity
    names, the generator does not), same periods, signs and goalkeeper, and the estimator and
    the counts give the same answers on both."""
    tracking, runs, instants = _synthetic(120, PLANTED_MARKER_M, PLANTED_LINE_M, seed=55)
    _write_warehouse(tmp_path, tracking, runs)
    loaded = load_tracking(tmp_path, CI_FIXTURE_MATCH)
    assert type(loaded) is MatchTracking
    assert loaded.match_id == tracking.match_id and loaded.frame0 == tracking.frame0
    assert loaded.period_frames == tracking.period_frames
    assert loaded.attack_sign == tracking.attack_sign
    assert sorted(loaded.entities) == sorted(tracking.entities) and "ball" not in loaded.entities
    order = [loaded.entity_index(e) for e in tracking.entities]
    assert all(i is not None for i in order)
    assert tuple(loaded.team[i] for i in order if i is not None) == tracking.team
    assert loaded.is_goalkeeper[order].tolist() == tracking.is_goalkeeper.tolist()
    np.testing.assert_array_equal(loaded.x[:, order], tracking.x)
    np.testing.assert_array_equal(loaded.y[:, order], tracking.y)
    np.testing.assert_array_equal(loaded.detected[:, order], tracking.detected)
    assert loaded.ball_x is not None and loaded.ball_y is not None
    np.testing.assert_array_equal(loaded.ball_x, tracking.ball_x)
    np.testing.assert_array_equal(loaded.ball_y, tracking.ball_y)
    assert load_runs(tmp_path, CI_FIXTURE_MATCH) == runs
    assert placebo.placebo_instants(tmp_path, [CI_FIXTURE_MATCH], PLACEBO_RULE) == {}
    in_memory = pair_effects(tracking, runs, instants)
    from_disk = pair_effects(loaded, runs, instants)
    assert len(in_memory) == len(from_disk) == 120
    for a, b in zip(in_memory, from_disk, strict=True):
        assert (a.run_id, a.subtype, a.possession_id) == (b.run_id, b.subtype, b.possession_id)
        assert a.marker_m == pytest.approx(b.marker_m, abs=1e-9)
        assert a.line_m == pytest.approx(b.line_m, abs=1e-9)
    assert count_match(loaded, runs, instants) == count_match(tracking, runs, instants)
    # the warehouse writes no off-ball events, so the instants it yields are none
    assert count_tracking(tmp_path, CI_FIXTURE_MATCH) == count_match(tracking, runs, {})


def test_a_failed_count_leaves_no_array_in_reach(tmp_path: Path) -> None:
    """A warehouse without `silver/dim_period` fails inside `_read_tracking`, after the raw
    columns of the match were read: the `RuntimeError` that comes out carries the type and
    the message and no traceback frame that holds an ndarray, and no `__context__`."""
    tracking, runs, _ = _synthetic(3, 1.0, 0.0, seed=7, match_id=CI_FIXTURE_MATCH)
    _write_warehouse(tmp_path, tracking, runs)
    shutil.rmtree(tmp_path / "silver" / "dim_period")
    with pytest.raises(RuntimeError) as caught:
        count_tracking(tmp_path, CI_FIXTURE_MATCH)
    exc = caught.value
    assert "dim_period" in str(exc) and exc.__context__ is None
    frames = 0
    tb = exc.__traceback__
    while tb is not None:
        frames += 1
        held = [k for k, v in tb.tb_frame.f_locals.items() if isinstance(v, np.ndarray)]
        held += [
            k
            for k, v in tb.tb_frame.f_locals.items()
            if isinstance(v, dict) and any(isinstance(w, np.ndarray) for w in v.values())
        ]
        assert held == [], (tb.tb_frame.f_code.co_name, held)
        tb = tb.tb_next
    assert frames >= 1


# --- the marker is the nearest opponent at t_c --------------------------------------------


def _passing_by() -> tuple[MatchTracking, Run]:
    """The runner walks along +x past two static opponents: A is nearest at t_c, B at
    t_c + 1 s. A is pushed 1 m along +x after t_c, B is not moved."""
    n = 100
    t_c = 40
    k = np.arange(n)
    x = np.full((n, 5), np.nan)
    y = np.full((n, 5), np.nan)
    x[:, 0], y[:, 0] = 0.5 * (k - t_c) - 4.0, 0.0  # the runner
    x[:, 1], y[:, 1] = -4.0 + np.clip(k - t_c, 0, EFFECT_FRAMES) / EFFECT_FRAMES, 1.0  # A
    x[:, 2], y[:, 2] = 2.0, 1.0  # B
    x[:, 3], y[:, 3] = 25.0, 10.0  # outfield, for the line
    x[:, 4], y[:, 4] = 50.0, 0.0  # the keeper
    tracking = MatchTracking(
        match_id=CI_FIXTURE_MATCH,
        frame0=0,
        x=x,
        y=y,
        detected=np.ones((n, 5), dtype=np.bool_),
        entities=("fb:7", "fb:301", "fb:302", "fb:303", "fb:304"),
        team=(TEAM, OTHER, OTHER, OTHER, OTHER),
        is_goalkeeper=np.array([False, False, False, False, True]),
        period_frames={1: (0, n - 1)},
        attack_sign={(1, TEAM): 1, (1, OTHER): -1},
    )
    return tracking, Run(CI_FIXTURE_MATCH, "r", 7, 100, 1, t_c, t_c + 20, "support", "p")


def test_the_marker_is_fixed_at_t_c_not_one_second_later() -> None:
    tracking, run = _passing_by()
    # at t_c the runner is 1 m from A and 6 m from B; one second on it is 5 m from A, 1.4 m from B
    got = quantities(tracking, run, run.period, run.frame_start, np.array([1.0, 0.0]))
    assert got is not None
    marker_m, _ = got
    assert marker_m == pytest.approx(1.0)  # A moved 1 m with the run
    # the scene discriminates: one second later B is the nearest, and B did not move
    k = run.frame_start + SAMPLE_RATE_HZ
    runner = np.array([tracking.x[k, 0], tracking.y[k, 0]])
    near = [
        float(np.hypot(tracking.x[k, j] - runner[0], tracking.y[k, j] - runner[1])) for j in (1, 2)
    ]
    assert near[1] < near[0]


def test_the_runs_direction_is_read_from_the_tracking_in_the_attack_frame() -> None:
    tracking, run = _passing_by()
    d = run_direction(tracking, run)
    assert d is not None and d.tolist() == pytest.approx([1.0, 0.0])
    standing = Run(CI_FIXTURE_MATCH, "s", 7, 100, 1, 10, 12, "support", "p")  # 1 m in 0.2 s? no
    assert run_direction(tracking, standing) is not None  # 0.5 m/frame * 2 = 1 m: the minimum
    too_short = Run(CI_FIXTURE_MATCH, "s2", 7, 100, 1, 10, 11, "support", "p")
    assert run_direction(tracking, too_short) is None


def test_a_leg_must_lie_inside_its_period() -> None:
    """The three frames of a leg (t - V, t, t + W) must be inside the leg's period: a run
    starting within V frames of its period's start, or a placebo whose window would reach
    the next period, has no quantities even when the frames exist in the array."""
    tracking, run = _passing_by()  # one period, frames 0 to 99
    two_periods = MatchTracking(
        **{
            **{f.name: getattr(tracking, f.name) for f in fields(MatchTracking)},
            "period_frames": {1: (0, 49), 2: (50, 99)},
            "attack_sign": {(1, TEAM): 1, (1, OTHER): -1, (2, TEAM): 1, (2, OTHER): -1},
        }
    )
    d = np.array([1.0, 0.0])
    assert quantities(tracking, run, 1, run.frame_start, d) is not None  # t_c = 40: 35 to 60
    assert quantities(two_periods, run, 1, run.frame_start, d) is None  # 60 is in period 2
    assert quantities(two_periods, run, 2, 60, d) is not None  # 55 to 80, inside period 2
    assert quantities(two_periods, run, 2, 52, d) is None  # 47 is in period 1
    assert quantities(tracking, run, 1, 3, d) is None  # -2 is before the match
    assert quantities(tracking, run, 3, 40, d) is None  # a period the match does not have


# --- placebos against the tracking ----------------------------------------------------------


def test_a_placebo_needs_the_runner_detected_and_the_frames_to_exist() -> None:
    tracking, run = _passing_by()
    assert placebo_supported(tracking, run, 1, 60)
    assert not placebo_supported(tracking, run, 1, 2)  # V frames before t' leave the period
    assert not placebo_supported(tracking, run, 1, 95)  # W frames after t' leave the period
    assert not placebo_supported(tracking, run, 2, 60)  # a period the match does not have
    undetected = tracking.detected.copy()
    undetected[60, 0] = False
    blind = replace(tracking, detected=undetected)
    assert not placebo_supported(blind, run, 1, 60)
    # a frame nobody has between t' and t' + W, one the three frames of the leg never read
    holed_x, holed_y = tracking.x.copy(), tracking.y.copy()
    holed_x[61, :] = np.nan
    holed_y[61, :] = np.nan
    holed = replace(tracking, x=holed_x, y=holed_y)
    assert not placebo_supported(holed, run, 1, 60)
    assert choose_placebo(holed, run, [(1, 60), (1, 70)]) == (1, 70)


def test_the_nearest_supported_instant_wins_and_ties_go_to_the_earlier() -> None:
    tracking, run = _passing_by()  # t_c = 40
    assert choose_placebo(tracking, run, [(1, 80), (1, 55), (1, 70)]) == (1, 55)
    assert choose_placebo(tracking, run, [(1, 50), (1, 30)]) == (1, 30)  # both 10 away
    assert choose_placebo(tracking, run, [(1, 2), (1, 95)]) is None  # neither is supported
    assert choose_placebo(tracking, run, [(1, 8), (1, 60)]) == (1, 60)  # 8 is unsupported


def test_the_second_placebo_is_the_next_by_the_same_rule_with_a_disjoint_window() -> None:
    """The real null's second placebo (review of task 49): the next candidate the rule would
    pick, skipping the first and every instant whose window [t' - V, t' + W] overlaps the
    first's (within V + W = 25 frames in the same period), unsupported instants too."""
    tracking, run = _passing_by()  # t_c = 40, frames 0 to 99
    candidates = [(1, 30), (1, 50), (1, 60), (1, 75)]
    first = choose_placebo(tracking, run, candidates)
    assert first == (1, 30)
    # 50 is nearer than 60 but 20 frames from the first: its window overlaps
    assert choose_second_placebo(tracking, run, candidates, first) == (1, 60)
    assert choose_second_placebo(tracking, run, [(1, 30), (1, 55), (1, 56)], first) == (1, 56)
    assert choose_second_placebo(tracking, run, [(1, 30), (1, 55), (1, 2)], first) is None
    assert choose_second_placebo(tracking, run, [(1, 30)], first) is None
    # the window test is per period: another period's instant never overlaps
    two_periods = MatchTracking(
        **{
            **{f.name: getattr(tracking, f.name) for f in fields(MatchTracking)},
            "period_frames": {1: (0, 49), 2: (50, 99)},
            "attack_sign": {(1, TEAM): 1, (1, OTHER): -1, (2, TEAM): 1, (2, OTHER): -1},
        }
    )
    assert choose_second_placebo(two_periods, run, [(1, 30), (2, 60)], (1, 30)) == (2, 60)
    # a leg the formulas cannot read (the marker gone at t' + W) is skipped like an
    # unsupported one
    holed_x, holed_y = tracking.x.copy(), tracking.y.copy()
    holed_x[80, 2] = holed_y[80, 2] = np.nan  # B, the nearest opponent at 60, at 60 + W
    holed = replace(tracking, x=holed_x, y=holed_y)
    assert placebo_supported(holed, run, 1, 60)
    assert choose_second_placebo(holed, run, candidates, first) == (1, 75)


def test_with_contiguous_periods_a_placebo_hugging_the_period_start_is_refused() -> None:
    """Period 2 starts the frame after period 1 ends, so the frames before its start exist.
    The nearest candidate sits 2 frames into period 2: its t' - V frames are in period 1, and
    `placebo_supported` must refuse it by the period bounds, not by the frames, so the farther
    candidate inside period 2 is picked and the run forms its pair. Without the check on the
    period's start the nearest wins, `_leg` then refuses it, and no pair forms (third review,
    finding 3)."""
    n, start2 = 300, 100
    k = np.arange(n)
    sign = np.where(k < start2, 1.0, -1.0)  # x_m = sign * x_att, per period
    x = np.zeros((n, 5))
    y = np.zeros((n, 5))
    x[:, 0] = sign * (0.5 * (k - 105) - 15.0)  # the runner, along +x_att
    x[:, 1], y[:, 1] = sign * (0.5 * (k - 105) - 16.0), 1.0  # the marker, 1 m behind
    x[:, 2], y[:, 2] = sign * 30.0, 8.0  # the line
    x[:, 3], y[:, 3] = sign * 28.0, -8.0
    x[:, 4], y[:, 4] = sign * 50.0, 0.0  # the keeper
    tracking = MatchTracking(
        match_id=CI_FIXTURE_MATCH,
        frame0=0,
        x=x,
        y=y,
        detected=np.ones((n, 5), dtype=np.bool_),
        entities=("fb:7", "fb:301", "fb:302", "fb:303", "fb:304"),
        team=(TEAM, OTHER, OTHER, OTHER, OTHER),
        is_goalkeeper=np.array([False, False, False, False, True]),
        period_frames={1: (0, start2 - 1), 2: (start2, n - 1)},
        attack_sign={(1, TEAM): 1, (2, TEAM): -1, (1, OTHER): -1, (2, OTHER): 1},
    )
    run = Run(CI_FIXTURE_MATCH, "r", 7, 100, 2, 105, 125, "support", "p")
    hugging, inside = (2, start2 + 2), (2, 160)
    assert tracking.frame_present(start2 + 2 - VELOCITY_FRAMES)  # the frames exist, in period 1
    assert not placebo_supported(tracking, run, *hugging)
    assert placebo_supported(tracking, run, *inside)
    assert choose_placebo(tracking, run, [hugging, inside]) == inside
    instants = {(CI_FIXTURE_MATCH, "r"): [hugging, inside]}
    assert len(pair_effects(tracking, [run], instants)) == 1
    assert count_match(tracking, [run], instants).analysis_set == 1


def test_a_placebo_in_the_other_half_is_turned_by_the_sign_of_its_own_period() -> None:
    """In the venue frame the runner's team attacks +x in period 1 and -x in period 2. The
    run (period 1) has no push; in the placebo scene (period 2) the marker moves 1 m with
    the attack direction and the line drops 1 m, so run minus placebo is -1 and -1. Turned by
    the run's period instead of its own, the placebo scene is rotated 180 degrees: the marker
    reads -1 and the line is taken at the wrong end, and the pair reads +1 and +1 (the
    second review's finding 1)."""
    n, t_c, t_p = 400, 40, 240
    k = np.arange(n)
    sign = np.where(k < 200, 1.0, -1.0)  # x_m = sign * x_att, per period
    x = np.full((n, 5), np.nan)
    y = np.full((n, 5), np.nan)
    runner_x_att = np.where(k < 200, 0.5 * (k - t_c) - 4.0, 0.5 * (k - t_p) - 4.0)
    push = np.where(k < 200, 0.0, np.clip(k - t_p, 0, 20) / 20.0)
    x[:, 0], y[:, 0] = sign * runner_x_att, 0.0
    x[:, 1], y[:, 1] = sign * (-4.0 + push), sign * 1.0  # the marker, 1 m from the runner
    x[:, 2], y[:, 2] = sign * (30.0 + push), sign * 8.0  # the line
    x[:, 3], y[:, 3] = sign * (28.0 + push), sign * -8.0
    x[:, 4], y[:, 4] = sign * 50.0, 0.0  # the keeper
    tracking = MatchTracking(
        match_id=CI_FIXTURE_MATCH,
        frame0=0,
        x=x,
        y=y,
        detected=np.ones((n, 5), dtype=np.bool_),
        entities=("fb:7", "fb:301", "fb:302", "fb:303", "fb:304"),
        team=(TEAM, OTHER, OTHER, OTHER, OTHER),
        is_goalkeeper=np.array([False, False, False, False, True]),
        period_frames={1: (0, 199), 2: (200, 399)},
        attack_sign={(1, TEAM): 1, (2, TEAM): -1, (1, OTHER): -1, (2, OTHER): 1},
    )
    run = Run(CI_FIXTURE_MATCH, "r", 7, 100, 1, t_c, t_c + 20, "support", "p")
    d = np.array([1.0, 0.0])
    assert placebo_supported(tracking, run, 2, t_p)
    assert choose_placebo(tracking, run, [(2, t_p)]) == (2, t_p)
    assert quantities(tracking, run, 1, t_c, d) == pytest.approx((0.0, 0.0))
    assert quantities(tracking, run, 2, t_p, d) == pytest.approx((1.0, 1.0))
    (pair,) = pair_effects(tracking, [run], {(CI_FIXTURE_MATCH, "r"): [(2, t_p)]})
    assert pair.marker_m == pytest.approx(-1.0)
    assert pair.line_m == pytest.approx(-1.0)


def test_window_bounds_clip_to_the_period() -> None:
    tracking, _ = _passing_by()
    near_start = Run(CI_FIXTURE_MATCH, "a", 7, 100, 1, 3, 10, "support", "p")
    assert window_bounds(tracking, near_start) == (0, 40, True)
    inside = Run(CI_FIXTURE_MATCH, "b", 7, 100, 1, 20, 30, "support", "p")
    assert window_bounds(tracking, inside) == (10, 60, False)


# --- the analysis set is what the estimator forms -------------------------------------------

SABOTAGE = (
    "marker_before",
    "marker_after",
    "lone_outfield_before",
    "lone_outfield_at",
    "lone_outfield_after",
)


def _sabotaged_match(seed: int) -> tuple[MatchTracking, list[Run], Instants, dict[str, int]]:
    """A random two-period match whose legs are sabotaged on purpose (the third review's
    probe): the opponent nearest to the runner loses its position at t - V or at t + W, or a
    single outfield opponent is left at one of the three frames of a leg; some runners stand
    still; some candidates hug a period edge; about 10 in-period frames are missing for every entity
    (the fourth review's mutant M3); the half-time gap is 0 or 10 frames. Returns
    how often each kind of sabotage was applied."""
    rng = np.random.default_rng(seed)
    n, n_entities = 520, 9  # entities 0 to 2 the runner's team, 3 to 7 outfield, 8 the keeper
    x = rng.uniform(-30, 30, n_entities) + np.cumsum(rng.normal(0, 0.15, (n, n_entities)), 0)
    y = rng.uniform(-20, 20, n_entities) + np.cumsum(rng.normal(0, 0.15, (n, n_entities)), 0)
    gap = int(rng.choice([0, 0, 10]))
    cut = 260
    x[cut : cut + gap] = np.nan
    y[cut : cut + gap] = np.nan
    bounds = {1: (0, cut - 1), 2: (cut + gap, n - 1)}
    x[cut + gap :] *= -1  # the teams change ends
    y[cut + gap :] *= -1
    k = np.arange(n)
    x[:, 0] += 0.35 * (k % 60) * np.where(k < cut + gap, 1.0, -1.0)  # the runner moves
    runs: list[Run] = []
    instants: Instants = {}
    legs: list[tuple[int, int]] = []
    for r in range(70):
        period = int(rng.integers(1, 3))
        a, b = bounds[period]
        start = int(rng.integers(a, b - 30))
        end = start + int(rng.integers(6, 25))
        if rng.random() < 0.12:  # a runner who stands still has no direction
            x[start : end + 1, 0] = x[start, 0]
            y[start : end + 1, 0] = y[start, 0]
        run = Run(CI_FIXTURE_MATCH, f"r{r}", 7, 100, period, start, end, "support", f"p{r}")
        runs.append(run)
        candidates: list[tuple[int, int]] = []
        for _ in range(int(rng.integers(1, 5))):
            q = int(rng.integers(1, 3))
            qa, qb = bounds[q]
            last = qb - EFFECT_FRAMES  # the last instant whose leg fits in the period
            edges = [qa + 2, qa + VELOCITY_FRAMES, qa + 7, last, last - 1, qb - 3]
            if rng.random() < 0.4:
                candidates.append((q, int(rng.choice(edges))))
            else:
                candidates.append((q, int(rng.integers(qa, qb + 1))))
        instants[(CI_FIXTURE_MATCH, run.event_id)] = sorted(candidates, key=lambda c: c[1])
        legs += [(run.period, run.frame_start), *candidates]
    applied = dict.fromkeys(SABOTAGE, 0)
    for _, instant in legs:
        before, after = instant - VELOCITY_FRAMES, instant + EFFECT_FRAMES
        if rng.random() >= 0.10 or before < 0 or after >= n:
            continue
        kind = str(rng.choice(SABOTAGE))
        applied[kind] += 1
        if kind.startswith("marker"):
            gaps = np.hypot(x[instant, 3:] - x[instant, 0], y[instant, 3:] - y[instant, 0])
            marker = 3 + int(np.argmin(np.where(np.isfinite(gaps), gaps, np.inf)))
            frame = before if kind == "marker_before" else after
            x[frame, marker] = y[frame, marker] = np.nan
        else:
            frame = {"before": before, "at": instant, "after": after}[kind.rsplit("_", 1)[1]]
            keep = int(rng.choice([3, 4]))
            for e in range(3, n_entities - 1):
                if e != keep:
                    x[frame, e] = y[frame, e] = np.nan
    for period in rng.integers(1, 3, 10):  # a frame missing for every entity, inside a period
        a, b = bounds[int(period)]
        gone = int(rng.integers(a, b + 1))
        x[gone] = y[gone] = np.nan
    detected = np.isfinite(x) & (rng.random((n, n_entities)) < 0.998)
    tracking = MatchTracking(
        match_id=CI_FIXTURE_MATCH,
        frame0=0,
        x=x,
        y=y,
        detected=detected,
        entities=tuple(f"fb:{7 + i}" for i in range(n_entities)),
        team=(TEAM,) * 3 + (OTHER,) * 6,
        is_goalkeeper=np.array([False] * 8 + [True]),
        period_frames=bounds,
        attack_sign={(1, TEAM): 1, (2, TEAM): -1, (1, OTHER): -1, (2, OTHER): 1},
    )
    return tracking, runs, instants, applied


def test_the_analysis_set_counts_exactly_the_pairs_the_estimator_forms() -> None:
    """`count_match` must drop a run for the reasons `pair_effects` does and for no other,
    on matches whose legs are sabotaged on purpose (third review, finding 2). Each condition
    of `count_match` (placebo leg, run leg, direction) and each rule of `_leg` (the marker's
    position at t + W, two outfield opponents at each frame) makes a run count that forms no
    pair when it is dropped, and a window with a frame missing for every entity makes a
    run count as clean that is not, so the mutants of those conditions fail here."""
    applied = dict.fromkeys(SABOTAGE, 0)
    pairs = clean = standing = 0
    for seed in range(20):
        tracking, runs, instants, kinds = _sabotaged_match(seed)
        for kind, times in kinds.items():
            applied[kind] += times
        counts = count_match(tracking, runs, instants)
        formed = pair_effects(tracking, runs, instants)
        assert counts.analysis_set == len(formed), seed
        pairs += len(formed)
        clean += counts.clean
        standing += sum(run_direction(tracking, run) is None for run in runs)
    assert all(times > 0 for times in applied.values()), applied
    assert standing > 0
    assert 0 < pairs < clean  # the sabotage bites: clean runs that form no pair


# --- the guard: values leave only through readable matches ---------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def design_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repository whose HEAD holds the protocol in stage design, so the outcome
    does not depend on this repository's stage (task 50 freezes it)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "ci@example.invalid")
    _git(repo, "config", "user.name", "ci")
    _git(repo, "config", "commit.gpgsign", "false")
    protocol = repo / data.PROTOCOL_IN_REPO
    protocol.parent.mkdir(parents=True)
    committed = read_protocol(PROTOCOL)  # as tasks 47 and 49 wrote it, whatever stage it is in now
    design = seal(
        {
            **committed,
            "stage": STAGE_DESIGN,
            "history": [h for h in committed["history"] if h["stage"] == STAGE_DESIGN],
        }
    )
    protocol.write_text(render(design), encoding="utf-8", newline="\n")
    # a code tree at the probe's path, so `code_tree_sha` has a tree to name and a test can
    # leave it uncommitted
    code = repo / data.CODE_IN_REPO / "probe.py"
    code.parent.mkdir(parents=True)
    code.write_text("# the code tree of the throwaway repository\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "design")
    monkeypatch.setattr(data, "repo_root", lambda: repo)
    return repo


def test_pair_effects_refuses_a_held_out_match_and_opens_a_calibration_one(
    design_repo: Path,
) -> None:
    with pytest.raises(HeldOutLocked):
        _synthetic(3, 1.0, 0.0, seed=1, match_id=HELD_OUT_MATCH)  # refused as it is built
    ok, runs, instants = _synthetic(3, 1.0, 0.0, seed=1, match_id=CI_FIXTURE_MATCH)
    assert len(pair_effects(ok, runs, instants)) == 3
    with pytest.raises(ValueError, match="neither half"):
        _synthetic(3, 1.0, 0.0, seed=1, match_id=1)


# Every public function or class of every module of `tracklab.runs`, by what it does with a
# held-out id while the committed protocol is in design. A new public name must be added
# here, and the test below calls each of the first two groups with the held-out match.
REFUSES_A_HELD_OUT_MATCH = {
    "windows.MatchTracking",
    "windows.load_tracking",
    "windows.run_direction",  # takes a MatchTracking, of which the held-out match has none
    "windows.run_length",  # the same
    "windows.line_height_at",  # the same
    "windows.quantities",  # the same
    "windows.run_class",  # the same (task 50)
    "windows.leg_marker",  # the same (task 50)
    "windows.leg_marker_detected",  # the same (task 50)
    "windows.pair_effects",  # the same
    "probe.probe_match",  # the same
    "probe.load_provider_lines",  # the same: a provider measure, read only to contrast
    "probe.cadence",  # the same
    "candidates.effect_match",  # the same (task 50)
    "data.require_readable",
    "data.load_half",
    "data.assert_held_out_open",
}
TAKES_A_MATCH_TRACKING = {
    "windows.run_direction",
    "windows.run_length",
    "windows.line_height_at",
    "windows.quantities",
    "windows.run_class",
    "windows.leg_marker",
    "windows.leg_marker_detected",
    "windows.pair_effects",
    "probe.probe_match",
    "probe.load_provider_lines",
    "probe.cadence",
    "candidates.effect_match",
}
COUNTS_ONLY = {
    "windows.load_runs",
    "windows.window_bounds",
    "windows.placebo_supported",
    "windows.choose_placebo",
    "windows.choose_second_placebo",
    "windows.count_match",
    "windows.count_tracking",
    "data.counting_match_ids",
    "data.match_halves",
    "data.committed_split",
    "coverage.coverage_rows",
    "coverage.run_runs_coverage",
    "placebo.placebo_counts",
    "placebo.placebo_instants",
    "probe.load_player_possessions",
}
# No match id to pass and no tracking but a `MatchTracking`: the ids are
# `load_half("calibration")` (test_runs_probe greps the module for it) and the other half is
# counted through `count_tracking`.
CALIBRATION_ONLY = {
    "probe.build_probe",
    "probe.run_runs_probe",
    "candidates.build_effect",
    "candidates.run_runs_effect",
}
# No tracking in, none out: the protocol and git (`data`), arithmetic on what the caller
# passes (`effect`, the null and the power of `probe`), the split and the events
# (`protocol`, `placebo`), or no input at all.
READS_NO_FRAMES = {
    "windows.whole_frames",
    "windows.Run",
    "windows.PairEffect",
    "windows.MatchCounts",
    "windows.components",
    "windows.unit_labels",
    "windows.units_by_subtype",
    "windows.pair_unit_key",
    "data.HeldOutLocked",
    "data.committed_protocol",
    "data.head_stage",
    "data.head_commit",
    "data.code_tree_sha",
    "data.dirty_paths",
    "data.dirty_code_paths",
    "data.repo_root",
    "coverage.render",
    "coverage.has_frames",
    "placebo.PlaceboCount",
    "placebo.total",
    "placebo.as_rows",
    "probe.ProbeInputError",
    "probe.Cadence",
    "probe.cadence_lag",
    "probe.pooled_autocorrelation",
    "probe.ProviderLines",
    "probe.MatchProbe",
    "probe.sign_flips",
    "probe.unit_sums",
    "probe.permutation_p",
    "probe.same_sign_matches",
    "probe.BarVerdict",
    "probe.bar_verdict",
    "probe.NullRates",
    "probe.null_fire_rates",
    "probe.DesignEffect",
    "probe.design_effect",
    "probe.normal_two_sided_tail",
    "probe.bar_pass_probability",
    "probe.Power",
    "probe.mde80",
    "probe.probable_subtypes",
    "probe.probe_path",
    "probe.consistency_problems",
    "probe.with_foreign_sections",
    "probe.protocol_record",
    "probe.protocol_problems",
    # task 50: the arithmetic of the effect's tables and verdict, the files and git
    "candidates.EffectInputError",
    "candidates.MatchEffects",
    "candidates.run_leg_overlap_keys",
    "candidates.subtype_verdict",
    "candidates.line_testability",
    "candidates.section_sha256",
    "candidates.probe_inputs",
    "candidates.calibration_path",
    "candidates.consistency_problems",
    "candidates.run_runs_freeze",
}


def _public_names(module: ModuleType) -> set[str]:
    short = module.__name__.rsplit(".", 1)[-1]
    return {
        f"{short}.{n}"
        for n, v in vars(module).items()
        if not n.startswith("_")
        and (inspect.isfunction(v) or inspect.isclass(v))
        and v.__module__ == module.__name__
    }


# Taken at import, before any fixture monkeypatches `data.repo_root`: every module of the
# package, so a new module's public names must be classified too.
PUBLIC = set[str]().union(
    *(
        _public_names(importlib.import_module(f"tracklab.runs.{m.name}"))
        for m in pkgutil.iter_modules([str(Path(windows.__file__).parent)])
    )
)
READS_NO_FRAMES |= _public_names(effect) | _public_names(protocol)


def _values_inside(obj: object, path: str = "value") -> list[str]:
    """Where `obj` holds an array or a float, recursively through dataclasses, mappings and
    sequences: what a counting function returns must hold none. The two detection fractions
    of a `MatchCounts` are the exception, and they must be fractions."""
    if isinstance(obj, np.ndarray | np.floating | float):
        return [path]
    if isinstance(obj, MatchCounts):
        return [
            f"{path}.{f.name}"
            for f in fields(obj)
            if not (
                isinstance(getattr(obj, f.name), int)
                or (f.name == "by_subtype" and all(isinstance(n, int) for n in obj.by_subtype))
                or (
                    f.name == "analysis_units"
                    and all(isinstance(n, int) for sizes in obj.analysis_units for n in sizes)
                )
                or (f.name.startswith("opp_detected_") and 0.0 <= getattr(obj, f.name) <= 1.0)
            )
        ]
    if is_dataclass(obj) and not isinstance(obj, type):
        return [
            found
            for f in fields(obj)
            for found in _values_inside(getattr(obj, f.name), f"{path}.{f.name}")
        ]
    if isinstance(obj, Mapping):
        return [
            found for key, item in obj.items() for found in _values_inside(item, f"{path}[{key!r}]")
        ]
    if isinstance(obj, list | tuple | set | frozenset):
        return [
            found for i, item in enumerate(obj) for found in _values_inside(item, f"{path}[{i}]")
        ]
    return []


def test_the_walk_sees_an_array_or_a_float_wherever_it_hides() -> None:
    held, runs, instants = _synthetic_raw(2, 1.0, 0.0, seed=3, match_id=HELD_OUT_MATCH)
    assert _values_inside(held) == [
        "value.x",
        "value.y",
        "value.detected",
        "value.is_goalkeeper",
        "value.ball_x",
        "value.ball_y",
    ]
    assert _values_inside({"a": [(1, np.float64(2.0))]}) == ["value['a'][0][1]"]
    assert _values_inside([runs[0], 1.5]) == ["value[1]"]
    assert _values_inside(
        windows.PairEffect(1, "r", None, "s", 7, 20, 1, 60, 0.0, 0.0, 0.0, 0.0)
    ) == [
        "value.marker_m",
        "value.line_m",
        "value.placebo_marker_m",
        "value.placebo_line_m",
    ]
    counts = count_match(held, runs, instants)
    assert _values_inside(counts) == []
    assert _values_inside(replace(counts, opp_detected_p50=7.0)) == ["value.opp_detected_p50"]
    assert _values_inside((runs, instants, {"ids": [1, 2]}, "text", None, True)) == []


def test_every_public_name_of_runs_refuses_a_held_out_match_or_returns_counts_only(
    design_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavioural, not lexical: with the committed protocol in design, every public name of
    every module of `tracklab.runs` is classified, and each one of the first two groups is
    called with the held-out match. No tracking of it can be built, loaded or relabelled,
    and the three functions that return values of a tracking take only what those three
    doors build; what the counting names return is walked, and it holds no array and no
    float but the detection fractions. The frames are read in one private function with
    those two callers, `load_tracking` and `count_tracking`."""
    groups = (REFUSES_A_HELD_OUT_MATCH, COUNTS_ONLY, CALIBRATION_ONLY, READS_NO_FRAMES)
    assert PUBLIC == set().union(*groups)
    assert sum(len(g) for g in groups) == len(PUBLIC)  # pairwise disjoint
    assert TAKES_A_MATCH_TRACKING <= REFUSES_A_HELD_OUT_MATCH
    held, runs, instants = _synthetic_raw(3, 1.0, 0.0, seed=2, match_id=HELD_OUT_MATCH)
    root = tmp_path / "data"
    _write_warehouse(root, held, runs)
    run = runs[0]
    cal, cal_runs, cal_instants = _synthetic(3, 1.0, 0.0, seed=2, match_id=CI_FIXTURE_MATCH)
    cal_root = tmp_path / "calibration"  # its own root: a warehouse holds one dim_period
    _write_warehouse(cal_root, cal, cal_runs)

    # refusals: no MatchTracking of the held-out match comes into being
    with pytest.raises(HeldOutLocked):
        _guarded(held)  # built by hand from the arrays
    with pytest.raises(HeldOutLocked):
        load_tracking(tmp_path / "nowhere", HELD_OUT_MATCH)  # refused before any read
    with pytest.raises(HeldOutLocked):
        load_tracking(root, HELD_OUT_MATCH)
    with pytest.raises(HeldOutLocked):
        replace(cal, match_id=HELD_OUT_MATCH)  # a calibration one relabelled
    with pytest.raises(HeldOutLocked):
        require_readable(HELD_OUT_MATCH)
    with pytest.raises(HeldOutLocked):
        load_half("held_out")
    with pytest.raises(HeldOutLocked):
        data.assert_held_out_open()
    for qualified in sorted(TAKES_A_MATCH_TRACKING):
        module_name, name = qualified.split(".")
        function = getattr(importlib.import_module(f"tracklab.runs.{module_name}"), name)
        parameter = next(iter(inspect.signature(function).parameters.values()))
        assert parameter.annotation == "MatchTracking", qualified
    assert {f.name for f in fields(MatchTracking)} == {f.name for f in fields(held)}
    pairs = pair_effects(load_tracking(cal_root, CI_FIXTURE_MATCH), cal_runs, cal_instants)
    assert len(pairs) == 3

    # counts only: each name called with the held-out match, what comes back walked
    exercised: set[str] = set()

    def counted(name: str, value: object) -> object:
        assert name in COUNTS_ONLY, name
        assert _values_inside(value) == [], name
        exercised.add(name)
        return value

    assert counted("windows.load_runs", load_runs(root, HELD_OUT_MATCH)) == runs
    assert {f.name for f in fields(Run)} == {
        "match_id",
        "event_id",
        "player_id",
        "team_id",
        "period",
        "frame_start",
        "frame_end",
        "subtype",
        "possession_id",
    }  # the provider's keys and labels, no tracking
    lo, hi, clipped = window_bounds(held, run)
    counted("windows.window_bounds", (lo, hi, clipped))
    assert isinstance(lo, int) and isinstance(hi, int) and isinstance(clipped, bool)
    t_placebo = _placebo_instant(run, instants)
    assert counted("windows.placebo_supported", placebo_supported(held, run, *t_placebo)) is True
    candidates = instants[(HELD_OUT_MATCH, run.event_id)]
    assert counted("windows.choose_placebo", choose_placebo(held, run, candidates)) == t_placebo
    # the next candidate with a disjoint window: the farther supported instant of the scene
    assert counted(
        "windows.choose_second_placebo", choose_second_placebo(held, run, candidates, t_placebo)
    ) == (t_placebo[0], t_placebo[1] + 30)
    counts = counted("windows.count_match", count_match(held, runs, instants))
    assert isinstance(counts, MatchCounts)
    assert counts.runs == counts.clean == counts.placebo_found == counts.analysis_set == 3
    from_disk = counted("windows.count_tracking", count_tracking(root, HELD_OUT_MATCH))
    assert from_disk == count_match(held, runs, {})
    assert HELD_OUT_MATCH in counted("data.counting_match_ids", counting_match_ids())
    assert counted("data.match_halves", match_halves())[HELD_OUT_MATCH] == "held_out"
    assert HELD_OUT_MATCH in counted("data.committed_split", data.committed_split())[1]
    (row,) = counted("coverage.coverage_rows", coverage_rows(root, [HELD_OUT_MATCH]))
    assert len(row) == len(HEADER) and row[HEADER.index("half")] == "held_out"
    _assert_count_row(dict(zip(HEADER, row, strict=True)))
    reports = tmp_path / "reports"
    assert counted("coverage.run_runs_coverage", run_runs_coverage(root, reports)) == 1
    assert not (reports / COVERAGE_NAME).exists()  # one match of 20: writes nothing
    assert "1 of the 20 matches" in capsys.readouterr().out
    (placebos,) = counted("placebo.placebo_counts", placebo.placebo_counts(root, [HELD_OUT_MATCH]))
    assert placebos.match_id == HELD_OUT_MATCH and placebos.runs == 3
    assert (
        counted(
            "placebo.placebo_instants",
            placebo.placebo_instants(root, [HELD_OUT_MATCH], PLACEBO_RULE),
        )
        == {}
    )
    assert (
        counted(
            "probe.load_player_possessions", probe.load_player_possessions(root, HELD_OUT_MATCH)
        )
        == []
    )
    assert exercised == COUNTS_ONLY

    # calibration only: no id to pass; on a root that holds the held-out match alone, the
    # probe asks for a calibration match's frames, which are not there, and writes nothing
    # (test_runs_probe greps its ids)
    with pytest.raises((ValueError, duckdb.IOException)):
        probe.build_probe(root, head="0" * 40, code_tree="0" * 40)
    assert probe.run_runs_probe(root, reports) == 1
    assert not (reports / probe.PROBE_NAME).exists()
    # the effect answers to a probe section: without one it refuses before any frame
    with pytest.raises(effect_probe.EffectInputError):
        effect_probe.build_effect(root, {}, "0" * 40, "0" * 40)
    assert effect_probe.run_runs_effect(root, reports) == 1
    assert not (reports / probe.PROBE_NAME).exists()

    # the rest reads no frames: the protocol and git, here; arithmetic and events elsewhere
    assert data.head_stage() == STAGE_DESIGN
    assert data.committed_protocol()["stage"] == STAGE_DESIGN
    assert data.dirty_paths(design_repo) == []
    assert data.repo_root() == design_repo
    src = PIPELINE / "src" / "tracklab" / "runs"
    for path in sorted(src.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if path.name == "windows.py":
            assert text.count("_read_tracking(") == 3  # the definition and its two callers
            assert text.count('"sport=football"') == 1
        else:
            assert "_read_tracking" not in text, path.name
            # coverage.py tests whether the folder exists and reads nothing from it
            assert ('"sport=football"' in text) == (path.name == "coverage.py"), path.name


# --- the coverage file: pinned header, every column a count ---------------------------------

COLUMN_TYPES: dict[str, type] = {
    "match_id": int,
    "half": str,
    "runs": int,
    "runs_behind": int,
    "runs_coming_short": int,
    "runs_cross_receiver": int,
    "runs_dropping_off": int,
    "runs_overlap": int,
    "runs_pulling_half_space": int,
    "runs_pulling_wide": int,
    "runs_run_ahead_of_the_ball": int,
    "runs_support": int,
    "runs_underlap": int,
    "complete_windows": int,
    "clipped_windows": int,
    "runner_absent": int,
    "runner_detected": int,
    "clean": int,
    "opp_detected_p50": float,
    "opp_detected_p10": float,
    "placebo_found": int,
    "analysis_set": int,
}


def _assert_count_row(row: dict[str, str]) -> None:
    for name, kind in COLUMN_TYPES.items():
        cell = row[name]
        if kind is str:
            assert cell in ("calibration", "held_out"), name
        elif kind is int:
            assert re.fullmatch(r"\d+", cell), (name, cell)
        else:  # a detection fraction, four decimals, in [0, 1]
            assert re.fullmatch(r"[01]\.\d{4}", cell) and 0.0 <= float(cell) <= 1.0, (name, cell)


def test_the_coverage_header_is_pinned_and_every_column_is_a_count() -> None:
    """A literal, not a blacklist: a column that is not an integer, a half or a detection
    fraction cannot enter the file without changing this test."""
    assert HEADER == tuple(COLUMN_TYPES)
    assert tuple(COLUMN_TYPES)[3:13] == tuple(f"runs_{s}" for s in SUBTYPES)
    for f in fields(MatchCounts):
        assert f.type in ("int", "float", "tuple[int, ...]", "tuple[tuple[int, ...], ...]"), f.name
    for row in _committed_rows().values():
        _assert_count_row(row)


def test_counting_covers_both_halves() -> None:
    ids = counting_match_ids()
    halves = match_halves()
    assert ids == sorted(halves)
    assert len(ids) == 20
    assert sorted(m for m, h in halves.items() if h == "calibration") == load_half("calibration")


# --- real rows: the fixture match against the versioned counts -------------------------------


def _committed_rows() -> dict[str, dict[str, str]]:
    with (REPORTS / COVERAGE_NAME).open(encoding="utf-8", newline="") as handle:
        return {r["match_id"]: r for r in csv.DictReader(handle)}


def _count_fixture_match(root: Path | None = None) -> tuple[MatchCounts, int]:
    root = root or data_root()
    tracking = load_tracking(root, CI_FIXTURE_MATCH)
    runs = load_runs(root, CI_FIXTURE_MATCH)
    instants = placebo.placebo_instants(root, [CI_FIXTURE_MATCH], PLACEBO_RULE)
    counts = count_match(tracking, runs, instants)
    # the analysis set is what the estimator forms (held in memory, never printed)
    return counts, len(pair_effects(tracking, runs, instants))


needs_the_fixture_match = pytest.mark.skipif(
    not (data_root() / "silver" / "frames" / "sport=football").is_dir()
    or not any((data_root() / "bronze" / "football" / "dynamic_events").glob("*.parquet")),
    reason="no football frames and events under the data root (a clone without data)",
)

# The fixture silver is not versioned: the `ci` workflow builds it with `tracklab build`
# before the tests, `full-build` and a clean clone with the real data root do not have it.
needs_the_fixture_silver = pytest.mark.skipif(
    not (
        FIXTURES / "silver" / "frames" / "sport=football" / f"native_match_id={CI_FIXTURE_MATCH}"
    ).is_dir()
    or not (FIXTURES / "silver" / "dim_match").is_dir(),
    reason="the fixture silver is not built (only `tracklab build` on the fixtures writes it)",
)


def _warehouse_holds_every_match() -> bool:
    return (REPORTS / COVERAGE_NAME).is_file() and all(
        coverage.has_frames(data_root(), int(m)) for m in _committed_rows()
    )


needs_the_whole_warehouse = pytest.mark.skipif(
    not _warehouse_holds_every_match(),
    reason="the frames of the 20 matches are not all under the data root",
)


@needs_the_fixture_match
def test_the_counts_of_the_ci_fixture_match_are_consistent() -> None:
    """On the CI fixtures this is a slice of the match (one possession), on the real warehouse
    the whole match: the invariants hold on both, the versioned row only on the second."""
    counts, formed = _count_fixture_match()
    con = duckdb.connect()
    events = (data_root() / "bronze" / "football" / "dynamic_events" / "*.parquet").as_posix()
    (n_runs,) = con.execute(
        "SELECT count(*) FROM read_parquet($g) WHERE match_id = $m AND event_type = 'off_ball_run'",
        {"g": events, "m": CI_FIXTURE_MATCH},
    ).fetchone() or (None,)
    assert counts.runs == n_runs > 0
    assert sum(counts.by_subtype) == counts.runs
    assert counts.clean <= counts.complete_windows <= counts.runs
    assert counts.clean <= counts.runner_detected <= counts.runs - counts.runner_absent
    assert counts.analysis_set <= counts.clean
    assert counts.analysis_set <= counts.placebo_found
    assert formed == counts.analysis_set
    assert 0.0 <= counts.opp_detected_p10 <= counts.opp_detected_p50 <= 1.0


@needs_the_fixture_match
def test_the_fixture_match_reproduces_its_versioned_row_when_the_match_is_whole() -> None:
    counts, formed = _count_fixture_match()
    row = _committed_rows()[str(CI_FIXTURE_MATCH)]
    if counts.runs != int(row["runs"]):
        pytest.skip(f"the warehouse at hand holds a slice of the match ({counts.runs} runs)")
    for subtype, n in zip(SUBTYPES, counts.by_subtype, strict=True):
        assert n == int(row[f"runs_{subtype}"])
    for name in (
        "complete_windows",
        "clipped_windows",
        "runner_absent",
        "runner_detected",
        "clean",
        "placebo_found",
        "analysis_set",
    ):
        assert getattr(counts, name) == int(row[name]), name
    assert f"{counts.opp_detected_p50:.4f}" == row["opp_detected_p50"]
    assert f"{counts.opp_detected_p10:.4f}" == row["opp_detected_p10"]
    assert formed == int(row["analysis_set"])


def test_the_versioned_counts_are_the_inventorys() -> None:
    rows = _committed_rows()
    assert sorted(int(m) for m in rows) == counting_match_ids()
    assert {int(m): r["half"] for m, r in rows.items()} == match_halves()

    def total(column: str) -> int:
        return sum(int(r[column]) for r in rows.values())

    assert total("runs") == 9898
    assert total("complete_windows") == 9774
    assert total("runner_detected") == 8262
    assert total("clean") == 8198
    assert {m: r["runner_absent"] for m, r in rows.items() if r["runner_absent"] != "0"} == {
        "1953632": "6"
    }
    for r in rows.values():
        assert int(r["clean"]) <= int(r["complete_windows"]) <= int(r["runs"])
        assert sum(int(r[f"runs_{s}"]) for s in SUBTYPES) == int(r["runs"])


@needs_the_whole_warehouse
def test_the_versioned_coverage_is_recounted_from_the_whole_warehouse(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The 20 rows, recounted from the real frames through `count_tracking`, are the
    versioned ones: what `runs coverage --check` says in the V gate, as a test."""
    assert run_runs_coverage(data_root(), REPORTS, check=True) == 0
    assert "warehouse=FULL 20/20 rows recounted and equal" in capsys.readouterr().out


# --- the command ----------------------------------------------------------------------------


def _reports_copy(tmp_path: Path) -> Path:
    """The coverage file alone: the split comes from the protocol committed in HEAD."""
    reports = tmp_path / "reports"
    reports.mkdir()
    shutil.copy(REPORTS / COVERAGE_NAME, reports / COVERAGE_NAME)
    return reports


def test_coverage_refuses_to_write_from_a_partial_warehouse(tmp_path: Path) -> None:
    reports = _reports_copy(tmp_path)
    before = (reports / COVERAGE_NAME).read_bytes()
    assert run_runs_coverage(FIXTURES, reports) == 1
    assert (reports / COVERAGE_NAME).read_bytes() == before


@needs_the_fixture_silver
def test_coverage_check_on_a_slice_verifies_the_header_and_the_match_list(
    tmp_path: Path,
) -> None:
    reports = _reports_copy(tmp_path)
    if len(load_runs(FIXTURES, CI_FIXTURE_MATCH)) == int(
        _committed_rows()[str(CI_FIXTURE_MATCH)]["runs"]
    ):
        pytest.skip("the fixtures hold the whole match: the next test covers this")
    assert run_runs_coverage(FIXTURES, reports, check=True) == 0
    text = (reports / COVERAGE_NAME).read_text(encoding="utf-8")
    (reports / COVERAGE_NAME).write_text(text.replace("match_id,", "match,", 1), encoding="utf-8")
    assert run_runs_coverage(FIXTURES, reports, check=True) == 1


@needs_the_fixture_silver
def test_coverage_check_recounts_a_whole_match_and_sees_a_hand_edit(tmp_path: Path) -> None:
    """The fixtures hold a slice of the match, so the file is given the slice's own counts: the
    whole-match path of `--check` is then the one exercised."""
    reports = _reports_copy(tmp_path)
    counts, _ = _count_fixture_match(FIXTURES)
    text = (reports / COVERAGE_NAME).read_text(encoding="utf-8")
    first = next(line for line in text.splitlines() if line.startswith(str(CI_FIXTURE_MATCH)))
    honest = ",".join(_row(counts, "calibration"))
    (reports / COVERAGE_NAME).write_text(text.replace(first, honest), encoding="utf-8")
    assert run_runs_coverage(FIXTURES, reports, check=True) == 0
    cells = honest.split(",")
    cells[HEADER.index("clean")] = str(int(cells[HEADER.index("clean")]) + 1)
    (reports / COVERAGE_NAME).write_text(text.replace(first, ",".join(cells)), encoding="utf-8")
    assert run_runs_coverage(FIXTURES, reports, check=True) == 1


def test_no_path_goes_through_the_possession_flipped_view() -> None:
    """`frames_attacking` turns each frame by the team in possession and drops frames no
    possession claims; the instrument turns every frame by the runner's team
    (`dim_team_period.attack_sign` on `frames`), so a possession change inside a window does
    not flip the geometry and no frame goes missing."""
    for name in ("windows.py", "effect.py", "coverage.py"):
        source = (PIPELINE / "src" / "tracklab" / "runs" / name).read_text(encoding="utf-8")
        assert "frames_attacking" not in source, name
    windows_source = (PIPELINE / "src" / "tracklab" / "runs" / "windows.py").read_text(
        encoding="utf-8"
    )
    assert "silver" in windows_source
    assert "dim_team_period" in windows_source
    assert '"frames"' in windows_source
    # and the protocol says exactly that (review of tasks 47-48, finding 2)
    coordinates = read_protocol(PROTOCOL)["design"]["frames"]["coordinates"]
    assert coordinates.startswith("silver frames (x_m, y_m")
    assert "dim_team_period.attack_sign" in coordinates
    assert "never the frames_attacking view" in coordinates
