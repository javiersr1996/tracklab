"""Stride kinematics of one player from his body pose: cadence and step length (task 59 of
tasks/todo.md, P6; revised in phase B1 of task 60).

Pure functions over numpy arrays. Nothing here opens a file, a path or a database (a test reads
this module's imports): the caller hands over one player's frames as `bronze` stores them.

* `windows`: stretches of `width` consecutive frames inside one period, every frame with joints
  and the predicted error of both ankles at or under `mae_cap_cm`. The cap is on the joints a
  signal reads and on no other (task 60: the heels read nothing and were the `mae` that bound).
  A frame without joints carries NaN as its `mae` (or is absent, which breaks the run): it never
  makes a window. Windows tile each stretch from its start and never overlap.
* `signal`: s(t) = (lAnkle - rAnkle) . d, with d the unit direction of the player's (x, y)
  displacement over the window (the file's own x, y, never the tracking's). `signal_h`: h(t) =
  z(lAnkle) - z(rAnkle), the same two ankles' vertical separation in the same frame (the foot
  in the air rises and falls once per stride, the same x 2 as s). The joints are centred on
  midHip first (`centre_on_midhip`): only differences between joints of the same body and frame
  survive, so no absolute height and no position of the body enters (limit 2 of the README).
* `cadence_hz`: steps per second = 2 x the fundamental of a signal (it swings once per stride,
  and a stride is two steps), read from the first peak of its autocorrelation after it turns
  negative, refined by a parabola through the peak and its two neighbours (finer than a frame);
  NaN when that first peak is not above white noise's band (task 60, reading A).
  `cadence_hz_batch` is the same function over many windows at once, bit for bit.
* `ankle_separation_m`: the amplitude of s(t), the mean of the maxima of |s|, one per step.
  It is not a step length: with a flight phase the ground covered between two footfalls
  includes what the body travels with both feet in the air, which no separation measured inside
  the body sees (task 60, review of method 1). `step_length_m`: the window's mean speed (net
  displacement of x, y over its duration) divided by the cadence of s, the only step length.
* `propagated_error`: Monte Carlo with a fixed seed; every joint of every frame gets gaussian
  noise whose sd is its `p90_mae_cm` (the conservative reading: a p90 taken as an sd), and the
  sd of each estimate over the draws is returned, with the sd of cad_s - cad_h taken draw by
  draw. The x, y of the file carry no predicted error, so none is added to them. The seed may
  be a sequence: on data every window gets its own, `window_seed` (phase B1's record: one seed
  for all would repeat draw k's noise in every window). `monte_carlo` returns the draws
  themselves, which M2 resamples, and `summarise` turns them into the sds.
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
ANKLES = (L_ANKLE, R_ANKLE)
BAND_Z = 1.96  # the two-sided 95 % normal quantile of the white-noise band of `cadence_hz`
DRAWS = 200
SEED = 59

Array = NDArray[np.float64]


@dataclass(frozen=True)
class Gait:
    """What one window says. NaN where it cannot say: no displacement, no resolved
    autocorrelation peak, no whole step inside the window. `cadence_hz` is the cadence of s(t),
    the instrument; `cadence_h_hz` that of h(t), its consistency check."""

    cadence_hz: float
    cadence_h_hz: float
    ankle_separation_m: float
    step_length_m: float
    speed_m_s: float


@dataclass(frozen=True)
class PropagatedError:
    """The sd of each estimate over `draws` noisy copies of the window. `valid` draws gave a
    finite cadence of s, separation and step (the sd of those three is over them); `valid_h`
    gave a finite cadence of s and of h (the sd of cad_h and of cad_s - cad_h is over them)."""

    cadence_hz_sd: float
    cadence_h_hz_sd: float
    cadence_diff_hz_sd: float
    ankle_separation_m_sd: float
    step_length_m_sd: float
    draws: int
    valid: int
    valid_h: int


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
    eligible = np.all(mae[:, ANKLES] <= mae_cap_cm, axis=1)  # NaN, no joints: never eligible
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


def signal_h(centred: Array) -> Array:
    """h(t): the ankles' vertical separation, z(lAnkle) - z(rAnkle), in metres."""
    return centred[:, L_ANKLE, 2] - centred[:, R_ANKLE, 2]


def cadence_hz(s: Array, *, fps: float, band_z: float = BAND_Z) -> float:
    """Steps per second: 2 x fps / (lag of the autocorrelation's first peak, in frames).

    The first peak is the first local maximum with r[k] > 0 after the first r[k] < 0, and only
    that one is read (reading A of task 60): if it is not resolved, the cadence is NaN and no
    later peak is tried. Resolved means r[k] / r[0] above `band_z` / sqrt(n - k), the band in
    which white noise keeps its sample autocorrelation 95 % of the time. Source of the band, read
    on 2026-10-14: the statsmodels documentation of `tsa.stattools.acf` gives, for white noise,
    a standard error of 1/sqrt(N) at every lag and cites Brockwell and Davis (1987), "Time Series:
    Theory and Methods", sections 7.2 (Bartlett's formula) and 9.4; the NIST/SEMATECH
    e-Handbook of Statistical Methods, section 1.3.3.1 (Autocorrelation Plot), gives the band
    +-z(1 - alpha/2) / sqrt(N). Brockwell and Davis themselves were not read: PENDIENTE DE
    CONFIRMAR. Here every lag is averaged over its own n - k products, not divided by N, so the
    band uses n - k (under white noise those products are uncorrelated, so their mean has a
    variance of about r[0]^2 / (n - k)): that step is the protocol's, not the sources'. `band_z`
    = 0 turns the rule off (the reprint of task 59's table without it)."""
    n = len(s)
    if n < 4 or not np.all(np.isfinite(s)):
        return math.nan
    s0 = s - s.mean()
    # Each lag averaged over its own overlap: dividing by n would drag the peak to shorter lags.
    # Lag by lag, product then sum, the very additions `cadence_hz_batch` repeats.
    r = np.array([np.sum(s0[: n - k] * s0[k:]) for k in range(n)]) / (n - np.arange(n))
    if not r[0] > 0:
        return math.nan
    negative = np.flatnonzero(r < 0)
    if negative.size == 0:
        return math.nan
    for k in range(int(negative[0]) + 1, n - 1):
        if r[k] > 0 and r[k] > r[k - 1] and r[k] >= r[k + 1]:
            if r[k] / r[0] <= band_z / math.sqrt(n - k):
                return math.nan
            curvature = r[k - 1] - 2.0 * r[k] + r[k + 1]
            shift = 0.5 * (r[k - 1] - r[k + 1]) / curvature if curvature < 0 else 0.0
            return 2.0 * fps / (k + shift)
    return math.nan


def cadence_hz_batch(s: ArrayLike, *, fps: float, band_z: float = BAND_Z) -> Array:
    """`cadence_hz` of every row of `s` (windows, frames), with the same additions in the same
    order, so the same bits (a test crosses them), and no Python loop over the windows: task
    60's sweep runs millions of them."""
    # Row by row in memory: in Fortran order the sums would run in another order (other bits).
    s = np.ascontiguousarray(s, dtype=np.float64)
    b, n = s.shape
    out = np.full(b, np.nan)
    if n < 4 or b == 0:
        return out
    s0 = s - s.mean(axis=1, keepdims=True)
    r = np.empty((b, n))
    for lag in range(n):
        r[:, lag] = np.sum(s0[:, : n - lag] * s0[:, lag:], axis=1)
    r = r / (n - np.arange(n))
    usable = np.all(np.isfinite(s), axis=1) & (r[:, 0] > 0)
    negative = r < 0
    first_negative = np.where(negative.any(axis=1), negative.argmax(axis=1), n)
    peak = np.zeros((b, n), dtype=bool)
    mid = r[:, 1:-1]
    peak[:, 1:-1] = (mid > 0) & (mid > r[:, :-2]) & (mid >= r[:, 2:])
    peak &= np.arange(n) > first_negative[:, None]
    rows = np.flatnonzero(usable & peak.any(axis=1))
    k = peak[rows].argmax(axis=1)
    rk, before, after, r0 = r[rows, k], r[rows, k - 1], r[rows, k + 1], r[rows, 0]
    resolved = ~(rk / r0 <= band_z / np.sqrt(n - k))
    curvature = before - 2.0 * rk + after
    with np.errstate(divide="ignore", invalid="ignore"):
        shift = np.where(curvature < 0, 0.5 * (before - after) / curvature, 0.0)
    out[rows] = np.where(resolved, 2.0 * fps / (k + shift), np.nan)
    return out


def ankle_separation_m(s: Array, cadence: float, *, fps: float) -> float:
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


def step_length_m(xy: Array, cadence: float, *, fps: float) -> float:
    return mean_speed_m_s(xy, fps=fps) / cadence


def estimate(joints: Array, xy: Array, *, fps: float) -> Gait:
    """One window: `joints` (frames, 29, 3) in metres as the file has them (x, y on the pitch,
    z relative to the centroid), `xy` (frames, 2) the player's x, y from the same file."""
    centred = centre_on_midhip(joints)
    s = signal(centred, direction(xy))
    cadence = cadence_hz(s, fps=fps)
    return Gait(
        cadence,
        cadence_hz(signal_h(centred), fps=fps),
        ankle_separation_m(s, cadence, fps=fps),
        step_length_m(xy, cadence, fps=fps),
        mean_speed_m_s(xy, fps=fps),
    )


def _sd(values: Array) -> Array:
    return values.std(axis=0, ddof=1) if len(values) > 1 else np.full(values.shape[1], np.nan)


def window_seed(match_id: int, player_id: int, frame: int) -> list[int]:
    """The seed of one window's Monte Carlo on data: `SEED`, the match, the player and the
    window's first frame (the protocol's design.monte_carlo.seed_per_window)."""
    return [SEED, match_id, player_id, frame]


def monte_carlo(
    joints: Array,
    xy: Array,
    mae_cm: Array,
    *,
    fps: float,
    draws: int = DRAWS,
    seed: int | list[int] = SEED,
) -> Array:
    """(draws, 4): cad_s, separation, step and cad_h of `estimate` when each joint of each frame
    moves by N(0, its `mae`) per axis. Noise is added to the centred joints and `estimate`
    centres again on the noisy midHip, which is the same as adding it to the joints as the file
    has them."""
    rng = np.random.default_rng(seed)
    centred = centre_on_midhip(joints)
    sd_m = np.asarray(mae_cm, dtype=np.float64)[:, :, None] / 100.0
    values = np.empty((draws, 4))
    for i in range(draws):
        g = estimate(centred + rng.standard_normal(centred.shape) * sd_m, xy, fps=fps)
        values[i] = (g.cadence_hz, g.ankle_separation_m, g.step_length_m, g.cadence_h_hz)
    return values


def propagated_error(
    joints: Array,
    xy: Array,
    mae_cm: Array,
    *,
    fps: float,
    draws: int = DRAWS,
    seed: int | list[int] = SEED,
) -> PropagatedError:
    """The sd of `estimate` over `monte_carlo`'s draws."""
    return summarise(monte_carlo(joints, xy, mae_cm, fps=fps, draws=draws, seed=seed))


def summarise(values: Array) -> PropagatedError:
    """The sds of `monte_carlo`'s draws: of cad_s, separation and step over the draws with the
    three finite; of cad_h and cad_s - cad_h over those with both cadences finite."""
    draws = len(values)
    with_s = values[np.all(np.isfinite(values[:, :3]), axis=1)]
    with_h = values[np.isfinite(values[:, 0]) & np.isfinite(values[:, 3])]
    cad, sep, step = _sd(with_s[:, :3])
    cad_h, diff = _sd(np.c_[with_h[:, 3], with_h[:, 0] - with_h[:, 3]])
    return PropagatedError(
        float(cad),
        float(cad_h),
        float(diff),
        float(sep),
        float(step),
        draws,
        len(with_s),
        len(with_h),
    )
