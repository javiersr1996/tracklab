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
and the two-period test; the placebo leg's sign flipped fails the planted-effect tests.
"""

from __future__ import annotations

import csv
import inspect
import math
import re
import shutil
import subprocess
from dataclasses import fields
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from tracklab.paths import data_root
from tracklab.runs import coverage, data, effect, placebo, windows
from tracklab.runs.coverage import COVERAGE_NAME, HEADER, _row, coverage_rows, run_runs_coverage
from tracklab.runs.data import (
    CountingHandle,
    CountingOnly,
    HeldOutLocked,
    counting_handle,
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
    count_match,
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

BLOCK = 80
ANCHOR = 20  # offset of t_c inside a scene
RUN_FRAMES = 20
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
    rng: np.random.Generator, direction_angle: float, marker_push: float, line_push: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One scene of BLOCK frames in the attack frame: runner (BLOCK, 2), opponents
    (BLOCK, 12, 2). Opponent 0 is the marker, 1 and 2 the two deepest outfield players, 3 to 10
    the rest of the line-up, 11 the goalkeeper. `marker_push` and `line_push` are the whole
    residual of the scene (planted effect plus baseline)."""
    k = np.arange(BLOCK) - ANCHOR  # frames relative to t_c
    d = np.array([math.cos(direction_angle), math.sin(direction_angle)])
    start = np.array([rng.uniform(-22.0, -14.0), rng.uniform(-3.0, 3.0)])
    run_progress = np.clip(k, 0, RUN_FRAMES) * 0.5  # 5 m/s: 10 m over the run
    runner = start + run_progress[:, None] * d

    opponents = np.zeros((BLOCK, 12, 2))
    ramp = np.clip(k, 0, EFFECT_FRAMES) / EFFECT_FRAMES
    # the marker: 2 m from the runner at t_c, its own velocity and acceleration, plus the push
    around = rng.uniform(0, 2 * math.pi)
    at_anchor = start + 2.0 * np.array([math.cos(around), math.sin(around)])
    v0 = rng.normal(0.0, 1.0, 2) / SAMPLE_RATE_HZ
    dv = rng.normal(0.0, 0.25, 2) / SAMPLE_RATE_HZ
    own = at_anchor + np.outer(k, v0) + np.outer(np.clip(k, 0, None), dv)
    opponents[:, 0] = own + (marker_push * ramp)[:, None] * d
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
    return runner, opponents, d


Instants = dict[tuple[int, str], list[tuple[int, int]]]


def _synthetic(
    n_runs: int,
    marker_push: float,
    line_push: float,
    seed: int,
    match_id: int = CI_FIXTURE_MATCH,
    *,
    counting_only: bool = False,
) -> tuple[MatchTracking, list[Run], Instants]:
    """`n_runs` runs, each with one placebo scene, in blocks of BLOCK frames: blocks 0 to
    n - 1 hold the run scenes, n to 2n - 1 the placebo scenes. Period 1 ends after the first
    half of the run scenes, so those runs find their placebo in the other half of the match
    (attack sign -1 against +1) and the rest in their own. Both scenes carry the baseline
    drift; the run scene carries the planted effect on top. Every run gets four candidates:
    a nearer instant where the runner is undetected, the placebo instant, a farther supported
    instant of the same scene, and the placebo instant labelled with the wrong period."""
    rng = np.random.default_rng(seed)
    n_blocks = 2 * n_runs
    n_frames = n_blocks * BLOCK
    n_period1 = n_runs // 2
    period_frames = {1: (0, n_period1 * BLOCK - 1), 2: (n_period1 * BLOCK, n_frames - 1)}

    def period_of(block: int) -> int:
        return 1 if block < n_period1 else 2

    x = np.full((n_frames, 13), np.nan)
    y = np.full((n_frames, 13), np.nan)
    detected = np.ones((n_frames, 13), dtype=np.bool_)
    runs: list[Run] = []
    instants: Instants = {}
    for i in range(n_runs):
        angle = rng.uniform(-math.pi / 3, math.pi / 3)
        scenes = (
            (i, (marker_push + BASELINE_MARKER_M, line_push + BASELINE_LINE_M)),
            (n_runs + i, (BASELINE_MARKER_M, BASELINE_LINE_M)),
        )
        for block, push in scenes:
            runner, opponents, _ = _scene(rng, angle, *push)
            sign = SIGN[period_of(block)]
            rows = slice(block * BLOCK, (block + 1) * BLOCK)
            x[rows, 0], y[rows, 0] = (sign * runner).T
            for j in range(12):
                x[rows, 1 + j], y[rows, 1 + j] = (sign * opponents[:, j]).T
        t_c = i * BLOCK + ANCHOR
        t_p = (n_runs + i) * BLOCK + ANCHOR
        run = Run(
            match_id,
            f"r{i}",
            7,
            100,
            period_of(i),
            t_c,
            t_c + RUN_FRAMES,
            SUBTYPES[i % len(SUBTYPES)],
            f"p{i}",
        )
        runs.append(run)
        detected[t_p - 10, 0] = False
        instants[(match_id, run.event_id)] = [(2, t_p + 30), (2, t_p - 10), (1, t_p), (2, t_p)]
    tracking = MatchTracking(
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
        counting_only=counting_only,
    )
    return tracking, runs, instants


def _placebo_instant(run: Run, instants: Instants) -> tuple[int, int]:
    return instants[(run.match_id, run.event_id)][-1]


def _parquet(path: Path, table: pa.Table) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _write_warehouse(root: Path, tracking: MatchTracking, runs: list[Run]) -> None:
    """The synthetic match as the silver and bronze files `load_tracking`, `load_runs` and
    `placebo` read, in their layout and with their columns: `frames` (plus a ball row, which
    the player filter must drop), `dim_period`, `dim_team_period`, `match_players`,
    `dynamic_events` (the runs alone, so no placebo candidate comes from the events) and
    `phases_of_play`."""
    m = tracking.match_id
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
    ball = pa.table(
        {
            "frame_native": pa.array([tracking.frame0], pa.int64()),
            "entity_id": ["ball"],
            "entity_kind": ["ball"],
            "team_id": pa.array([None], pa.string()),
            "x_m": [0.0],
            "y_m": [0.0],
            "is_detected": [True],
        }
    )
    _parquet(
        root / "silver" / "frames" / "sport=football" / f"native_match_id={m}" / "data.parquet",
        pa.concat_tables([frames, ball]),
    )
    _parquet(
        root / "silver" / "dim_period" / "data.parquet",
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
        root / "silver" / "dim_team_period" / "data.parquet",
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
        root / "bronze" / "football" / "dynamic_events" / f"{m}.parquet",
        pa.table(
            {
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
                "team_in_possession_phase_type": ["build_up"] * len(runs),
                "associated_player_possession_frame_start": pa.array(
                    [None] * len(runs), pa.int64()
                ),
            }
        ),
    )
    _parquet(
        root / "bronze" / "football" / "phases_of_play" / f"{m}.parquet",
        pa.table(
            {
                "match_id": [m] * len(tracking.period_frames),
                "index": list(tracking.period_frames),
                "period": list(tracking.period_frames),
                "frame_start": [a for a, _ in tracking.period_frames.values()],
                "frame_end": [b for _, b in tracking.period_frames.values()],
            }
        ),
    )


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
    assert not loaded.counting_only
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
    blind = MatchTracking(
        **{
            **{f.name: getattr(tracking, f.name) for f in fields(MatchTracking)},
            "detected": undetected,
        }
    )
    assert not placebo_supported(blind, run, 1, 60)


def test_the_nearest_supported_instant_wins_and_ties_go_to_the_earlier() -> None:
    tracking, run = _passing_by()  # t_c = 40
    assert choose_placebo(tracking, run, [(1, 80), (1, 55), (1, 70)]) == (1, 55)
    assert choose_placebo(tracking, run, [(1, 50), (1, 30)]) == (1, 30)  # both 10 away
    assert choose_placebo(tracking, run, [(1, 2), (1, 95)]) is None  # neither is supported
    assert choose_placebo(tracking, run, [(1, 8), (1, 60)]) == (1, 60)  # 8 is unsupported


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
    committed = read_protocol(PROTOCOL)  # as task 47 wrote it, whatever stage it is in now
    design = seal({**committed, "stage": STAGE_DESIGN, "history": committed["history"][:1]})
    protocol.write_text(render(design), encoding="utf-8", newline="\n")
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


# Every public function or class of the three modules that touch a match, by what it does
# with a held-out id while the committed protocol is in design. A new public name must be
# added here, and the test below exercises each of the first two groups.
REFUSES_A_HELD_OUT_MATCH = {
    "MatchTracking",
    "load_tracking",
    "run_direction",
    "quantities",
    "pair_effects",
    "require_readable",
    "load_half",
    "assert_held_out_open",
}
COUNTS_ONLY = {
    "load_runs",
    "window_bounds",
    "placebo_supported",
    "choose_placebo",
    "count_match",
    "counting_handle",
    "CountingHandle",
    "counting_match_ids",
    "match_halves",
    "committed_split",
    "committed_protocol",
    "head_stage",
    "dirty_paths",
    "repo_root",
    "coverage_rows",
    "run_runs_coverage",
}
TAKES_NO_MATCH = {
    "whole_frames",
    "render",
    "Run",
    "PairEffect",
    "MatchCounts",
    "HeldOutLocked",
    "CountingOnly",
}


def _public_names(module: object) -> set[str]:
    name = module.__name__  # type: ignore[attr-defined]
    return {
        n
        for n, v in vars(module).items()
        if not n.startswith("_")
        and (inspect.isfunction(v) or inspect.isclass(v))
        and v.__module__ == name
    }


# Taken at import, before any fixture monkeypatches `data.repo_root`.
PUBLIC = _public_names(windows) | _public_names(data) | _public_names(coverage)


def test_every_public_function_refuses_a_held_out_match_or_returns_counts_only(
    design_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavioural, not lexical: with the committed protocol in design, every public name of
    `windows`, `data` and `coverage` is classified, and each one is called with the held-out
    match. The ones that return values refuse it; the ones that count work on a tracking
    loaded with the counting handle and give back booleans, integers, ids or rows of
    counts; a tracking built by hand with the held-out id is refused as it is built, and
    `load_tracking` refuses before it reads a byte."""
    assert PUBLIC == REFUSES_A_HELD_OUT_MATCH | COUNTS_ONLY | TAKES_NO_MATCH
    held, runs, instants = _synthetic(
        3, 1.0, 0.0, seed=2, match_id=HELD_OUT_MATCH, counting_only=True
    )
    root = tmp_path / "data"
    _write_warehouse(root, held, runs)
    run = runs[0]
    d = np.array([1.0, 0.0])

    # refusals
    with pytest.raises(HeldOutLocked):
        MatchTracking(
            **{
                **{f.name: getattr(held, f.name) for f in fields(MatchTracking)},
                "counting_only": False,
            }
        )
    with pytest.raises(HeldOutLocked):
        load_tracking(tmp_path / "nowhere", HELD_OUT_MATCH)  # refused before any read
    with pytest.raises(HeldOutLocked):
        load_tracking(root, HELD_OUT_MATCH)
    with pytest.raises(HeldOutLocked):
        require_readable(HELD_OUT_MATCH)
    with pytest.raises(HeldOutLocked):
        load_half("held_out")
    with pytest.raises(HeldOutLocked):
        data.assert_held_out_open()
    counting = load_tracking(root, HELD_OUT_MATCH, counting=counting_handle(HELD_OUT_MATCH))
    assert counting.counting_only
    with pytest.raises(CountingOnly):
        run_direction(counting, run)
    with pytest.raises(CountingOnly):
        quantities(counting, run, run.period, run.frame_start, d)
    with pytest.raises(CountingOnly):
        pair_effects(counting, runs, instants)
    with pytest.raises(CountingOnly):
        run_direction(held, run)  # the hand-built counting-only one, the same
    with pytest.raises(ValueError, match="cannot load"):
        load_tracking(root, HELD_OUT_MATCH, counting=counting_handle(CI_FIXTURE_MATCH))

    # counts only, on the held-out match
    assert counting_handle(HELD_OUT_MATCH) == CountingHandle(HELD_OUT_MATCH)
    with pytest.raises(ValueError, match="neither half"):
        counting_handle(1)
    assert HELD_OUT_MATCH in counting_match_ids()
    assert match_halves()[HELD_OUT_MATCH] == "held_out"
    assert HELD_OUT_MATCH in data.committed_split()[1]
    assert data.head_stage() == STAGE_DESIGN
    assert data.committed_protocol()["stage"] == STAGE_DESIGN
    assert data.dirty_paths(design_repo) == []
    assert data.repo_root() == design_repo
    loaded_runs = load_runs(root, HELD_OUT_MATCH)
    assert loaded_runs == runs
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
    lo, hi, clipped = window_bounds(counting, run)
    assert isinstance(lo, int) and isinstance(hi, int) and isinstance(clipped, bool)
    assert placebo_supported(counting, run, *_placebo_instant(run, instants)) is True
    assert choose_placebo(counting, run, instants[(HELD_OUT_MATCH, run.event_id)]) == (
        _placebo_instant(run, instants)
    )
    counts = count_match(counting, runs, instants)
    assert isinstance(counts, MatchCounts)
    assert counts.runs == counts.clean == counts.placebo_found == counts.analysis_set == 3
    for f in fields(MatchCounts):
        value = getattr(counts, f.name)
        assert isinstance(value, int | float | tuple), f.name
    (row,) = coverage_rows(root, [HELD_OUT_MATCH])
    assert len(row) == len(HEADER) and row[HEADER.index("half")] == "held_out"
    _assert_count_row(dict(zip(HEADER, row, strict=True)))
    reports = tmp_path / "reports"
    assert run_runs_coverage(root, reports) == 1  # one match of 20: writes nothing
    assert not (reports / COVERAGE_NAME).exists()
    assert "1 of the 20 matches" in capsys.readouterr().out

    # and the handle is counting-only on a calibration match as well
    cal, cal_runs, cal_instants = _synthetic(3, 1.0, 0.0, seed=2, match_id=CI_FIXTURE_MATCH)
    _write_warehouse(root, cal, cal_runs)
    assert len(pair_effects(load_tracking(root, CI_FIXTURE_MATCH), cal_runs, cal_instants)) == 3
    with pytest.raises(CountingOnly):
        pair_effects(
            load_tracking(root, CI_FIXTURE_MATCH, counting=counting_handle(CI_FIXTURE_MATCH)),
            cal_runs,
            cal_instants,
        )


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
        assert f.type in ("int", "float", "tuple[int, ...]"), f.name
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
        coverage._has_frames(data_root(), int(m)) for m in _committed_rows()
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
    """The 20 rows, recounted from the real frames through the counting handles, are the
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
