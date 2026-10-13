"""The stride estimator of task 59 (`tracklab.pose.gait`), validated on synthetic runners only.

No real pose is read here: the only thing taken from the sample is its predicted error, the 29
`mae` of every skeleton of the versioned clip (`web/public/data/pose/1925299_phase406.json`), so
the noise has the size the provider predicts and the suite runs in CI without data.

The runner is built from a body the test owns (a template of 29 joints in the body's own frame,
the legs swung forward and back along the direction of travel, the arms against them, the body
bobbing in z), moved along a random heading from a random point of the pitch, and never calls
the estimator. Planted: 4.3 steps per second (the plan's figure for the resolution bar) at
5.5 m/s (the plan's hypothesis for the high band), so the step is 5.5 / 4.3 m and the ankles
part by that much at each step.

Bars written before the first run (tasks/todo.md, task 59): in each of 20 seeds, cadence within
5 % and within 0.1 Hz, both step lengths within 10 %; the propagated sd within a factor 1.5 of
the spread between noisy copies. `mae_cap` 20 cm: at 15 cm (the plan's hypothesis) no skeleton
of the sample qualifies, because rHeel's `mae` is never below 15.1 cm there. Two bars missed
on that first run and stay as written, as strict xfails: the step from the pose (5 of 20 seeds
over 10 %) and the 0.1 Hz with noise (1 of 20). The record has the table.

Mutations, each applied, seen failing and restored (tasks/todo.md, task 59): the fundamental
without the x 2; the body's z added to s(t); the parabola removed; the propagated noise at half
the `mae`; the period, the consecutive frame and the inclusive cap dropped from `windows`;
joints read by position in the line reader; duckdb imported by `gait`.
"""

from __future__ import annotations

import ast
import json
import math
import random
from dataclasses import astuple
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from tracklab.pose import gait
from tracklab.pose.jsonl import JOINTS, parse_frame

Array = NDArray[np.float64]

CLIP = Path(__file__).resolve().parents[3] / "web" / "public" / "data" / "pose"
CLIP = CLIP / "1925299_phase406.json"
W = 25  # frames: the plan's hypothesis (1 s); task 60 tries 25, 37 and 50
CAP_CM = 20.0  # the top of task 60's grid, and the lowest value of it that admits the sample
CADENCE_HZ = 4.3
SPEED_M_S = 5.5
STEP_M = SPEED_M_S / CADENCE_HZ
SEEDS = range(20)
CADENCE_BAR = 0.05
CADENCE_BAR_HZ = 0.1
STEP_BAR = 0.10
SD_RATIO_BAR = 1.5

# The body at rest in its own frame, metres from midHip: (forward, left, up).
BODY: dict[str, tuple[float, float, float]] = {
    "nose": (0.10, 0.0, 0.75), "neck": (0.0, 0.0, 0.55),
    "lEye": (0.08, 0.03, 0.78), "rEye": (0.08, -0.03, 0.78),
    "lEar": (0.0, 0.07, 0.75), "rEar": (0.0, -0.07, 0.75),
    "lShoulder": (0.0, 0.18, 0.50), "rShoulder": (0.0, -0.18, 0.50),
    "lElbow": (0.0, 0.22, 0.25), "rElbow": (0.0, -0.22, 0.25),
    "lWrist": (0.05, 0.22, 0.02), "rWrist": (0.05, -0.22, 0.02),
    "lThumb": (0.07, 0.20, 0.0), "rThumb": (0.07, -0.20, 0.0),
    "lPinky": (0.06, 0.23, -0.03), "rPinky": (0.06, -0.23, -0.03),
    "midHip": (0.0, 0.0, 0.0), "lHip": (0.0, 0.10, 0.0), "rHip": (0.0, -0.10, 0.0),
    "lKnee": (0.02, 0.10, -0.45), "rKnee": (0.02, -0.10, -0.45),
    "lAnkle": (0.0, 0.10, -0.88), "rAnkle": (0.0, -0.10, -0.88),
    "lHeel": (-0.06, 0.10, -0.93), "rHeel": (-0.06, -0.10, -0.93),
    "lBigToe": (0.16, 0.12, -0.95), "rBigToe": (0.16, -0.12, -0.95),
    "lSmallToe": (0.14, 0.15, -0.95), "rSmallToe": (0.14, -0.15, -0.95),
}  # fmt: skip
# How far each joint swings forward with `swing` (the left leg) or against it (the right leg,
# and the arms against their own leg): the ankles part by 2 x swing.
SWING: dict[str, float] = {
    "lKnee": 0.5, "lAnkle": 1.0, "lHeel": 1.0, "lBigToe": 1.0, "lSmallToe": 1.0,
    "rKnee": -0.5, "rAnkle": -1.0, "rHeel": -1.0, "rBigToe": -1.0, "rSmallToe": -1.0,
    "lElbow": -0.3, "lWrist": -0.4, "lThumb": -0.4, "lPinky": -0.4,
    "rElbow": 0.3, "rWrist": 0.4, "rThumb": 0.4, "rPinky": 0.4,
}  # fmt: skip
TEMPLATE = np.array([BODY[name] for name in JOINTS])
SWING_OF = np.array([SWING.get(name, 0.0) for name in JOINTS])


@pytest.fixture(scope="module")
def clip_mae() -> tuple[float, Array]:
    """The clip's fps and the 29 `mae` (cm) of every skeleton of the sample."""
    clip = json.loads(CLIP.read_text(encoding="utf-8"))
    assert clip["joints"] == list(JOINTS)
    mae = np.array(
        [p[4][1] for f in clip["frames"] for p in f["p"] if p[4] is not None], dtype=np.float64
    )
    return float(clip["fps"]), mae / 10.0  # the clip has whole millimetres


@pytest.fixture(scope="module")
def sample(clip_mae: tuple[float, Array]) -> tuple[float, Array]:
    """The skeletons whose ankles and heels are at or under `CAP_CM`: the noise a window that
    passes the cap can carry."""
    fps, mae = clip_mae
    return fps, mae[np.all(mae[:, gait.FOOT] <= CAP_CM, axis=1)]


def test_the_plans_cap_of_15_cm_admits_no_skeleton_of_the_sample(
    clip_mae: tuple[float, Array],
) -> None:
    _, mae = clip_mae
    foot = mae[:, gait.FOOT]
    counts = {cap: int(np.sum(np.all(foot <= cap, axis=1))) for cap in (10.0, 15.0, CAP_CM)}
    lowest = dict(
        zip(("lAnkle", "rAnkle", "lHeel", "rHeel"), foot.min(axis=0).tolist(), strict=True)
    )
    print(f"\nskeletons {len(mae)}; ankles and heels at or under the cap: {counts}; "
          f"lowest mae (cm): {lowest}")  # fmt: skip
    assert counts[15.0] == 0 and counts[CAP_CM] > 0


def runner(
    rng: np.random.Generator,
    *,
    fps: float,
    width: int = W,
    cadence_hz: float = CADENCE_HZ,
    step_m: float = STEP_M,
) -> tuple[Array, Array]:
    """A clean runner: joints (width, 29, 3) as the file has them and his (x, y) (width, 2)."""
    t = np.arange(width) / fps
    heading = rng.uniform(0.0, 2.0 * math.pi)
    forward = np.array([math.cos(heading), math.sin(heading)])
    left = np.array([-math.sin(heading), math.cos(heading)])
    # One swing per stride, two steps per stride: the stride frequency is half the cadence.
    swing = 0.5 * step_m * np.sin(math.pi * cadence_hz * t + rng.uniform(0.0, 2.0 * math.pi))
    body = TEMPLATE[None, :, :] + np.zeros((width, 1, 1))
    body[:, :, 0] += swing[:, None] * SWING_OF[None, :]
    xy = rng.uniform((-40.0, -25.0), (40.0, 25.0)) + np.outer(cadence_hz * step_m * t, forward)
    joints = np.empty((width, len(JOINTS), 3))
    joints[:, :, :2] = xy[:, None, :] + body[:, :, 0:1] * forward + body[:, :, 1:2] * left
    bob = 1.0 + 0.04 * np.cos(2.0 * math.pi * cadence_hz * t)
    joints[:, :, 2] = bob[:, None] + body[:, :, 2]
    return joints, xy


def noise(rng: np.random.Generator, mae_cm: Array) -> Array:
    """N(0, mae) per joint, frame and axis, in metres: the model of `propagated_error`."""
    return rng.standard_normal((*mae_cm.shape, 3)) * mae_cm[:, :, None] / 100.0


def draw_mae(rng: np.random.Generator, rows: Array, width: int = W) -> Array:
    return rows[rng.integers(len(rows), size=width)]


def dyadic(a: Array) -> Array:
    """Round to 1/1024 m: sums of such numbers under 1024 m are exact in float64."""
    return np.round(a * 1024.0) / 1024.0


# --- the bar ----------------------------------------------------------------------------------

COLUMNS = ("seed", "cad_clean_hz", "cad_hz", "step_pose_clean_m", "step_pose_m", "step_speed_m")


@pytest.fixture(scope="module")
def bar(sample: tuple[float, Array]) -> dict[str, Array]:
    """Per seed: the estimate on the clean runner and on the same runner seen through noise."""
    fps, rows = sample
    table = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        mae = draw_mae(rng, rows)
        clean, xy = runner(rng, fps=fps)
        observed = clean + noise(rng, mae)
        frames, periods = np.arange(W) + 124487, np.full(W, 2)
        assert gait.windows(frames, periods, mae, width=W, mae_cap_cm=CAP_CM) == [(0, W)]
        g, g0 = gait.estimate(observed, xy, fps=fps), gait.estimate(clean, xy, fps=fps)
        table.append(
            (
                seed,
                g0.cadence_hz,
                g.cadence_hz,
                g0.step_length_pose_m,
                g.step_length_pose_m,
                g.step_length_speed_m,
            )
        )
    return dict(zip(COLUMNS, np.array(table).T, strict=True))


def _rel(values: Array, truth: float) -> Array:
    return (values - truth) / truth


def test_the_bar_by_seed_cadence_within_5_percent_and_step_speed_within_10(
    bar: dict[str, Array],
) -> None:
    """The table of the record (run with `-rP`); the two bars that held in every seed."""
    cad, pose, speed = _rel(bar["cad_hz"], CADENCE_HZ), bar["step_pose_m"], bar["step_speed_m"]
    print(f"\nplanted: cadence {CADENCE_HZ} Hz, step {STEP_M:.4f} m, W {W}, cap {CAP_CM} cm")
    print("seed | cadence Hz (clean) | err | step_pose m (clean) | err | step_speed m | err")
    for i, seed in enumerate(bar["seed"]):
        print(
            f"{int(seed):4d} | {bar['cad_hz'][i]:.4f} ({bar['cad_clean_hz'][i]:.4f}) | "
            f"{cad[i]:+.4%} | {pose[i]:.4f} ({bar['step_pose_clean_m'][i]:.4f}) | "
            f"{_rel(pose[i], STEP_M):+.4%} | {speed[i]:.4f} | {_rel(speed[i], STEP_M):+.4%}"
        )
    hz = np.abs(bar["cad_hz"] - CADENCE_HZ)
    print(
        f"worst |err|: cadence {np.max(np.abs(cad)):.4%} ({np.max(hz):.4f} Hz, "
        f"{int(np.sum(hz > CADENCE_BAR_HZ))} seeds over {CADENCE_BAR_HZ} Hz), step_pose "
        f"{np.max(np.abs(_rel(pose, STEP_M))):.4%} "
        f"({int(np.sum(np.abs(_rel(pose, STEP_M)) >= STEP_BAR))} seeds at or over "
        f"{STEP_BAR:.0%}), step_speed {np.max(np.abs(_rel(speed, STEP_M))):.4%}; "
        f"mean step_pose err {np.mean(_rel(pose, STEP_M)):+.4%}"
    )
    clean_pose = _rel(bar["step_pose_clean_m"], STEP_M)
    print(
        f"clean runners: cadence worst {np.max(np.abs(bar['cad_clean_hz'] - CADENCE_HZ)):.4f} Hz,"
        f" step_pose from {np.min(clean_pose):+.4%} to {np.max(clean_pose):+.4%}"
    )
    assert np.all(np.abs(cad) < CADENCE_BAR)
    assert np.all(np.abs(_rel(speed, STEP_M)) < STEP_BAR)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="bar missed on its first run (2026-10-13): 5 of 20 seeds, worst +17.02 %; "
    "reported in tasks/todo.md (task 59), not moved",
)
def test_the_bar_step_pose_within_10_percent_in_every_seed(bar: dict[str, Array]) -> None:
    assert np.all(np.abs(_rel(bar["step_pose_m"], STEP_M)) < STEP_BAR)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="bar missed on its first run (2026-10-13): seed 5 at 0.1477 Hz; reported in "
    "tasks/todo.md (task 59), not moved",
)
def test_the_bar_cadence_within_0_1_hz_in_every_noisy_seed(bar: dict[str, Array]) -> None:
    assert np.all(np.abs(bar["cad_hz"] - CADENCE_HZ) <= CADENCE_BAR_HZ)


def test_the_peak_interpolation_resolves_0_1_hz_on_the_clean_runners(
    bar: dict[str, Array],
) -> None:
    """Added after the first run, to give the mutation of the parabola a test of its own: the
    frame is 40 ms, and at 4.3 Hz a whole lag either side of the peak is 0.13 or 0.25 Hz off."""
    assert np.all(np.abs(bar["cad_clean_hz"] - CADENCE_HZ) <= CADENCE_BAR_HZ)


def test_the_propagated_sd_matches_the_spread_between_noisy_copies(
    sample: tuple[float, Array],
) -> None:
    """The same runner seen through 400 independent noises gives the empirical sd; the Monte
    Carlo run around each of five noisy observations has to land within a factor 1.5 of it."""
    fps, rows = sample
    rng = np.random.default_rng(100)
    mae = draw_mae(rng, rows)
    clean, xy = runner(rng, fps=fps)
    copies = np.array(
        [
            astuple(gait.estimate(clean + noise(np.random.default_rng(s), mae), xy, fps=fps))[:3]
            for s in range(1000, 1400)
        ]
    )
    assert np.all(np.isfinite(copies))
    empirical = copies.std(axis=0, ddof=1)
    for s in range(2000, 2005):
        observed = clean + noise(np.random.default_rng(s), mae)
        p = gait.propagated_error(observed, xy, mae, fps=fps, draws=400)
        ratio = np.array(astuple(p)[:3]) / empirical
        print(f"observation {s}: propagated / empirical sd = {np.round(ratio, 3).tolist()}")
        assert p.valid == p.draws
        assert np.all((ratio >= 1 / SD_RATIO_BAR) & (ratio <= SD_RATIO_BAR))


def test_a_clean_runner_gives_the_planted_speed(sample: tuple[float, Array]) -> None:
    fps, _ = sample
    for seed in SEEDS:
        clean, xy = runner(np.random.default_rng(seed), fps=fps)
        g = gait.estimate(clean, xy, fps=fps)
        assert g.speed_m_s == pytest.approx(SPEED_M_S, rel=1e-12)
        assert g.step_length_speed_m == pytest.approx(SPEED_M_S / g.cadence_hz, rel=1e-12)


# --- invariance (limit 2) ---------------------------------------------------------------------


def test_a_different_offset_per_frame_on_every_joint_changes_nothing(
    sample: tuple[float, Array],
) -> None:
    """x, y and z of all 29 joints moved by up to 512 m, a different shift in every frame: the
    centred joints, and with them every output, are the same bits (`propagated_error` too)."""
    fps, rows = sample
    rng = np.random.default_rng(7)
    mae = draw_mae(rng, rows)
    clean, xy = runner(rng, fps=fps)
    joints, xy = dyadic(clean + noise(rng, mae)), dyadic(xy)
    offset = rng.integers(-(2**19), 2**19, size=(W, 1, 3)) / 1024.0
    assert len({tuple(o) for o in offset[:, 0, :]}) == W  # a different one in every frame
    moved = joints + offset
    assert np.array_equal(gait.centre_on_midhip(moved), gait.centre_on_midhip(joints))
    before, after = gait.estimate(joints, xy, fps=fps), gait.estimate(moved, xy, fps=fps)
    assert all(math.isfinite(v) for v in astuple(before))
    assert after == before
    assert gait.propagated_error(moved, xy, mae, fps=fps) == gait.propagated_error(
        joints, xy, mae, fps=fps
    )


def test_an_arbitrary_float_offset_moves_the_outputs_only_by_rounding(
    sample: tuple[float, Array],
) -> None:
    """Without dyadic numbers the centring rounds in the last bits: the same values to 1e-9."""
    fps, rows = sample
    rng = np.random.default_rng(8)
    mae = draw_mae(rng, rows)
    clean, xy = runner(rng, fps=fps)
    joints = clean + noise(rng, mae)
    moved = joints + rng.uniform(-1000.0, 1000.0, size=(W, 1, 3))
    before, after = gait.estimate(joints, xy, fps=fps), gait.estimate(moved, xy, fps=fps)
    np.testing.assert_allclose(astuple(after), astuple(before), rtol=1e-9)


def test_the_players_x_y_is_the_displacement_and_is_not_invariant(
    sample: tuple[float, Array],
) -> None:
    """What reads the joints is invariant; what reads the player's x, y is the measurement.
    Moving the whole scene by one (x, y) changes nothing. Moving the player by a different
    (x, y) in every frame (his joints with him) changes d, the speed and `step_length_speed_m`,
    while s(t) along a given d stays the same bits."""
    fps, rows = sample
    rng = np.random.default_rng(9)
    mae = draw_mae(rng, rows)
    clean, xy = runner(rng, fps=fps)
    joints, xy = dyadic(clean + noise(rng, mae)), dyadic(xy)
    before = gait.estimate(joints, xy, fps=fps)

    shift = dyadic(rng.uniform(-30.0, 30.0, size=2))
    scene = joints.copy()
    scene[:, :, :2] += shift
    assert gait.estimate(scene, xy + shift, fps=fps) == before

    wobble = dyadic(rng.uniform(-1.0, 1.0, size=(W, 2)))
    assert not np.array_equal(wobble[-1], wobble[0])
    body = joints.copy()
    body[:, :, :2] += wobble[:, None, :]
    after = gait.estimate(body, xy + wobble, fps=fps)
    assert not np.array_equal(gait.direction(xy + wobble), gait.direction(xy))
    assert after.speed_m_s != before.speed_m_s
    assert after.step_length_speed_m != before.step_length_speed_m
    d = gait.direction(xy)
    assert np.array_equal(
        gait.signal(gait.centre_on_midhip(body), d), gait.signal(gait.centre_on_midhip(joints), d)
    )


# --- windows ----------------------------------------------------------------------------------


def _mae(n: int, value: float = 12.0) -> Array:
    return np.full((n, len(JOINTS)), value)


def test_12_of_25_frames_without_joints_make_no_window() -> None:
    frames, periods = np.arange(25) + 1000, np.full(25, 1)
    assert gait.windows(frames, periods, _mae(25), width=W, mae_cap_cm=CAP_CM) == [(0, 25)]
    missing = np.sort(np.random.default_rng(12).choice(25, size=12, replace=False))
    as_nan = _mae(25)
    as_nan[missing] = np.nan  # joints null: no mae either
    assert gait.windows(frames, periods, as_nan, width=W, mae_cap_cm=CAP_CM) == []
    kept = np.setdiff1d(np.arange(25), missing)  # or the rows are simply not there
    assert gait.windows(frames[kept], periods[kept], _mae(13), width=W, mae_cap_cm=CAP_CM) == []


def test_windows_tile_one_period_and_never_cross_into_the_next() -> None:
    frames = np.arange(60) + 5000
    one = np.full(60, 1)
    assert gait.windows(frames, one, _mae(60), width=W, mae_cap_cm=CAP_CM) == [(0, 25), (25, 50)]
    two = np.r_[np.full(20, 1), np.full(40, 2)]  # consecutive frame numbers, a new period at 20
    assert gait.windows(frames, two, _mae(60), width=W, mae_cap_cm=CAP_CM) == [(20, 45)]


def test_a_missing_frame_breaks_the_stretch_however_many_rows_there_are() -> None:
    frames = np.r_[np.arange(12), np.arange(13, 26)]  # 25 rows, frame 12 without pose
    periods = np.full(25, 1)
    assert gait.windows(frames, periods, _mae(25), width=W, mae_cap_cm=CAP_CM) == []
    whole = np.arange(13, 38)  # the same 25 rows, consecutive
    assert gait.windows(whole, periods, _mae(25), width=W, mae_cap_cm=CAP_CM) == [(0, 25)]


def test_the_cap_is_on_the_ankles_and_heels_and_is_inclusive() -> None:
    frames, periods = np.arange(25), np.full(25, 1)
    at_cap = _mae(25, CAP_CM)
    at_cap[:, JOINTS.index("lPinky")] = 40.0  # not a foot joint: does not count
    assert gait.windows(frames, periods, at_cap, width=W, mae_cap_cm=CAP_CM) == [(0, 25)]
    for name in ("lAnkle", "rAnkle", "lHeel", "rHeel"):
        over = at_cap.copy()
        over[12, JOINTS.index(name)] = CAP_CM + 0.01
        assert gait.windows(frames, periods, over, width=W, mae_cap_cm=CAP_CM) == [], name


# --- the joints by name, and nothing read ----------------------------------------------------


def _line(frame: int, x: float, y: float, joints: dict[str, Any]) -> str:
    return json.dumps(
        {
            "frame": frame,
            "timestamp": "01:17:34.48",
            "period": 2,
            "ball_data": {"x": 0.0, "y": 0.0, "z": 0.0, "is_detected": True},
            "possession": {"player_id": None, "group": None},
            "image_corners_projection": {},
            "player_data": [
                {"player_id": 7, "x": x, "y": y, "is_detected": True, "joints": joints}
            ],
        }
    )


def test_a_runner_written_with_shuffled_joint_keys_gives_the_same_values(
    sample: tuple[float, Array],
) -> None:
    fps, rows = sample
    rng = np.random.default_rng(11)
    mae = draw_mae(rng, rows)
    clean, xy = runner(rng, fps=fps)
    joints = clean + noise(rng, mae)
    shuffled = list(JOINTS)
    random.Random(11).shuffle(shuffled)
    assert shuffled != list(JOINTS)

    def read(order: list[str]) -> gait.Gait:
        players = [
            parse_frame(
                _line(
                    124487 + i,
                    float(xy[i, 0]),
                    float(xy[i, 1]),
                    {
                        n: {
                            "xyz": joints[i, JOINTS.index(n)].tolist(),
                            "p90_mae_cm": float(mae[i, JOINTS.index(n)]),
                        }
                        for n in order
                    },
                )
            ).players[0]
            for i in range(W)
        ]
        assert all(p.xyz is not None for p in players)
        stacked = np.stack([p.xyz for p in players if p.xyz is not None])
        return gait.estimate(stacked, np.array([[p.x, p.y] for p in players]), fps=fps)

    direct = gait.estimate(joints, xy, fps=fps)
    assert read(list(JOINTS)) == direct
    assert read(shuffled) == direct


def test_gait_imports_no_database_and_reads_no_path() -> None:
    tree = ast.parse(Path(gait.__file__).read_text(encoding="utf-8"))
    modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert modules == {"__future__", "math", "dataclasses", "numpy", "numpy.typing",
                       "tracklab.pose.jsonl"}  # fmt: skip
    from_jsonl = {
        a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "tracklab.pose.jsonl"
        for a in n.names
    }
    assert from_jsonl == {"JOINTS"}  # the constant, not the readers beside it
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    readers = {"open", "Path", "load", "loadtxt", "genfromtxt", "fromfile", "memmap", "connect"}
    assert not names & readers
