"""Windows, placebos and the estimator, validated on synthetic matches (task 48).

The estimator is run end to end only here, on matches fabricated with a known effect: real
data produces counts (`runs_coverage.csv`) and nothing else. The generator writes positions
from geometry it owns (an explicit marker 2 m from the runner, an explicit line of two
defenders, a goalkeeper behind them) and never calls the estimator, so the two cannot share
a defect. It writes the venue frame the way silver does (the runner's team attacks towards
-x here), so the attack-frame turn is exercised as well.

Mutations recorded in tasks/todo.md: the sign of the run direction flipped in
`effect.run_direction` fails the planted-effect test; the marker taken at t_c + 1 s in
`windows.quantities` fails the test that pins it at t_c.
"""

from __future__ import annotations

import csv
import math
import shutil
from dataclasses import fields
from pathlib import Path

import duckdb
import numpy as np
import pytest

from tracklab.paths import data_root
from tracklab.runs import effect, placebo
from tracklab.runs.coverage import COVERAGE_NAME, HEADER, _row, match_halves, run_runs_coverage
from tracklab.runs.data import HeldOutLocked, counting_match_ids, load_half
from tracklab.runs.protocol import (
    EFFECT_WINDOW_S,
    MIN_RUN_LENGTH_M,
    PLACEBO_EXCLUDES_TEAMMATES_RUNS,
    SAMPLE_RATE_HZ,
    VELOCITY_WINDOW_S,
    read_protocol,
)
from tracklab.runs.windows import (
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
TEAM, OTHER = "fb:100", "fb:200"


def test_the_windows_are_the_protocols() -> None:
    assert EFFECT_FRAMES == round(EFFECT_WINDOW_S * SAMPLE_RATE_HZ) == 20
    assert VELOCITY_FRAMES == round(VELOCITY_WINDOW_S * SAMPLE_RATE_HZ) == 5
    windows = read_protocol(PROTOCOL)["design"]["windows"]
    assert windows["effect_s"][1] == EFFECT_WINDOW_S
    assert windows["velocity_s"] == VELOCITY_WINDOW_S
    assert PLACEBO_RULE == ("team_overlap" if PLACEBO_EXCLUDES_TEAMMATES_RUNS else "runner_overlap")


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


def _venue(attack_xy: np.ndarray) -> np.ndarray:
    """The runner's team attacks towards -x in the venue frame: sign -1."""
    return -attack_xy


def _scene(
    rng: np.random.Generator, direction_angle: float, marker_push: float, line_push: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One scene of BLOCK frames in the attack frame: runner (BLOCK, 2), opponents
    (BLOCK, 12, 2). Opponent 0 is the marker, 1 and 2 the two deepest outfield players, 3 to 10
    the rest of the line-up, 11 the goalkeeper."""
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


def _synthetic(
    n_runs: int, marker_push: float, line_push: float, seed: int, match_id: int = CI_FIXTURE_MATCH
) -> tuple[MatchTracking, list[Run], dict[tuple[int, str], list[tuple[int, int]]]]:
    """`n_runs` runs and one placebo scene per run, in disjoint blocks of one period."""
    rng = np.random.default_rng(seed)
    n_blocks = 2 * n_runs
    n_frames = n_blocks * BLOCK
    x = np.full((n_frames, 13), np.nan)
    y = np.full((n_frames, 13), np.nan)
    runs: list[Run] = []
    instants: dict[tuple[int, str], list[tuple[int, int]]] = {}
    for i in range(n_runs):
        angle = rng.uniform(-math.pi / 3, math.pi / 3)
        for block, push in ((2 * i, (marker_push, line_push)), (2 * i + 1, (0.0, 0.0))):
            runner, opponents, _ = _scene(rng, angle, *push)
            rows = slice(block * BLOCK, (block + 1) * BLOCK)
            x[rows, 0], y[rows, 0] = _venue(runner).T
            for j in range(12):
                x[rows, 1 + j], y[rows, 1 + j] = _venue(opponents[:, j]).T
        t_c = 2 * i * BLOCK + ANCHOR
        run = Run(
            match_id,
            f"r{i}",
            7,
            100,
            1,
            t_c,
            t_c + RUN_FRAMES,
            SUBTYPES[i % len(SUBTYPES)],
            f"p{i}",
        )
        runs.append(run)
        instants[(match_id, run.event_id)] = [(1, (2 * i + 1) * BLOCK + ANCHOR)]
    tracking = MatchTracking(
        match_id=match_id,
        frame0=0,
        x=x,
        y=y,
        detected=np.ones((n_frames, 13), dtype=np.bool_),
        entities=("fb:7", *(f"fb:{300 + j}" for j in range(12))),
        team=(TEAM, *([OTHER] * 12)),
        is_goalkeeper=np.array([False] * 12 + [True], dtype=np.bool_),
        period_frames={1: (0, n_frames - 1)},
        attack_sign={(1, TEAM): -1, (1, OTHER): 1},
    )
    return tracking, runs, instants


def _recovered(push: float, line: float, seed: int) -> tuple[float, float, float, float, int]:
    tracking, runs, instants = _synthetic(3000, push, line, seed)
    pairs = pair_effects(tracking, runs, instants, protocol_path=PROTOCOL)
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


def test_the_line_ignores_the_goalkeeper() -> None:
    tracking, runs, instants = _synthetic(200, 0.0, PLANTED_LINE_M, seed=51)
    keeper_counts_as_outfield = MatchTracking(
        **{
            **{f.name: getattr(tracking, f.name) for f in fields(MatchTracking)},
            "is_goalkeeper": np.zeros(13, dtype=np.bool_),
        }
    )
    with_keeper = pair_effects(keeper_counts_as_outfield, runs, instants, protocol_path=PROTOCOL)
    without = pair_effects(tracking, runs, instants, protocol_path=PROTOCOL)
    mean_with = float(np.mean([p.line_m for p in with_keeper]))
    mean_without = float(np.mean([p.line_m for p in without]))
    assert mean_without == pytest.approx(PLANTED_LINE_M, rel=0.1)
    assert abs(mean_with - PLANTED_LINE_M) > 0.3


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
    got = quantities(tracking, run, run.frame_start, np.array([1.0, 0.0]))
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
    assert choose_placebo(tracking, run, [(1, 80), (1, 55), (1, 70)]) == 55
    assert choose_placebo(tracking, run, [(1, 50), (1, 30)]) == 30  # both 10 away
    assert choose_placebo(tracking, run, [(1, 2), (1, 95)]) is None  # neither is supported
    assert choose_placebo(tracking, run, [(1, 8), (1, 60)]) == 60  # 8 is unsupported, 60 is not


def test_window_bounds_clip_to_the_period() -> None:
    tracking, _ = _passing_by()
    near_start = Run(CI_FIXTURE_MATCH, "a", 7, 100, 1, 3, 10, "support", "p")
    assert window_bounds(tracking, near_start) == (0, 40, True)
    inside = Run(CI_FIXTURE_MATCH, "b", 7, 100, 1, 20, 30, "support", "p")
    assert window_bounds(tracking, inside) == (10, 60, False)


# --- the guard: values leave only through readable matches ---------------------------------


def test_pair_effects_refuses_a_held_out_match_and_opens_a_calibration_one(
    tmp_path: Path,
) -> None:
    protocol = tmp_path / "runs_protocol.json"  # outside any git repository: never frozen
    shutil.copy(PROTOCOL, protocol)
    held, runs, instants = _synthetic(3, 1.0, 0.0, seed=1, match_id=HELD_OUT_MATCH)
    with pytest.raises(HeldOutLocked):
        pair_effects(held, runs, instants, protocol_path=protocol)
    ok, runs, instants = _synthetic(3, 1.0, 0.0, seed=1, match_id=CI_FIXTURE_MATCH)
    assert len(pair_effects(ok, runs, instants, protocol_path=protocol)) == 3
    stranger, runs, instants = _synthetic(3, 1.0, 0.0, seed=1, match_id=1)
    with pytest.raises(ValueError, match="neither half"):
        pair_effects(stranger, runs, instants, protocol_path=protocol)


def test_counting_covers_both_halves_and_returns_only_counts() -> None:
    ids = counting_match_ids(PROTOCOL)
    halves = match_halves(PROTOCOL)
    assert ids == sorted(halves)
    assert len(ids) == 20
    assert sorted(m for m, h in halves.items() if h == "calibration") == load_half(
        "calibration", PROTOCOL
    )
    # a count has no coordinate: every field is an integer or a detection fraction
    for f in fields(MatchCounts):
        assert f.type in ("int", "float", "tuple[int, ...]"), f.name
    assert not [h for h in HEADER if h.split("_")[0] in ("x", "y", "pos", "disp", "effect")]


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
    return counts, len(pair_effects(tracking, runs, instants, protocol_path=PROTOCOL))


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
    assert sorted(int(m) for m in rows) == counting_match_ids(PROTOCOL)
    assert {int(m): r["half"] for m, r in rows.items()} == match_halves(PROTOCOL)

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


# --- the command ----------------------------------------------------------------------------


def _reports_copy(tmp_path: Path) -> Path:
    reports = tmp_path / "reports"
    reports.mkdir()
    for name in ("runs_protocol.json", COVERAGE_NAME):
        shutil.copy(REPORTS / name, reports / name)
    return reports


def test_coverage_refuses_to_write_from_a_partial_warehouse(tmp_path: Path) -> None:
    reports = _reports_copy(tmp_path)
    before = (reports / COVERAGE_NAME).read_bytes()
    assert run_runs_coverage(FIXTURES, reports) == 1
    assert (reports / COVERAGE_NAME).read_bytes() == before


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
    windows = (PIPELINE / "src" / "tracklab" / "runs" / "windows.py").read_text(encoding="utf-8")
    assert "silver" in windows and "dim_team_period" in windows and '"frames"' in windows
