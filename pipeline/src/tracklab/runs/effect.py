"""The instrument of P5 as pure functions (task 48).

Everything here is arithmetic on positions in the attack frame (`+x` is the runner's team's
goal direction, metres) and nothing else: no files, no match, no split. The definitions come
from `reports/runs_protocol.json` (written by `protocol.py`) and the windows are the
protocol's constants, passed in by the caller.

* the run direction `d`: unit vector from the runner's tracked position at `frame_start` to
  his position at `frame_end`; shorter than the protocol's minimum, no direction;
* the marker: the opponent nearest to the runner at `t_c`, goalkeeper included;
* the marker displacement: projection on `d` of `[p(t_c + W) - p(t_c)] - v(t_c) * W`, with
  `v(t_c) = [p(t_c) - p(t_c - V)] / V`; positive means the marker moved with the run;
* the line height: mean `x_att` of the two deepest outfield opponents; the same residual;
  positive means the line dropped towards its own goal.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


def run_direction(start_xy: Array, end_xy: Array, min_length_m: float) -> Array | None:
    """Unit vector from `start_xy` to `end_xy`, or None when the run is shorter than
    `min_length_m` (or either end is missing)."""
    delta = np.asarray(end_xy, dtype=np.float64) - np.asarray(start_xy, dtype=np.float64)
    length = float(np.hypot(delta[0], delta[1]))
    if not math.isfinite(length) or length < min_length_m:
        return None
    unit: Array = delta / length
    return unit


def nearest_opponent(runner_xy: Array, opponents_xy: Array) -> int | None:
    """Index of the opponent nearest to the runner, ties to the lowest index. Rows with a
    missing coordinate never win; None when no opponent has a position."""
    gap = np.hypot(
        opponents_xy[:, 0] - runner_xy[0],
        opponents_xy[:, 1] - runner_xy[1],
    )
    if not np.isfinite(gap).any():
        return None
    return int(np.nanargmin(gap))


def residual_displacement(
    before_xy: Array, at_xy: Array, after_xy: Array, *, window_s: float, velocity_s: float
) -> Array:
    """`[p(t + W) - p(t)] - v(t) * W` with `v(t) = [p(t) - p(t - V)] / V`: the displacement
    over the window beyond what the velocity just before already predicted."""
    velocity = (at_xy - before_xy) / velocity_s
    residual: Array = (after_xy - at_xy) - velocity * window_s
    return residual


def project(vector: Array, direction: Array) -> float:
    return float(vector[0] * direction[0] + vector[1] * direction[1])


def line_height(x_att: Array, is_goalkeeper: NDArray[np.bool_]) -> float:
    """Mean `x_att` of the two deepest (largest `x_att`) outfield opponents; NaN when fewer
    than two outfield opponents have a position."""
    outfield = x_att[~is_goalkeeper]
    outfield = outfield[np.isfinite(outfield)]
    if outfield.size < 2:
        return math.nan
    return float(np.sort(outfield)[-2:].mean())


def residual_scalar(
    before: float, at: float, after: float, *, window_s: float, velocity_s: float
) -> float:
    """The scalar twin of `residual_displacement`, for the line height."""
    return (after - at) - ((at - before) / velocity_s) * window_s


def standardise(values: Array, placebo_sd: float) -> Array:
    """Values in units of the sd of the placebo values pooled over the calibration half."""
    if not placebo_sd > 0.0:
        raise ValueError(f"placebo sd must be positive, got {placebo_sd}")
    scaled: Array = np.asarray(values, dtype=np.float64) / placebo_sd
    return scaled


def mean_and_se(values: Array) -> tuple[float, float]:
    """Mean and standard error of the mean of the finite values (n >= 2 for a finite se)."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return math.nan, math.nan
    if finite.size == 1:
        return float(finite[0]), math.nan
    return float(finite.mean()), float(finite.std(ddof=1) / math.sqrt(finite.size))
