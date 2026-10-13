"""Stride kinematics of one player from his body pose: cadence and step length (task 59 of
tasks/todo.md, P6).

Pure functions over numpy arrays. Nothing here opens a file, a path or a database (a test reads
this module's imports): the caller hands over one player's frames as `bronze` stores them.

* `windows`: stretches of `width` consecutive frames inside one period, every frame with joints
  and the predicted error of both ankles and both heels at or under `mae_cap_cm`. A frame
  without joints carries NaN as its `mae` (or is absent, which breaks the run): it never makes
  a window. Windows tile each stretch from its start and never overlap.
* `signal`: s(t) = (lAnkle - rAnkle) . d, with d the unit direction of the player's (x, y)
  displacement over the window (the file's own x, y, never the tracking's). The joints are
  centred on midHip first (`centre_on_midhip`): only differences between joints of the same
  body and frame survive, so no absolute height and no position of the body enters (limit 2 of
  the README).
* `cadence_hz`: steps per second = 2 x the fundamental of s(t) (s swings once per stride, and a
  stride is two steps), read from the first peak of its autocorrelation after it turns
  negative, refined by a parabola through the peak and its two neighbours (finer than a frame).
* `step_length_pose_m`: the mean of the maxima of |s(t)|, one per step (|s| peaks once per
  step, with the left foot ahead and then the right); `step_length_speed_m`: the window's mean
  speed (net displacement of x, y over its duration) divided by the cadence. Two roads to the
  same step, which task 60 compares.
* `propagated_error`: Monte Carlo with a fixed seed; every joint of every frame gets gaussian
  noise whose sd is its `p90_mae_cm` (the conservative reading: a p90 taken as an sd), and the
  sd of each estimate over the draws is returned. The x, y of the file carry no predicted
  error, so none is added to them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from tracklab.pose.jsonl import JOINTS

MIDHIP = JOINTS.index("midHip")
L_ANKLE = JOINTS.index("lAnkle")
R_ANKLE = JOINTS.index("rAnkle")
FOOT = tuple(JOINTS.index(n) for n in ("lAnkle", "rAnkle", "lHeel", "rHeel"))
DRAWS = 200
SEED = 59

Array = NDArray[np.float64]


@dataclass(frozen=True)
class Gait:
    """What one window says. NaN where it cannot say: no displacement, no autocorrelation peak,
    no whole step inside the window."""

    cadence_hz: float
    step_length_pose_m: float
    step_length_speed_m: float
    speed_m_s: float


@dataclass(frozen=True)
class PropagatedError:
    """The sd of each estimate over `draws` noisy copies of the window; `valid` draws gave a
    finite value of all three."""

    cadence_hz_sd: float
    step_length_pose_m_sd: float
    step_length_speed_m_sd: float
    draws: int
    valid: int


def windows(
    frames: ArrayLike,
    periods: ArrayLike,
    mae_cm: ArrayLike,
    *,
    width: int,
    mae_cap_cm: float,
) -> list[tuple[int, int]]:
    """`[start, stop)` indices into one player's rows (sorted by frame) of every window."""
    f = np.asarray(frames, dtype=np.int64)
    p = np.asarray(periods)
    mae = np.asarray(mae_cm, dtype=np.float64)
    if f.ndim != 1 or np.any(np.diff(f) <= 0):
        raise ValueError("frames must be one player's, strictly increasing")
    eligible = np.all(mae[:, FOOT] <= mae_cap_cm, axis=1)  # NaN, no joints: never eligible
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i in range(len(f)):
        if not eligible[i]:
            start = None
            continue
        if start is None or f[i] != f[i - 1] + 1 or p[i] != p[i - 1]:
            start = i
        if (i + 1 - start) % width == 0:
            out.append((i + 1 - width, i + 1))
    return out


def centre_on_midhip(joints: Array) -> Array:
    """(frames, 29, 3) joints minus each frame's midHip."""
    return joints - joints[:, MIDHIP : MIDHIP + 1, :]


def direction(xy: Array) -> Array:
    """Unit vector of the (x, y) displacement from the first frame to the last (NaN if none)."""
    delta = xy[-1] - xy[0]
    norm = math.hypot(float(delta[0]), float(delta[1]))
    return delta / norm if norm > 0 else np.full(2, np.nan)


def signal(centred: Array, d: Array) -> Array:
    """s(t): the ankles' separation along the direction of travel, in metres."""
    return (centred[:, L_ANKLE, :2] - centred[:, R_ANKLE, :2]) @ d


def cadence_hz(s: Array, *, fps: float) -> float:
    """Steps per second: 2 x fps / (lag of the autocorrelation's first peak, in frames)."""
    n = len(s)
    if n < 4 or not np.all(np.isfinite(s)):
        return math.nan
    s0 = s - s.mean()
    # Each lag averaged over its own overlap: dividing by n would drag the peak to shorter lags.
    r = np.correlate(s0, s0, mode="full")[n - 1 :] / (n - np.arange(n))
    if not r[0] > 0:
        return math.nan
    negative = np.flatnonzero(r < 0)
    if negative.size == 0:
        return math.nan
    for k in range(int(negative[0]) + 1, n - 1):
        if r[k] > 0 and r[k] > r[k - 1] and r[k] >= r[k + 1]:
            curvature = r[k - 1] - 2.0 * r[k] + r[k + 1]
            shift = 0.5 * (r[k - 1] - r[k + 1]) / curvature if curvature < 0 else 0.0
            return 2.0 * fps / (k + shift)
    return math.nan


def step_length_pose_m(s: Array, cadence: float, *, fps: float) -> float:
    """Mean of the maxima of |s|, one per step: a sample that is the largest within half a
    step on either side, the whole half step inside the window (a step cut by the window's
    edge would count short)."""
    if not (math.isfinite(cadence) and cadence > 0) or not np.all(np.isfinite(s)):
        return math.nan
    a = np.abs(s)
    half = max(1, round(fps / cadence / 2))
    peaks = [a[i] for i in range(half, len(a) - half) if a[i] == a[i - half : i + half + 1].max()]
    return float(np.mean(peaks)) if peaks else math.nan


def mean_speed_m_s(xy: Array, *, fps: float) -> float:
    """Net (x, y) displacement over the window's duration, (frames - 1) / fps."""
    delta = xy[-1] - xy[0]
    return math.hypot(float(delta[0]), float(delta[1])) * fps / (len(xy) - 1)


def step_length_speed_m(xy: Array, cadence: float, *, fps: float) -> float:
    return mean_speed_m_s(xy, fps=fps) / cadence


def estimate(joints: Array, xy: Array, *, fps: float) -> Gait:
    """One window: `joints` (frames, 29, 3) in metres as the file has them (x, y on the pitch,
    z relative to the centroid), `xy` (frames, 2) the player's x, y from the same file."""
    s = signal(centre_on_midhip(joints), direction(xy))
    cadence = cadence_hz(s, fps=fps)
    return Gait(
        cadence,
        step_length_pose_m(s, cadence, fps=fps),
        step_length_speed_m(xy, cadence, fps=fps),
        mean_speed_m_s(xy, fps=fps),
    )


def propagated_error(
    joints: Array,
    xy: Array,
    mae_cm: Array,
    *,
    fps: float,
    draws: int = DRAWS,
    seed: int = SEED,
) -> PropagatedError:
    """The sd of `estimate` when each joint of each frame moves by N(0, its `mae`) per axis.
    Noise is added to the centred joints and `estimate` centres again on the noisy midHip,
    which is the same as adding it to the joints as the file has them."""
    rng = np.random.default_rng(seed)
    centred = centre_on_midhip(joints)
    sd_m = np.asarray(mae_cm, dtype=np.float64)[:, :, None] / 100.0
    values = np.empty((draws, 3))
    for i in range(draws):
        g = estimate(centred + rng.standard_normal(centred.shape) * sd_m, xy, fps=fps)
        values[i] = (g.cadence_hz, g.step_length_pose_m, g.step_length_speed_m)
    finite = values[np.all(np.isfinite(values), axis=1)]
    sds = finite.std(axis=0, ddof=1) if len(finite) > 1 else np.full(3, np.nan)
    return PropagatedError(float(sds[0]), float(sds[1]), float(sds[2]), draws, len(finite))
