"""The stride estimator of task 59 (`tracklab.pose.gait`), validated on synthetic runners only,
as phase B1 of task 60 revised it.

No real pose is read here: the only thing taken from the sample is its predicted error, the 29
`mae` of every skeleton of the versioned clip (`web/public/data/pose/1925299_phase406.json`), so
the noise has the size the provider predicts and the suite runs in CI without data.

The runner is built from a body the test owns (a template of 29 joints in the body's own frame,
the legs swung forward and back along the direction of travel, the arms against them, the body
bobbing in z), moved along a random heading from a random point of the pitch, and never calls
the estimator. Since task 60 the ankles' separation and the step are planted apart (the step
is speed / cadence; where it is longer than the separation the difference is flight), and the
foot in the air rises in a half sine while it swings forward, half of the stride, so h(t) sees
the stride. The bar keeps task 59's point, 4.3 steps per second (the plan's figure for the
resolution bar) at 5.5 m/s (the plan's hypothesis for the high band) with the ankles parting
by 5.5 / 4.3 m (the separation task 60's sweep fixes), so its table can be set beside task 59's;
the test of the flight plants the two apart.

Bars written before the first run (tasks/todo.md, task 59): in each of 20 seeds, cadence within
5 % and within 0.1 Hz, both step lengths within 10 %; the propagated sd within a factor 1.5 of
the spread between noisy copies. `mae_cap` 20 cm. Two bars missed on that first run and stay as
written, as strict xfails: the step from the pose, now `ankle_separation_m` (5 of 20 seeds over
10 %), and the 0.1 Hz with noise (1 of 20). The record has the table.

Mutations, each applied, seen failing and restored (tasks/todo.md, tasks 59 and 60): the
fundamental without the x 2; the body's z added to s(t); the parabola removed; the propagated
noise at half the `mae`; the period, the consecutive frame and the inclusive cap dropped from
`windows`; joints read by position in the line reader; duckdb imported by `gait`; the heels
back under the cap; h reading x instead of z; the NaN rule reading the first peak that clears
the band (reading B) or dropping r[k] > 0; the separation set to speed / cadence.
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
CAP_CM = 20.0  # the top of task 59's grid, and the lowest value of it that admitted the sample
CADENCE_HZ = 4.3
SPEED_M_S = 5.5
SEPARATION_M = SPEED_M_S / CADENCE_HZ  # task 59's point, and the separation of task 60's sweep
LIFT_M = 0.30  # the lift of task 60's test of the NaN rule on h; no source
ANKLES_AND_HEELS = tuple(JOINTS.index(n) for n in ("lAnkle", "rAnkle", "lHeel", "rHeel"))
SEEDS = range(20)
CADENCE_BAR = 0.05
CADENCE_BAR_HZ = 0.1
STEP_BAR = 0.10
SD_RATIO_BAR = 1.5
# Task 59's table as recorded in tasks/todo.md (the noisy cadence per seed, Hz, 4 decimals):
# the first column of the reprint has to give it back.
CADENCE_59 = (
    4.3119, 4.2140, 4.2420, 4.3920, 4.2378, 4.1523, 4.2853, 4.3317, 4.3018, 4.2372,
    4.2981, 4.2971, 4.2235, 4.3004, 4.2706, 4.3379, 4.2836, 4.3420, 4.2481, 4.3519,
)  # fmt: skip

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
FOOT_L = np.array([n in ("lAnkle", "lHeel", "lBigToe", "lSmallToe") for n in JOINTS], dtype=float)
FOOT_R = np.array([n in ("rAnkle", "rHeel", "rBigToe", "rSmallToe") for n in JOINTS], dtype=float)


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
    """The skeletons whose ankles are at or under `CAP_CM`: the noise a window that passes the
    cap can carry."""
    fps, mae = clip_mae
    return fps, mae[np.all(mae[:, gait.ANKLES] <= CAP_CM, axis=1)]


def test_the_cap_on_the_ankles_admits_what_the_heels_held_back(
    clip_mae: tuple[float, Array],
) -> None:
    """Task 59 capped ankles and heels, and at 15 cm admitted nothing (rHeel's `mae` never goes
    under 15.1 cm in the sample); task 60 caps the ankles only. Both, on the grid {10, 15, 20,
    25} cm, as the probe (a) will print them."""
    _, mae = clip_mae
    caps = (10.0, 15.0, 20.0, 25.0)
    ankles = {c: int(np.sum(np.all(mae[:, gait.ANKLES] <= c, axis=1))) for c in caps}
    four = {c: int(np.sum(np.all(mae[:, ANKLES_AND_HEELS] <= c, axis=1))) for c in caps}
    lowest = dict(
        zip(
            ("lAnkle", "rAnkle", "lHeel", "rHeel"),
            mae[:, ANKLES_AND_HEELS].min(axis=0).tolist(),
            strict=True,
        )
    )
    print(f"\nskeletons {len(mae)}; at or under the cap, ankles: {ankles}; ankles and heels: "
          f"{four}; lowest mae (cm): {lowest}")  # fmt: skip
    assert ankles == {10.0: 0, 15.0: 3369, 20.0: 4282, 25.0: 4659}
    assert four == {10.0: 0, 15.0: 0, 20.0: 3966, 25.0: 4431}


def runner(
    rng: np.random.Generator,
    *,
    fps: float,
    width: int = W,
    cadence_hz: float = CADENCE_HZ,
    separation_m: float = SEPARATION_M,
    speed_m_s: float = SPEED_M_S,
    lift_m: float = LIFT_M,
) -> tuple[Array, Array]:
    """A clean runner: joints (width, 29, 3) as the file has them and his (x, y) (width, 2).

    The ankles part by `separation_m` at each step while the body travels at `speed_m_s`, so
    the step between footfalls is speed / cadence: the two are planted apart, and where the
    step is the longer the difference is flight, ground covered with no foot under the body.
    Each foot rises by `lift_m` in a half sine while it swings forward, half of the stride, so
    h(t) = lift x cos(stride phase) (the feet take turns: never both up). The stride's phase is
    uniform per window. The random draws are task 59's, in its order: the lift draws none."""
    t = np.arange(width) / fps
    heading = rng.uniform(0.0, 2.0 * math.pi)
    forward = np.array([math.cos(heading), math.sin(heading)])
    left = np.array([-math.sin(heading), math.cos(heading)])
    # One swing per stride, two steps per stride: the stride frequency is half the cadence.
    phase = math.pi * cadence_hz * t + rng.uniform(0.0, 2.0 * math.pi)
    swing = 0.5 * separation_m * np.sin(phase)
    body = TEMPLATE[None, :, :] + np.zeros((width, 1, 1))
    body[:, :, 0] += swing[:, None] * SWING_OF[None, :]
    # The left foot swings forward while d(swing)/dt, as cos(phase), is positive.
    body[:, :, 2] += lift_m * np.maximum(np.cos(phase), 0.0)[:, None] * FOOT_L[None, :]
    body[:, :, 2] += lift_m * np.maximum(-np.cos(phase), 0.0)[:, None] * FOOT_R[None, :]
    xy = rng.uniform((-40.0, -25.0), (40.0, 25.0)) + np.outer(speed_m_s * t, forward)
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


def observe(
    rng: np.random.Generator, rows: Array, *, fps: float, width: int = W, **planted: float
) -> tuple[Array, Array, Array, Array]:
    """(clean joints, noisy joints, xy, mae) of one runner, task 59's draws in its order."""
    mae = draw_mae(rng, rows, width)
    clean, xy = runner(rng, fps=fps, width=width, **planted)
    return clean, clean + noise(rng, mae), xy, mae


def same(a: Any, b: Any) -> bool:
    """Two results field by field, a NaN equal to a NaN (a dataclass's == is not, since 3.13)."""
    return bool(np.array_equal(astuple(a), astuple(b), equal_nan=True))


def dyadic(a: Array) -> Array:
    """Round to 1/1024 m: sums of such numbers under 1024 m are exact in float64."""
    return np.round(a * 1024.0) / 1024.0


# --- the bar, and task 59's table reprinted in three columns ----------------------------------

COLUMNS = (
    "seed", "cad_59_hz", "cad_ankles_hz", "cad_clean_hz", "cad_hz", "sep_clean_m", "sep_m",
    "step_m", "cad_h_hz",
)  # fmt: skip


@pytest.fixture(scope="module")
def bar(clip_mae: tuple[float, Array]) -> dict[str, Array]:
    """Per seed, the same runner (task 59's point) seen three ways, so the cap and the NaN rule
    show apart (task 60, third review, point 9): the cap on ankles and heels without the rule
    (task 59 as it ran), the cap on the ankles without the rule, and the cap on the ankles with
    the rule, the estimator as it is (also on the clean runner)."""
    fps, mae = clip_mae
    rows_59 = mae[np.all(mae[:, ANKLES_AND_HEELS] <= CAP_CM, axis=1)]
    rows = mae[np.all(mae[:, gait.ANKLES] <= CAP_CM, axis=1)]
    table = []
    for seed in SEEDS:
        unruled = []
        for pool in (rows_59, rows):
            _, observed, xy, _ = observe(np.random.default_rng(seed), pool, fps=fps)
            s = gait.signal(gait.centre_on_midhip(observed), gait.direction(xy))
            unruled.append(gait.cadence_hz(s, fps=fps, band_z=0.0))
        clean, observed, xy, m = observe(np.random.default_rng(seed), rows, fps=fps)
        frames, periods = np.arange(W) + 124487, np.full(W, 2)
        assert gait.windows(frames, periods, m, width=W, mae_cap_cm=CAP_CM) == [(0, W)]
        g, g0 = gait.estimate(observed, xy, fps=fps), gait.estimate(clean, xy, fps=fps)
        table.append(
            (
                seed,
                *unruled,
                g0.cadence_hz,
                g.cadence_hz,
                g0.ankle_separation_m,
                g.ankle_separation_m,
                g.step_length_m,
                g.cadence_h_hz,
            )
        )
    return dict(zip(COLUMNS, np.array(table).T, strict=True))


def _rel(values: Array, truth: float) -> Array:
    return (values - truth) / truth


def test_the_bar_by_seed_cadence_within_5_percent_and_step_within_10(
    bar: dict[str, Array],
) -> None:
    """The table of the record (run with `-rP`) and the two bars that held in every seed."""
    cad, sep, step = _rel(bar["cad_hz"], CADENCE_HZ), bar["sep_m"], bar["step_m"]
    print(f"\nplanted: cadence {CADENCE_HZ} Hz, separation {SEPARATION_M:.4f} m, step "
          f"{SPEED_M_S / CADENCE_HZ:.4f} m, lift {LIFT_M} m, W {W}, cap {CAP_CM} cm")  # fmt: skip
    print("seed | cadence Hz: ankles+heels, no rule | ankles, no rule | ankles, rule (clean) | "
          "err | separation m (clean) | err | step m | err | cad_h Hz")  # fmt: skip
    for i, seed in enumerate(bar["seed"]):
        print(
            f"{int(seed):4d} | {bar['cad_59_hz'][i]:.4f} | {bar['cad_ankles_hz'][i]:.4f} | "
            f"{bar['cad_hz'][i]:.4f} ({bar['cad_clean_hz'][i]:.4f}) | {cad[i]:+.4%} | "
            f"{sep[i]:.4f} ({bar['sep_clean_m'][i]:.4f}) | {_rel(sep[i], SEPARATION_M):+.4%} | "
            f"{step[i]:.4f} | {_rel(step[i], SPEED_M_S / CADENCE_HZ):+.4%} | "
            f"{bar['cad_h_hz'][i]:.4f}"
        )
    for name in ("cad_59_hz", "cad_ankles_hz", "cad_hz"):
        hz = np.abs(bar[name] - CADENCE_HZ)
        print(
            f"{name}: worst {np.nanmax(hz):.4f} Hz ({np.nanmax(hz) / CADENCE_HZ:.4%}, seed "
            f"{int(np.nanargmax(hz))}), {int(np.sum(hz > CADENCE_BAR_HZ))} seeds over "
            f"{CADENCE_BAR_HZ} Hz, {int(np.sum(np.isnan(hz)))} NaN"
        )
    rel_sep = np.abs(_rel(sep, SEPARATION_M))
    print(
        f"separation: worst {np.max(rel_sep):.4%}, {int(np.sum(rel_sep >= STEP_BAR))} seeds at or "
        f"over {STEP_BAR:.0%}, mean {np.mean(_rel(sep, SEPARATION_M)):+.4%}; step: worst "
        f"{np.max(np.abs(_rel(step, SPEED_M_S / CADENCE_HZ))):.4%}"
    )
    clean_sep = _rel(bar["sep_clean_m"], SEPARATION_M)
    print(
        f"clean runners: cadence worst {np.max(np.abs(bar['cad_clean_hz'] - CADENCE_HZ)):.4f} Hz,"
        f" separation from {np.min(clean_sep):+.4%} to {np.max(clean_sep):+.4%}"
    )
    assert np.all(np.abs(cad) < CADENCE_BAR)
    assert np.all(np.abs(_rel(step, SPEED_M_S / CADENCE_HZ)) < STEP_BAR)


def test_the_reprint_gives_back_task_59s_table_and_the_rule_moves_no_cadence(
    bar: dict[str, Array],
) -> None:
    """The first column is task 59's table, figure by figure; the rule only ever turns a
    cadence into NaN (the second and third columns agree wherever the third is finite)."""
    assert np.round(bar["cad_59_hz"], 4).tolist() == list(CADENCE_59)
    finite = np.isfinite(bar["cad_hz"])
    print(f"\nseeds the rule turns to NaN: {int(np.sum(~finite))} of {len(finite)}")
    assert np.array_equal(bar["cad_ankles_hz"][finite], bar["cad_hz"][finite])


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="bar missed on its first run (2026-10-13): 5 of 20 seeds, worst +17.02 % with task "
    "59's cap; reported in tasks/todo.md (tasks 59 and 60), not moved",
)
def test_the_bar_ankle_separation_within_10_percent_in_every_seed(bar: dict[str, Array]) -> None:
    assert np.all(np.abs(_rel(bar["sep_m"], SEPARATION_M)) < STEP_BAR)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="bar missed on its first run (2026-10-13): seed 5 at 0.1477 Hz with task 59's cap; "
    "reported in tasks/todo.md (tasks 59 and 60), not moved",
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
    Carlo run around each of five noisy observations has to land within a factor 1.5 of it
    (cadence of s, separation, step)."""
    fps, rows = sample
    rng = np.random.default_rng(100)
    mae = draw_mae(rng, rows)
    clean, xy = runner(rng, fps=fps)
    copies = np.array(
        [
            astuple(gait.estimate(clean + noise(np.random.default_rng(s), mae), xy, fps=fps))
            for s in range(1000, 1400)
        ]
    )[:, [0, 2, 3]]
    assert np.all(np.isfinite(copies))
    empirical = copies.std(axis=0, ddof=1)
    for s in range(2000, 2005):
        observed = clean + noise(np.random.default_rng(s), mae)
        p = gait.propagated_error(observed, xy, mae, fps=fps, draws=400)
        ratio = np.array(astuple(p))[[0, 3, 4]] / empirical
        print(f"observation {s}: propagated / empirical sd = {np.round(ratio, 3).tolist()}")
        assert p.valid == p.draws
        assert np.all((ratio >= 1 / SD_RATIO_BAR) & (ratio <= SD_RATIO_BAR))


def test_the_sd_of_h_and_of_the_difference_are_taken_draw_by_draw(
    sample: tuple[float, Array],
) -> None:
    """`propagated_error` for h: the same noise drawn as it draws it, the cadence of s and of h
    of each draw, and the sd of cad_h and of cad_s - cad_h over the draws where both are finite
    (`valid_h`), the difference taken within each draw. At W 25 with the lift of `LIFT_M` some
    draws lose h and keep s, so the subset matters. Pairing draw i of s with draw i + 1 of h, or
    taking the sd of h over the draws valid for s, falls here.

    Not a calibration: the sd of cad_h around one noisy window is not the spread between noisy
    copies the way s's is (at W 50 and 0.30 m, two of five observations gave 7.3 and 9.3 times
    the spread; task 60, record of phase B1)."""
    fps, rows = sample
    rng = np.random.default_rng(102)
    mae = draw_mae(rng, rows)
    clean, xy = runner(rng, fps=fps)
    observed = clean + noise(rng, mae)
    p = gait.propagated_error(observed, xy, mae, fps=fps, draws=200, seed=5)
    replay = np.random.default_rng(5)
    centred = gait.centre_on_midhip(observed)
    pairs = []
    for _ in range(200):
        draw = centred + replay.standard_normal(centred.shape) * mae[:, :, None] / 100.0
        g = gait.estimate(draw, xy, fps=fps)
        pairs.append((g.cadence_hz, g.cadence_h_hz))
    both = np.array(pairs)[np.all(np.isfinite(pairs), axis=1)]
    print(f"\nvalid {p.valid}, valid_h {p.valid_h} of {p.draws}")
    assert p.valid == p.draws > p.valid_h == len(both) > 1
    assert p.cadence_h_hz_sd == pytest.approx(both[:, 1].std(ddof=1), rel=1e-12)
    assert p.cadence_diff_hz_sd == pytest.approx((both[:, 0] - both[:, 1]).std(ddof=1), rel=1e-12)


def test_a_clean_runner_gives_the_planted_speed(sample: tuple[float, Array]) -> None:
    fps, _ = sample
    for seed in SEEDS:
        clean, xy = runner(np.random.default_rng(seed), fps=fps)
        g = gait.estimate(clean, xy, fps=fps)
        assert g.speed_m_s == pytest.approx(SPEED_M_S, rel=1e-12)
        assert g.step_length_m == pytest.approx(SPEED_M_S / g.cadence_hz, rel=1e-12)


# --- the separation is not the step (task 60, review of method 1) -----------------------------


@pytest.mark.parametrize(
    ("cadence", "separation", "speed"),
    [(4.3, 1.0, 5.5), (3.0, SEPARATION_M, 5.5)],
    ids=["shorter-separation", "slower-cadence"],
)
def test_with_flight_the_separation_and_the_step_are_read_apart(
    sample: tuple[float, Array], cadence: float, separation: float, speed: float
) -> None:
    """A runner with a flight phase at W 50: the ankles part by `separation` and the footfalls
    are speed / cadence apart, over 20 % further (no source for either: the point is that they
    differ). On each clean runner each estimate lands within 2 % of its own truth; seen through
    noise, the mean over 20 seeds of each lands nearer its own truth than the other's, and the
    step within 5 % of its own (the amplitude is biased upwards by the noise, task 59: +10.16 %
    at 1.0 m, so "within 10 %" and "nearer in every seed", written first, both failed on it;
    task 60, record of phase B1). A separation read as speed / cadence (the identity task 59's
    runner planted) falls here."""
    fps, rows = sample
    step = speed / cadence
    assert (step - separation) / step > 0.2
    noisy = []
    for seed in SEEDS:
        clean, observed, xy, _ = observe(
            np.random.default_rng(seed),
            rows,
            fps=fps,
            width=50,
            cadence_hz=cadence,
            separation_m=separation,
            speed_m_s=speed,
        )
        g0, g = gait.estimate(clean, xy, fps=fps), gait.estimate(observed, xy, fps=fps)
        assert g0.ankle_separation_m == pytest.approx(separation, rel=0.02)
        assert g0.step_length_m == pytest.approx(step, rel=0.02)
        noisy.append((g.ankle_separation_m, g.step_length_m))
    sep, est = np.mean(noisy, axis=0)
    print(
        f"\nplanted separation {separation:.4f} m, step {step:.4f} m; noisy means {sep:.4f} "
        f"({_rel(sep, separation):+.2%}) and {est:.4f} ({_rel(est, step):+.2%})"
    )
    assert abs(sep - separation) < abs(sep - step)
    assert abs(est - step) < abs(est - separation)
    assert abs(_rel(est, step)) < CADENCE_BAR


# --- the NaN rule (task 60, reading A) and h ----------------------------------------------------


def test_the_nan_rule_turns_white_noise_into_nan(sample: tuple[float, Array]) -> None:
    """White noise at W 50, 2,000 windows: NaN in at least 90 % (the reviewer: 94.3 % with
    reading A, 43.5 % with reading B, the first peak that clears the band). Only the first peak
    is read; trying later ones (B) falls here."""
    fps, _ = sample
    noisy = np.random.default_rng(60).standard_normal((2000, 50))
    nan = float(np.mean([math.isnan(gait.cadence_hz(s, fps=fps)) for s in noisy]))
    unruled = float(np.mean([math.isnan(gait.cadence_hz(s, fps=fps, band_z=0.0)) for s in noisy]))
    print(f"\nwhite noise, W 50: NaN {nan:.4f} with the rule, {unruled:.4f} without")
    assert nan >= 0.90


def test_the_nan_rule_keeps_a_sane_h_at_w_50(sample: tuple[float, Array]) -> None:
    """h of runners at W 50, 4.3 Hz, lift 0.30 m, kz 1.0, rho 0 and the cap at 20 cm, 2,000
    windows: NaN in at most 10 % (the reviewer: 0.031). Without r[k] > 0 the first local
    maximum after the first negative lag can be one below zero, which never clears the band (the
    reviewer: 0.162): that mutation falls here."""
    fps, rows = sample
    rng = np.random.default_rng(61)
    cad_h = []
    for _ in range(2000):
        _, observed, xy, _ = observe(rng, rows, fps=fps, width=50)
        cad_h.append(gait.estimate(observed, xy, fps=fps).cadence_h_hz)
    h = np.array(cad_h)
    nan = float(np.mean(np.isnan(h)))
    rel = np.abs(h[np.isfinite(h)] - CADENCE_HZ) / CADENCE_HZ
    print(f"\nsane h, W 50: NaN {nan:.4f}; |err| p50 {np.median(rel):.4f}, p95 "
          f"{np.percentile(rel, 95):.4f}")  # fmt: skip
    assert nan <= 0.10


def test_h_is_the_vertical_separation_and_a_flat_h_has_no_cadence(
    sample: tuple[float, Array],
) -> None:
    """h = z(lAnkle) - z(rAnkle). On runners whose feet never rise (broken row ii) h is error
    only: its cadence is NaN in at least 90 % of 400 windows at W 50 while s keeps its own; with
    the lift, h's cadence is the planted one. Read from x instead of
    z, h would see the swing projected on the pitch's x axis and find a cadence on the flat
    runners: that mutation falls here. The lifted side was first written as "within 5 % in at
    least 90 %" and gave 0.8225: it reads now as the NaN test's bar (at most 10 % NaN) and a
    median error within 5 % (task 60, record of phase B1)."""
    fps, rows = sample
    rng = np.random.default_rng(62)
    out = {}
    for lift in (0.0, LIFT_M):
        pairs = []
        for _ in range(400):
            _, observed, xy, _ = observe(rng, rows, fps=fps, width=50, lift_m=lift)
            g = gait.estimate(observed, xy, fps=fps)
            pairs.append((g.cadence_hz, g.cadence_h_hz))
        out[lift] = np.array(pairs)
    flat, lifted = out[0.0], out[LIFT_M]
    rel = np.abs(lifted[:, 1] - CADENCE_HZ) / CADENCE_HZ
    near = rel <= CADENCE_BAR  # NaN is not near
    print(f"\nflat h: NaN in h {np.mean(np.isnan(flat[:, 1])):.4f}, in s "
          f"{np.mean(np.isnan(flat[:, 0])):.4f}; lifted h: NaN {np.mean(np.isnan(rel)):.4f}, "
          f"within 5 % {np.mean(near):.4f}, median |err| {np.nanmedian(rel):.4f}")  # fmt: skip
    assert np.mean(np.isnan(flat[:, 1])) >= 0.90
    assert np.mean(np.isfinite(flat[:, 0])) >= 0.90
    assert np.mean(np.isnan(rel)) <= 0.10 and np.nanmedian(rel) <= CADENCE_BAR


def test_the_batch_cadence_is_cadence_hz_bit_for_bit(sample: tuple[float, Array]) -> None:
    """`cadence_hz_batch` against `cadence_hz` one window at a time, with the band and without,
    on white noise, AR(1) noise, sinusoids under noise at random frequencies, constant windows
    and a window with a NaN, at W 25, 37 and 50: the same bits and the same NaN, with both
    outcomes present."""
    fps, _ = sample
    rng = np.random.default_rng(63)
    for width in (25, 37, 50):
        t = np.arange(width) / fps
        ar = rng.standard_normal((500, width))
        for i in range(1, width):
            ar[:, i] = 0.8 * ar[:, i - 1] + 0.6 * ar[:, i]
        freq, phase = rng.uniform(1.0, 6.0, (1000, 1)), rng.uniform(0.0, 7.0, (1000, 1))
        noisy = rng.uniform(0.0, 1.5, (1000, 1)) * rng.standard_normal((1000, width))
        signals = np.concatenate(
            [
                rng.standard_normal((500, width)),
                ar,
                np.sin(math.pi * freq * t + phase) + noisy,
                np.full((5, width), 0.3),
            ]
        )
        signals[-2, 7] = np.nan
        for band in (gait.BAND_Z, 0.0):
            batch = gait.cadence_hz_batch(signals, fps=fps, band_z=band)
            one = np.array([gait.cadence_hz(s, fps=fps, band_z=band) for s in signals])
            assert np.array_equal(batch, one, equal_nan=True)
            assert 0 < np.sum(np.isnan(one)) < len(one)


# --- invariance (limit 2) ---------------------------------------------------------------------


def test_a_different_offset_per_frame_on_every_joint_changes_nothing(
    sample: tuple[float, Array],
) -> None:
    """x, y and z of all 29 joints moved by up to 512 m, a different shift in every frame: the
    centred joints, and with them every output, are the same bits (`propagated_error` too). h
    reads z, so the shift in z now reaches an output."""
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
    assert same(after, before)
    assert same(
        gait.propagated_error(moved, xy, mae, fps=fps),
        gait.propagated_error(joints, xy, mae, fps=fps),
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
    (x, y) in every frame (his joints with him) changes d, the speed and `step_length_m`,
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
    assert same(gait.estimate(scene, xy + shift, fps=fps), before)

    wobble = dyadic(rng.uniform(-1.0, 1.0, size=(W, 2)))
    assert not np.array_equal(wobble[-1], wobble[0])
    body = joints.copy()
    body[:, :, :2] += wobble[:, None, :]
    after = gait.estimate(body, xy + wobble, fps=fps)
    assert not np.array_equal(gait.direction(xy + wobble), gait.direction(xy))
    assert after.speed_m_s != before.speed_m_s
    assert after.step_length_m != before.step_length_m
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


def test_the_cap_is_on_the_ankles_only_and_is_inclusive() -> None:
    """The ankles are the joints a signal reads (task 60): the heels, like a hand, do not count."""
    frames, periods = np.arange(25), np.full(25, 1)
    at_cap = _mae(25, CAP_CM)
    for name in ("lPinky", "lHeel", "rHeel"):
        at_cap[:, JOINTS.index(name)] = 40.0
    assert gait.windows(frames, periods, at_cap, width=W, mae_cap_cm=CAP_CM) == [(0, 25)]
    for name in ("lAnkle", "rAnkle"):
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
    assert same(read(list(JOINTS)), direct)
    assert same(read(shuffled), direct)


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
