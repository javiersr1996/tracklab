"""M1 and M2 of task 60 as code, and their simulation against the noise twin (phase B1).

The forms are those of the protocol after the six reviews (tasks/todo.md, task 60), with its
numbers as the defaults:

* **M1**: fewer than 10 players with >= 5 windows finite in s in the high band -> dies.
* **M2**: among the players with >= 5 windows finite in s in both bands (fewer than 10 -> dies
  by coverage), fewer than 3 in 4 with cad_s high > cad_s low (each the median of his finite
  windows in that band) -> dies; or, among the players of M1, the median of the propagated sd
  of the median of his first 5 finite high windows exceeds half the IQR between players of that
  same median -> dies.

The propagated sd of a player follows point 6(i) of the second review: draw k of every one of
his five windows gives one median (`nanmedian`: a window NaN in that draw is ignored), a draw
with all five NaN is not valid, and the sd (ddof 1) is over the valid draws. With fewer than two
valid draws there is no sd; such a player counts as imprecise (an infinite sd), a choice the
protocol does not make and this module does. The IQR is numpy's linear-interpolation
percentiles 75 minus 25.

`m1_m2` judges one match from its windows; M4 passes it the half IQR of 1925299, frozen as a
number, instead of the one of its own squad. `simulate_m1_m2` builds matches by resampling
windows from two pools with the counts of admitted windows per player and band that the probe
measures, and says how often P6 dies. Against the noise twin (`sweep.noise_pool` in both bands,
NaN included), the rule of (W, cap) asks P(P6 dies | noise) >= 0.95 in each rho; against sane
pools (`sweep.sane_pool`), `simulate_sane` gives each player his own cadence, spread between
players and lower in the low band, and the rule asks that P6 live (phase B2).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

MIN_PLAYERS = 10
MIN_WINDOWS = 5
SIGN_SHARE = 0.75
REPS = 200
SEED = 60
DEATHS = ("m1", "m2_coverage", "m2_sign", "m2_precision")


@dataclass(frozen=True)
class Pool:
    """Windows to resample: the cadence of s of each (n,) and the cadences of its Monte Carlo
    copies (n, draws). NaN kept."""

    cadence: Array
    draws: Array


@dataclass(frozen=True)
class Player:
    """One player's admitted windows, in frame order: the cadence of s of each high window, of
    each low window, and the Monte Carlo cadences of each high window (len(high), draws)."""

    high: Array
    low: Array
    high_draws: Array


@dataclass(frozen=True)
class Verdict:
    dies_at: str | None  # one of DEATHS, the first that kills, or None
    m1_players: int
    m2_players: int
    m2_positive: int
    median_sd_hz: float
    half_iqr_hz: float


def propagated_sd(draws: Array) -> float:
    """The sd over the draws of the median of the windows (rows of `draws`)."""
    valid = draws[:, ~np.all(np.isnan(draws), axis=0)]
    if valid.shape[1] < 2:
        return np.inf
    return float(np.std(np.nanmedian(valid, axis=0), ddof=1))


def m1_m2(
    players: Sequence[Player],
    *,
    min_players: int = MIN_PLAYERS,
    min_windows: int = MIN_WINDOWS,
    share: float = SIGN_SHARE,
    half_iqr_hz: float | None = None,
) -> Verdict:
    """`half_iqr_hz`, when given, is the precision clause's threshold instead of half the IQR
    of these players' five-window medians (M4: 1925299's, frozen as a number)."""
    finite_high = [np.flatnonzero(np.isfinite(p.high)) for p in players]
    m1 = [i for i, f in enumerate(finite_high) if len(f) >= min_windows]
    both = [i for i in m1 if np.sum(np.isfinite(players[i].low)) >= min_windows]
    positive = sum(
        float(np.nanmedian(players[i].high)) > float(np.nanmedian(players[i].low)) for i in both
    )
    first = [finite_high[i][:min_windows] for i in m1]
    medians = np.array([np.median(players[i].high[f]) for i, f in zip(m1, first, strict=True)])
    sds = np.array(
        [propagated_sd(players[i].high_draws[f]) for i, f in zip(m1, first, strict=True)]
    )
    if len(m1) >= 2:
        q25, q75 = np.percentile(medians, [25, 75])
        median_sd, half_iqr = float(np.median(sds)), float(q75 - q25) / 2.0
    else:
        median_sd = half_iqr = np.nan
    if half_iqr_hz is not None:
        half_iqr = half_iqr_hz
    if len(m1) < min_players:
        dies: str | None = "m1"
    elif len(both) < min_players:
        dies = "m2_coverage"
    elif positive < share * len(both):
        dies = "m2_sign"
    elif median_sd > half_iqr:
        dies = "m2_precision"
    else:
        dies = None
    return Verdict(dies, len(m1), len(both), positive, median_sd, half_iqr)


def simulate_m1_m2(
    high_counts: Sequence[int],
    low_counts: Sequence[int],
    high: Pool,
    low: Pool,
    *,
    reps: int = REPS,
    seed: int = SEED,
) -> dict[str, Any]:
    """P6 judged `reps` times on matches whose player i has `high_counts[i]` windows drawn
    (with replacement) from `high` and `low_counts[i]` from `low`."""
    if len(high_counts) != len(low_counts):
        raise ValueError("one count per player and band")
    rng = np.random.default_rng(seed)
    tally: Counter[str] = Counter()
    for _ in range(reps):
        players = []
        for nh, nl in zip(high_counts, low_counts, strict=True):
            i = rng.integers(len(high.cadence), size=nh)
            j = rng.integers(len(low.cadence), size=nl)
            players.append(Player(high.cadence[i], low.cadence[j], high.draws[i]))
        tally[m1_m2(players).dies_at or "alive"] += 1
    return _tallied(tally, reps)


def simulate_sane(
    high_counts: Sequence[int],
    low_counts: Sequence[int],
    high: Pool,
    low: Pool,
    *,
    cadence_hz: float,
    delta_hz: float,
    sigma_b_hz: float,
    reps: int = REPS,
    seed: int = SEED,
) -> dict[str, Any]:
    """P6 judged `reps` times on sane players: player i runs at c_i = `cadence_hz` + `sigma_b_hz`
    x N(0, 1) in the high band and c_i - `delta_hz` in the low one. Both pools were drawn at
    `cadence_hz`; a window and its copies are scaled by c_i / `cadence_hz` (by (c_i - delta) /
    `cadence_hz` in the low band), so a player keeps the estimator's relative error, not its
    error at c_i (an approximation, said in the protocol)."""
    if len(high_counts) != len(low_counts):
        raise ValueError("one count per player and band")
    rng = np.random.default_rng(seed)
    tally: Counter[str] = Counter()
    for _ in range(reps):
        players = []
        for nh, nl in zip(high_counts, low_counts, strict=True):
            c = cadence_hz + sigma_b_hz * rng.standard_normal()
            f_high, f_low = c / cadence_hz, (c - delta_hz) / cadence_hz
            i = rng.integers(len(high.cadence), size=nh)
            j = rng.integers(len(low.cadence), size=nl)
            players.append(
                Player(high.cadence[i] * f_high, low.cadence[j] * f_low, high.draws[i] * f_high)
            )
        tally[m1_m2(players).dies_at or "alive"] += 1
    return _tallied(tally, reps)


def _tallied(tally: Counter[str], reps: int) -> dict[str, Any]:
    dies = reps - tally["alive"]
    return {"reps": reps, "dies": dies, "p_dies": dies / reps, "by": {d: tally[d] for d in DEATHS}}
