"""`tracklab runs probe`: death probe 1 of P5, on the calibration half alone (task 49).

Writes the `probe` section of `reports/runs_calibration.json`, in this order and with the
death criteria written before anything was looked at (tasks/todo.md, P5, task 49):

(a) the cadence of the football tracking: the fraction of second differences of a detected
    player's position that are null, the autocorrelation of |acceleration| by lag and its
    peak, and the shortest window that cadence admits, against the protocol's V and W;
    the tracked length of every run against the protocol's minimum;
(e) three design properties of the placebo each pair got, printed before any null: the gap
    |t' - t_c|, the runner holding a `player_possession` at t', and the instants several
    runs share; and from them the unit of the null, the connected component of the pairs
    that share a possession or a placebo instant inside the match (`windows.unit_labels`);
(b) the instrument: the quantity whose direction is forced, the marker's displacement along
    the run against the placebo's, every run together, per match and pooled, against the
    protocol's bar; and the line height at t_c against the provider's
    `last_defensive_line_height_start`, correlation and median difference per match;
(c) the real null: sign flips of the units inside each match, the whole bar applied to each
    draw, how often it fires per subtype and at least once over the ten; the hardening rule
    of the protocol is evaluated and never applied here;
(d) the power: MDE80 per subtype in both halves, in placebo sd and in metres, simulated with
    the measured dispersion, the measured within-unit correlation and the unit sizes of each
    half; the sizes of the closed half come from `windows.count_tracking`, counts and nothing
    else.

No effect per subtype is computed, printed or stored: the pairs live in memory for the
duration of the command. Every tracking the probe holds is a `windows.MatchTracking`, which
passed the guard as it was built; the ids are `data.load_half("calibration")` and the other
half is only counted. `--check` regenerates the file where the warehouse holds the 20
matches (`FULL`), and otherwise verifies the seal, the protocol it answers to, the match
list and the verdict against the figures as written (`PARTIAL`).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from numpy.typing import NDArray

from tracklab.runs import placebo
from tracklab.runs.coverage import has_frames
from tracklab.runs.data import (
    Half,
    committed_protocol,
    counting_match_ids,
    head_commit,
    load_half,
)
from tracklab.runs.protocol import (
    BAR_OF_MATCHES,
    BAR_P,
    BAR_SAME_SIGN_MATCHES,
    BAR_Z,
    EFFECT_WINDOW_S,
    MIN_RUN_LENGTH_M,
    N_PERMUTATIONS,
    NULL_AT_LEAST_ONE_MAX_PCT,
    SAMPLE_RATE_HZ,
    SEED,
    TESTABILITY_MDE80_SD,
    VELOCITY_WINDOW_S,
    render,
    seal,
    sealed,
)
from tracklab.runs.windows import (
    PLACEBO_RULE,
    SUBTYPES,
    MatchCounts,
    MatchTracking,
    PairEffect,
    count_tracking,
    line_height_at,
    load_runs,
    load_tracking,
    pair_effects,
    pair_unit_key,
    run_length,
    unit_labels,
    units_by_subtype,
)

PROBE_NAME = "runs_calibration.json"
SCHEMA_VERSION = 1
TASK = 49
WRITTEN = "2026-10-10"
HALF: Half = "calibration"
NULL_DRAWS = N_PERMUTATIONS  # null data sets the bar is applied to, each with its own test
POWER_REPLICATIONS = 400
POWER_TARGET = 0.8
MDE_GRID_SD = tuple(round(0.05 * i, 2) for i in range(1, 17))  # 0.05 to 0.80
CADENCE_MAX_LAG = 30  # frames: 3 s at 10 Hz
# Seed streams, all children of the protocol's seed: one per use, so adding a use later does
# not move the others.
STREAM_INSTRUMENT, STREAM_NULL_OUTER, STREAM_NULL_INNER, STREAM_POWER = 0, 1, 2, 3

Array = NDArray[np.float64]


class ProbeInputError(RuntimeError):
    """The warehouse cannot give the probe its ten calibration matches, or the two doors
    (pairs and counts) of one match disagree."""


Z_TWO_SIDED = BAR_Z  # the protocol's z_equivalent, the normal quantile of its two-sided p


# --- (a) cadence --------------------------------------------------------------------------


@dataclass(frozen=True)
class Cadence:
    """Second differences of a detected player's position (detected at k - 1, k, k + 1), one
    match: how many triples, how many with a null second difference (exactly, and within half
    the coordinate grid), the grid, and the pooled autocorrelation of |a| as numerators per lag
    and one denominator, so matches add up."""

    triples: int
    exactly_zero: int
    below_half_grid: int
    grid_m: float
    autocorrelation_numerator: tuple[float, ...]
    autocorrelation_denominator: float


def cadence(t: MatchTracking, max_lag: int = CADENCE_MAX_LAG) -> Cadence:
    x, y, det = t.x, t.y, t.detected
    d2x = x[2:] - 2.0 * x[1:-1] + x[:-2]
    d2y = y[2:] - 2.0 * y[1:-1] + y[:-2]
    ok = det[2:] & det[1:-1] & det[:-2] & np.isfinite(d2x) & np.isfinite(d2y)
    consecutive = det[1:] & det[:-1]
    d1 = np.concatenate([np.abs(x[1:] - x[:-1])[consecutive], np.abs(y[1:] - y[:-1])[consecutive]])
    d1 = d1[np.isfinite(d1) & (d1 > 0)]
    grid = float(d1.min()) if d1.size else math.nan
    a = np.hypot(d2x, d2y)
    a = np.where(ok, a, np.nan)
    with np.errstate(invalid="ignore"):
        centred = a - np.nanmean(a, axis=0, keepdims=True)
    den = float(np.nansum(centred * centred))
    num = tuple(float(np.nansum(centred[lag:] * centred[:-lag])) for lag in range(1, max_lag + 1))
    magnitude = a[ok]
    return Cadence(
        triples=int(ok.sum()),
        exactly_zero=int((magnitude == 0.0).sum()),
        below_half_grid=int((magnitude < grid / 2.0).sum()) if math.isfinite(grid) else 0,
        grid_m=grid,
        autocorrelation_numerator=num,
        autocorrelation_denominator=den,
    )


def cadence_lag(autocorrelation: Sequence[float]) -> int:
    """The cadence in frames: the first lag (from 2) where the autocorrelation of |a| rises
    above the lag before and holds against the lag after, the shortest period the tracking
    repeats its slope changes at; 1 when the curve only decays (no cadence beyond a frame).
    A tracking that changes slope every c frames peaks at c, 2c, 3c alike: the first wins."""
    ac = list(autocorrelation)
    for lag in range(2, len(ac) + 1):
        before, here = ac[lag - 2], ac[lag - 1]
        after = ac[lag] if lag < len(ac) else -math.inf
        if here > before and here >= after:
            return lag
    return 1


def pooled_autocorrelation(cadences: Sequence[Cadence]) -> list[float]:
    """The autocorrelation of |a| by lag over the matches: numerators and denominators add."""
    den = sum(c.autocorrelation_denominator for c in cadences)
    lags = len(cadences[0].autocorrelation_numerator)
    if den <= 0.0:
        return [math.nan] * lags
    return [sum(c.autocorrelation_numerator[i] for c in cadences) / den for i in range(lags)]


# --- per-match loading: values, behind the guard ----------------------------------------


def load_player_possessions(data_dir: Path, match_id: int) -> list[tuple[int, int, int]]:
    """(player_id, frame_start, frame_end) of every `player_possession` of the match, from
    bronze events: who has the ball when, no tracking."""
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT player_id, frame_start, frame_end FROM read_parquet($g) "
            "WHERE match_id = $m AND event_type = 'player_possession' ORDER BY frame_start",
            {
                "g": (data_dir / "bronze" / "football" / "dynamic_events" / "*.parquet").as_posix(),
                "m": match_id,
            },
        ).fetchall()
    finally:
        con.close()
    return [(int(p), int(a), int(b)) for p, a, b in rows]


def load_provider_lines(t: MatchTracking, data_dir: Path) -> tuple[float, dict[str, float]]:
    """The pitch length and, per run event_id, the provider's last defensive line at the
    run's start as an x in the attack frame: pitch_length / 2 - last_defensive_line_height_start
    (the provider measures the height from the defending goal line). A provider measure, read
    only to contrast the instrument, and only of a match whose tracking the caller holds."""
    football = data_dir / "bronze" / "football"
    con = duckdb.connect()
    try:
        (length,) = con.execute(
            "SELECT pitch_length FROM read_parquet($g) WHERE match_id = $m",
            {"g": (football / "match" / "*.parquet").as_posix(), "m": t.match_id},
        ).fetchone() or (None,)
        rows = con.execute(
            "SELECT event_id, last_defensive_line_height_start FROM read_parquet($g) "
            "WHERE match_id = $m AND event_type = 'off_ball_run'",
            {"g": (football / "dynamic_events" / "*.parquet").as_posix(), "m": t.match_id},
        ).fetchall()
    finally:
        con.close()
    if length is None:
        raise ProbeInputError(f"no pitch length for match {t.match_id} in bronze match")
    half = float(length) / 2.0
    return float(length), {str(e): half - float(h) for e, h in rows if h is not None}


@dataclass(frozen=True)
class MatchProbe:
    """What the probe holds of one calibration match while it runs: the pairs (values, never
    serialised whole), the tracked length and the line height at t_c of every run, the
    provider's line, whether the runner has the ball at t', and the cadence."""

    match_id: int
    runs: int
    pairs: tuple[PairEffect, ...]
    length_m: Array
    line_at_tc_m: Array
    provider_line_x_m: Array
    pitch_length_m: float
    runner_in_possession_at_placebo: NDArray[np.bool_]
    cadence: Cadence


def probe_match(t: MatchTracking, data_dir: Path) -> MatchProbe:
    """Everything the probe needs of one match, from a tracking that passed the guard."""
    runs = load_runs(data_dir, t.match_id)
    instants = placebo.placebo_instants(data_dir, [t.match_id], PLACEBO_RULE)
    pairs = tuple(pair_effects(t, runs, instants))
    pitch, provider = load_provider_lines(t, data_dir)
    possessions = load_player_possessions(data_dir, t.match_id)

    def as_array(values: list[float | None]) -> Array:
        return np.array([math.nan if v is None else v for v in values], dtype=np.float64)

    holding = np.array(
        [
            any(p == pair.player_id and a <= pair.placebo_instant <= b for p, a, b in possessions)
            for pair in pairs
        ],
        dtype=np.bool_,
    )
    return MatchProbe(
        match_id=t.match_id,
        runs=len(runs),
        pairs=pairs,
        length_m=as_array([run_length(t, r) for r in runs]),
        line_at_tc_m=as_array([line_height_at(t, r) for r in runs]),
        provider_line_x_m=as_array([provider.get(r.event_id) for r in runs]),
        pitch_length_m=pitch,
        runner_in_possession_at_placebo=holding,
        cadence=cadence(t),
    )


# --- the null and the bar: arithmetic on arrays -------------------------------------------


def sign_flips(rng: np.random.Generator, draws: int, n_units: int) -> Array:
    flips: Array = rng.integers(0, 2, size=(draws, n_units)).astype(np.float64) * 2.0 - 1.0
    return flips


def unit_sums(values: Array, units: NDArray[np.intp], n_units: int) -> Array:
    sums: Array = np.bincount(units, weights=values, minlength=n_units).astype(np.float64)
    return sums


def permutation_p(stat: float, flipped: Array) -> float:
    """Two-sided, (1 + count of |stat*| >= |stat|) / (1 + draws), as the protocol writes it."""
    return (1 + int((np.abs(flipped) >= abs(stat)).sum())) / (1 + int(flipped.size))


def same_sign_matches(match_sums: Array, pooled: float) -> int:
    """How many matches' sums have the sign of the pooled statistic; a match without pairs
    (sum 0) never agrees."""
    return int((np.sign(match_sums) == np.sign(pooled)).sum()) if pooled != 0.0 else 0


@dataclass(frozen=True)
class BarVerdict:
    pairs: int
    units: int
    mean: float
    p: float
    same_sign_matches: int
    of_matches: int
    passes: bool


def bar_verdict(
    values: Array,
    units: NDArray[np.intp],
    match_of_pair: NDArray[np.intp],
    n_matches: int,
    rng: np.random.Generator,
) -> BarVerdict:
    """The protocol's bar on one set of pairs: same sign in at least 8 of the 10 matches and
    the sign-flip permutation p over the units at most BAR_P. The units never cross a match
    (`unit_labels` runs per match)."""
    n_units = int(units.max()) + 1 if units.size else 0
    n = int(values.size)
    pooled = float(values.sum()) / n if n else math.nan
    sums = unit_sums(values, units, n_units)
    flipped = sign_flips(rng, N_PERMUTATIONS, n_units) @ sums
    p = permutation_p(float(values.sum()), flipped)
    per_match = unit_sums(values, match_of_pair, n_matches)
    agreeing = same_sign_matches(per_match, pooled)
    return BarVerdict(
        pairs=n,
        units=n_units,
        mean=pooled,
        p=p,
        same_sign_matches=agreeing,
        of_matches=n_matches,
        passes=agreeing >= BAR_SAME_SIGN_MATCHES and p <= BAR_P,
    )


@dataclass(frozen=True)
class NullRates:
    """How often the bar fires on null data sets: per subtype, with the permutation p the
    protocol names and with its normal approximation (the one the power uses), and at least
    once over the subtypes."""

    draws: int
    fires_pct: tuple[float, ...]
    fires_normal_pct: tuple[float, ...]
    at_least_one_pct: float
    at_least_one_normal_pct: float


def null_fire_rates(
    values: Array,
    units: NDArray[np.intp],
    match_of_pair: NDArray[np.intp],
    subtype_of_pair: NDArray[np.intp],
    n_subtypes: int,
    n_matches: int,
    rng_outer: np.random.Generator,
    rng_inner: np.random.Generator,
    draws: int = NULL_DRAWS,
) -> NullRates:
    """`draws` null data sets, each a sign flip of every unit inside its match, shared by the
    subtypes (a unit may hold pairs of several); on each, per subtype, the whole bar: the
    sign count over the matches and a fresh permutation p from N_PERMUTATIONS inner flips.
    The inner flips are one draw of N_PERMUTATIONS sign vectors multiplied by the outer one,
    so each null data set is tested as the real one is."""
    n_units = int(units.max()) + 1 if units.size else 0
    n_pairs = np.bincount(subtype_of_pair, minlength=n_subtypes)
    sums = np.zeros((n_units, n_subtypes))
    np.add.at(sums, (units, subtype_of_pair), values)
    match_of_unit = np.zeros(n_units, dtype=np.intp)
    match_of_unit[units] = match_of_pair
    onehot = np.zeros((n_units, n_matches))
    onehot[np.arange(n_units), match_of_unit] = 1.0
    outer = sign_flips(rng_outer, draws, n_units)
    inner = sign_flips(rng_inner, N_PERMUTATIONS, n_units)
    fires = np.zeros((draws, n_subtypes), dtype=np.bool_)
    fires_normal = np.zeros((draws, n_subtypes), dtype=np.bool_)
    for k in range(n_subtypes):
        s = sums[:, k]
        if n_pairs[k] == 0:
            continue
        total = outer @ s  # (draws,): the pooled sum of each null data set
        per_match = outer @ (s[:, None] * onehot)  # (draws, matches)
        agreeing = (np.sign(per_match) == np.sign(total)[:, None]).sum(axis=1)
        sign_ok = (agreeing >= BAR_SAME_SIGN_MATCHES) & (total != 0.0)
        reference = inner @ (s[:, None] * outer.T)  # (N_PERMUTATIONS, draws)
        counts = (np.abs(reference) >= np.abs(total)[None, :]).sum(axis=0)
        p = (1 + counts) / (1 + N_PERMUTATIONS)
        fires[:, k] = sign_ok & (p <= BAR_P)
        z = total / math.sqrt(float((s * s).sum()))
        fires_normal[:, k] = sign_ok & (np.abs(z) >= Z_TWO_SIDED)
    return NullRates(
        draws=draws,
        fires_pct=tuple(float(v) for v in fires.mean(axis=0) * 100.0),
        fires_normal_pct=tuple(float(v) for v in fires_normal.mean(axis=0) * 100.0),
        at_least_one_pct=float(fires.any(axis=1).mean() * 100.0),
        at_least_one_normal_pct=float(fires_normal.any(axis=1).mean() * 100.0),
    )


# --- the power ----------------------------------------------------------------------------


@dataclass(frozen=True)
class DesignEffect:
    """The within-unit correlation of the pair values, the pairwise intraclass estimator over
    the units of two or more pairs."""

    rho: float
    units_of_two_or_more: int
    pairs_of_pairs: int


def design_effect(values: Array, units: NDArray[np.intp]) -> DesignEffect:
    n_units = int(units.max()) + 1 if units.size else 0
    centred = values - values.mean()
    size = np.bincount(units, minlength=n_units)
    c = unit_sums(centred, units, n_units)
    q = unit_sums(centred * centred, units, n_units)
    cross = float(((c * c - q) / 2.0).sum())
    pairs_of_pairs = int((size * (size - 1) // 2).sum())
    variance = float((centred * centred).mean())
    rho = cross / (pairs_of_pairs * variance) if pairs_of_pairs and variance > 0 else math.nan
    return DesignEffect(rho, int((size >= 2).sum()), pairs_of_pairs)


@dataclass(frozen=True)
class Power:
    """Pass rate of the bar at each effect of the grid (in placebo sd), and the smallest
    effect that passes at least POWER_TARGET of the time (None when none of the grid does)."""

    pairs: int
    units: int
    pass_rate_by_effect: tuple[float, ...]
    mde80_sd: float | None


def mde80(
    units_per_match: Sequence[Sequence[int]],
    *,
    sd_pair: float,
    rho: float,
    sd_placebo: float,
    rng: np.random.Generator,
    replications: int = POWER_REPLICATIONS,
    grid: Sequence[float] = MDE_GRID_SD,
    same_sign_at_least: int = BAR_SAME_SIGN_MATCHES,
) -> Power:
    """The bar's pass rate when every pair carries an effect of d placebo sd on top of noise
    with the measured sd of the pair values and the measured within-unit correlation (a
    unit effect plus a pair residual), on the unit sizes of each match of the half. The
    sign-flip p is taken by its normal approximation (|z| >= Z_TWO_SIDED, z the pooled sum
    over the root of the sum of squared unit sums) and the sign count as in the bar; common
    random numbers across the grid, so the curve is monotone. The matches are the half's:
    `units_per_match` has one entry per match, empty where the subtype has no pair."""
    sizes = np.array([s for match in units_per_match for s in match], dtype=np.intp)
    n_units = int(sizes.size)
    n_pairs = int(sizes.sum())
    if n_pairs == 0:
        return Power(0, 0, tuple(0.0 for _ in grid), None)
    unit_of_pair = np.repeat(np.arange(n_units), sizes)
    match_of_unit = np.repeat(
        np.arange(len(units_per_match)), [len(match) for match in units_per_match]
    )
    onehot = np.zeros((n_units, len(units_per_match)))
    onehot[np.arange(n_units), match_of_unit] = 1.0
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    rho_used = min(max(rho, 0.0), 1.0) if math.isfinite(rho) else 0.0
    unit_effect = rng.normal(0.0, math.sqrt(rho_used) * sd_pair, size=(replications, n_units))
    residual = rng.normal(0.0, math.sqrt(1.0 - rho_used) * sd_pair, size=(replications, n_pairs))
    noise = residual + unit_effect[:, unit_of_pair]
    rates: list[float] = []
    for d in grid:
        y = noise + d * sd_placebo
        sums = np.add.reduceat(y, starts, axis=1)  # (replications, units)
        total = y.sum(axis=1)
        z = total / np.sqrt((sums * sums).sum(axis=1))
        per_match = sums @ onehot
        agreeing = (np.sign(per_match) == np.sign(total)[:, None]).sum(axis=1)
        passes = (np.abs(z) >= Z_TWO_SIDED) & (agreeing >= same_sign_at_least)
        rates.append(float(passes.mean()))
    mde = next((float(d) for d, r in zip(grid, rates, strict=True) if r >= POWER_TARGET), None)
    return Power(n_pairs, n_units, tuple(rates), mde)


def probable_subtypes(
    mde: dict[tuple[str, str, str], float | None], halves: Iterable[str]
) -> dict[str, list[str]]:
    """Per quantity, the subtypes whose MDE80 (keyed by subtype, half and quantity) is at most
    TESTABILITY_MDE80_SD placebo sd in every half; on the 0.05 grid a subtype can land on the
    threshold exactly, and it counts. M1 counts `marker`, the forced-direction instrument;
    `both` is the intersection."""
    halves = list(halves)

    def testable(value: float | None) -> bool:
        return value is not None and value <= TESTABILITY_MDE80_SD

    def probable(quantity: str) -> list[str]:
        return [s for s in SUBTYPES if all(testable(mde[(s, h, quantity)]) for h in halves)]

    lists = {"marker": probable("marker"), "line": probable("line")}
    lists["both"] = [s for s in lists["marker"] if s in lists["line"]]
    return lists


# --- the payload --------------------------------------------------------------------------


def _round(value: float, digits: int) -> float | None:
    return None if not math.isfinite(value) else round(float(value), digits)


def _quantile(values: Array, q: float) -> float:
    finite = values[np.isfinite(values)]
    return float(np.quantile(finite, q)) if finite.size else math.nan


def _pearson(a: Array, b: Array) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return math.nan
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


@dataclass(frozen=True)
class _Pairs:
    """Every pair of the half as parallel arrays, the units labelled per match and then
    offset so labels are unique across the half (a unit never crosses a match)."""

    match_of_pair: NDArray[np.intp]
    subtype_of_pair: NDArray[np.intp]
    units: NDArray[np.intp]
    marker_m: Array
    line_m: Array
    placebo_marker_m: Array
    placebo_line_m: Array
    gap_s: Array
    shared_instant: NDArray[np.bool_]
    shared_possession: NDArray[np.bool_]
    holding: NDArray[np.bool_]
    units_per_match: tuple[int, ...]
    largest_unit_per_match: tuple[int, ...]
    shared_instants_per_match: tuple[int, ...]
    shared_possessions_per_match: tuple[int, ...]


def _collect(probes: Sequence[MatchProbe]) -> _Pairs:
    match_of, subtype_of, units, offset = [], [], [], 0
    shared_i, shared_p = [], []
    per_match_units, largest, n_shared_i, n_shared_p = [], [], [], []
    for m, probe in enumerate(probes):
        keys = [pair_unit_key(p) for p in probe.pairs]
        labels = unit_labels(keys)
        n_units = len(set(labels))
        instants: dict[tuple[int, int], int] = {}
        possessions: dict[str, int] = {}
        for pair in probe.pairs:
            key_i = (pair.player_id, pair.placebo_instant)
            instants[key_i] = instants.get(key_i, 0) + 1
            if pair.possession_id is not None:
                possessions[pair.possession_id] = possessions.get(pair.possession_id, 0) + 1
        for pair, label in zip(probe.pairs, labels, strict=True):
            match_of.append(m)
            subtype_of.append(SUBTYPES.index(pair.subtype))
            units.append(offset + label)
            shared_i.append(instants[(pair.player_id, pair.placebo_instant)] >= 2)
            shared_p.append(pair.possession_id is not None and possessions[pair.possession_id] >= 2)
        offset += n_units
        per_match_units.append(n_units)
        largest.append(int(np.bincount(labels).max()) if labels else 0)
        n_shared_i.append(sum(1 for n in instants.values() if n >= 2))
        n_shared_p.append(sum(1 for n in possessions.values() if n >= 2))
    pairs = [p for probe in probes for p in probe.pairs]
    return _Pairs(
        match_of_pair=np.array(match_of, dtype=np.intp),
        subtype_of_pair=np.array(subtype_of, dtype=np.intp),
        units=np.array(units, dtype=np.intp),
        marker_m=np.array([p.marker_m for p in pairs]),
        line_m=np.array([p.line_m for p in pairs]),
        placebo_marker_m=np.array([p.placebo_marker_m for p in pairs]),
        placebo_line_m=np.array([p.placebo_line_m for p in pairs]),
        gap_s=np.array([abs(p.placebo_instant - p.t_c) / SAMPLE_RATE_HZ for p in pairs]),
        shared_instant=np.array(shared_i, dtype=np.bool_),
        shared_possession=np.array(shared_p, dtype=np.bool_),
        holding=np.concatenate([probe.runner_in_possession_at_placebo for probe in probes])
        if probes
        else np.zeros(0, dtype=np.bool_),
        units_per_match=tuple(per_match_units),
        largest_unit_per_match=tuple(largest),
        shared_instants_per_match=tuple(n_shared_i),
        shared_possessions_per_match=tuple(n_shared_p),
    )


def _cadence_section(probes: Sequence[MatchProbe]) -> dict[str, Any]:
    cadences = [p.cadence for p in probes]
    pooled = pooled_autocorrelation(cadences)
    peak_lag = cadence_lag(pooled)
    min_window_s = peak_lag / SAMPLE_RATE_HZ
    triples = sum(c.triples for c in cadences)
    per_match = []
    for probe in probes:
        c = probe.cadence
        own = pooled_autocorrelation([c])
        per_match.append(
            {
                "match_id": probe.match_id,
                "triples": c.triples,
                "second_difference_exactly_zero_fraction": _round(c.exactly_zero / c.triples, 4),
                "second_difference_below_half_grid_fraction": _round(
                    c.below_half_grid / c.triples, 4
                ),
                "grid_m": _round(c.grid_m, 4),
                "cadence_lag_frames": cadence_lag(own),
                "autocorrelation_at_cadence": _round(own[cadence_lag(own) - 1], 4),
            }
        )
    return {
        "what": (
            "second differences of position of a player detected at k-1, k, k+1 (metres, "
            "10 Hz): the fraction that are null (exactly, and below half the coordinate "
            "grid), and the autocorrelation of |acceleration| by lag, pooled over players "
            "with each player's mean removed; a tracking that changes slope every c frames "
            "shows null second differences between knots and its first local maximum at "
            "lag c (cadence_lag_frames), and a window shorter than c frames cannot see a "
            "residual"
        ),
        "per_match": per_match,
        "pooled": {
            "triples": triples,
            "second_difference_exactly_zero_fraction": _round(
                sum(c.exactly_zero for c in cadences) / triples, 4
            ),
            "second_difference_below_half_grid_fraction": _round(
                sum(c.below_half_grid for c in cadences) / triples, 4
            ),
            "autocorrelation_by_lag": [_round(v, 4) for v in pooled],
            "cadence_lag_frames": peak_lag,
            "autocorrelation_at_cadence": _round(pooled[peak_lag - 1], 4),
        },
        "windows": {
            "min_window_s": min_window_s,
            "velocity_s": VELOCITY_WINDOW_S,
            "effect_s": EFFECT_WINDOW_S,
            "velocity_window_admits": VELOCITY_WINDOW_S >= min_window_s,
            "effect_window_admits": EFFECT_WINDOW_S >= min_window_s,
            "changed": False,
            "rule": (
                "the protocol lets task 49 shorten W or V once, to the minimum the cadence "
                "admits; both already exceed it, so neither changes"
            ),
        },
    }


def _length_section(probes: Sequence[MatchProbe]) -> dict[str, Any]:
    per_match = []
    for probe in probes:
        tracked = probe.length_m[np.isfinite(probe.length_m)]
        per_match.append(
            {
                "match_id": probe.match_id,
                "runs": probe.runs,
                "runs_tracked_at_both_ends": int(tracked.size),
                "below_minimum": int((tracked < MIN_RUN_LENGTH_M).sum()),
                "p10_m": _round(_quantile(tracked, 0.1), 3),
                "p50_m": _round(_quantile(tracked, 0.5), 3),
                "p90_m": _round(_quantile(tracked, 0.9), 3),
            }
        )
    every = np.concatenate([p.length_m for p in probes])
    tracked = every[np.isfinite(every)]
    return {
        "what": (
            "metres between the runner's tracked positions at frame_start and frame_end, "
            "against the protocol's minimum run length"
        ),
        "min_run_length_m": MIN_RUN_LENGTH_M,
        "per_match": per_match,
        "pooled": {
            "runs": int(every.size),
            "runs_tracked_at_both_ends": int(tracked.size),
            "below_minimum": int((tracked < MIN_RUN_LENGTH_M).sum()),
            "below_minimum_fraction": _round(
                float((tracked < MIN_RUN_LENGTH_M).mean()) if tracked.size else math.nan, 4
            ),
            "p10_m": _round(_quantile(tracked, 0.1), 3),
            "p50_m": _round(_quantile(tracked, 0.5), 3),
            "p90_m": _round(_quantile(tracked, 0.9), 3),
        },
        "changed": False,
    }


def _placebo_design_section(probes: Sequence[MatchProbe], pairs: _Pairs) -> dict[str, Any]:
    per_match = []
    for m, probe in enumerate(probes):
        mine = pairs.match_of_pair == m
        n = int(mine.sum())
        per_match.append(
            {
                "match_id": probe.match_id,
                "pairs": n,
                "gap_s_p50": _round(_quantile(pairs.gap_s[mine], 0.5), 2),
                "gap_s_p90": _round(_quantile(pairs.gap_s[mine], 0.9), 2),
                "runner_in_possession_at_placebo_fraction": _round(
                    float(pairs.holding[mine].mean()) if n else math.nan, 4
                ),
                "shared_instants": pairs.shared_instants_per_match[m],
                "pairs_on_shared_instants": int(pairs.shared_instant[mine].sum()),
                "pairs_on_shared_instants_fraction": _round(
                    float(pairs.shared_instant[mine].mean()) if n else math.nan, 4
                ),
                "shared_possessions": pairs.shared_possessions_per_match[m],
                "pairs_in_shared_possessions": int(pairs.shared_possession[mine].sum()),
                "pairs_in_shared_possessions_fraction": _round(
                    float(pairs.shared_possession[mine].mean()) if n else math.nan, 4
                ),
            }
        )
    n = int(pairs.gap_s.size)
    return {
        "what": (
            "three properties of the placebo each pair of the analysis set got, before any "
            "null: the gap |t' - t_c| in seconds; whether the runner holds a "
            "player_possession covering t' (an off-ball placebo with the runner on the "
            "ball, from the offset rule); and the instants shared by several pairs (same "
            "runner, same t': the placebo quantity is the same in each), with the "
            "possessions shared by several pairs alongside"
        ),
        "per_match": per_match,
        "pooled": {
            "pairs": n,
            "gap_s_p50": _round(_quantile(pairs.gap_s, 0.5), 2),
            "gap_s_p90": _round(_quantile(pairs.gap_s, 0.9), 2),
            "runner_in_possession_at_placebo_fraction": _round(
                float(pairs.holding.mean()) if n else math.nan, 4
            ),
            "shared_instants": int(sum(pairs.shared_instants_per_match)),
            "pairs_on_shared_instants": int(pairs.shared_instant.sum()),
            "pairs_on_shared_instants_fraction": _round(
                float(pairs.shared_instant.mean()) if n else math.nan, 4
            ),
            "shared_possessions": int(sum(pairs.shared_possessions_per_match)),
            "pairs_in_shared_possessions": int(pairs.shared_possession.sum()),
            "pairs_in_shared_possessions_fraction": _round(
                float(pairs.shared_possession.mean()) if n else math.nan, 4
            ),
        },
    }


def _units_section(probes: Sequence[MatchProbe], pairs: _Pairs) -> dict[str, Any]:
    size = np.bincount(pairs.units) if pairs.units.size else np.zeros(0, dtype=np.intp)
    in_big = size[pairs.units] >= 2 if pairs.units.size else np.zeros(0, dtype=np.bool_)
    per_match = []
    for m, probe in enumerate(probes):
        mine = pairs.match_of_pair == m
        n = int(mine.sum())
        per_match.append(
            {
                "match_id": probe.match_id,
                "pairs": n,
                "units": pairs.units_per_match[m],
                "largest_unit": int(pairs.largest_unit_per_match[m]),
                "pairs_in_units_of_two_or_more_fraction": _round(
                    float(in_big[mine].mean()) if n else math.nan, 4
                ),
            }
        )
    return {
        "unit": (
            "the connected component, inside the match, of the pairs that share "
            "associated_player_possession_event_id or a placebo instant (same runner, same "
            "t'); the null flips the sign of every pair of a unit together, and never "
            "across matches (possession ids and frames repeat from match to match)"
        ),
        "per_match": per_match,
        "pooled": {
            "pairs": int(pairs.units.size),
            "units": int(sum(pairs.units_per_match)),
            "largest_unit": int(max(pairs.largest_unit_per_match, default=0)),
            "pairs_in_units_of_two_or_more_fraction": _round(
                float(in_big.mean()) if in_big.size else math.nan, 4
            ),
        },
    }


def _instrument_section(
    probes: Sequence[MatchProbe], pairs: _Pairs, placebo_sd_marker: float
) -> dict[str, Any]:
    rng = np.random.default_rng([SEED, STREAM_INSTRUMENT])
    verdict = bar_verdict(pairs.marker_m, pairs.units, pairs.match_of_pair, len(probes), rng)
    per_match = []
    for m, probe in enumerate(probes):
        mine = pairs.match_of_pair == m
        values = pairs.marker_m[mine]
        n = int(values.size)
        mean = float(values.mean()) if n else math.nan
        se = float(values.std(ddof=1) / math.sqrt(n)) if n > 1 else math.nan
        per_match.append(
            {
                "match_id": probe.match_id,
                "pairs": n,
                "mean_m": _round(mean, 4),
                "mean_sd": _round(mean / placebo_sd_marker, 4),
                "se_m": _round(se, 4),
            }
        )
    lines = []
    for probe in probes:
        own, prov = probe.line_at_tc_m, probe.provider_line_x_m
        ok = np.isfinite(own) & np.isfinite(prov)
        lines.append(
            {
                "match_id": probe.match_id,
                "runs_compared": int(ok.sum()),
                "pitch_length_m": probe.pitch_length_m,
                "pearson_r": _round(_pearson(own, prov), 4),
                "median_difference_m": _round(_quantile(own[ok] - prov[ok], 0.5), 3),
            }
        )
    own_all = np.concatenate([p.line_at_tc_m for p in probes])
    prov_all = np.concatenate([p.provider_line_x_m for p in probes])
    ok_all = np.isfinite(own_all) & np.isfinite(prov_all)
    difference_all = own_all[ok_all] - prov_all[ok_all]
    return {
        "marker": {
            "what": (
                "the quantity whose direction is forced: the marker's residual displacement "
                "along the run, run minus placebo, every run together (no subtype), per "
                "match and pooled, in metres and in placebo sd, against the bar"
            ),
            "per_match": per_match,
            "pooled": {
                "pairs": verdict.pairs,
                "units": verdict.units,
                "mean_m": _round(verdict.mean, 4),
                "mean_sd": _round(verdict.mean / placebo_sd_marker, 4),
                "same_sign_matches": verdict.same_sign_matches,
                "of_matches": verdict.of_matches,
                "p": _round(verdict.p, 5),
                "bar": {
                    "same_sign_matches_at_least": BAR_SAME_SIGN_MATCHES,
                    "of_matches": BAR_OF_MATCHES,
                    "p_at_most": BAR_P,
                },
                "passes_bar": verdict.passes,
            },
        },
        "line_against_provider": {
            "what": (
                "the protocol's line height at t_c (mean x_att of the two deepest outfield "
                "opponents) against the provider's last_defensive_line_height_start, turned "
                "to an x in the attack frame as pitch_length / 2 - height; a contrast of the "
                "instrument, never an outcome"
            ),
            "per_match": lines,
            "pooled": {
                "runs_compared": int(ok_all.sum()),
                "pearson_r": _round(_pearson(own_all, prov_all), 4),
                "median_difference_m": _round(_quantile(difference_all, 0.5), 3),
            },
        },
    }


def _null_section(probes: Sequence[MatchProbe], pairs: _Pairs) -> tuple[dict[str, Any], bool]:
    rates = null_fire_rates(
        pairs.marker_m,
        pairs.units,
        pairs.match_of_pair,
        pairs.subtype_of_pair,
        len(SUBTYPES),
        len(probes),
        np.random.default_rng([SEED, STREAM_NULL_OUTER]),
        np.random.default_rng([SEED, STREAM_NULL_INNER]),
    )
    n_pairs = np.bincount(pairs.subtype_of_pair, minlength=len(SUBTYPES))
    n_units = [
        len(set(pairs.units[pairs.subtype_of_pair == k].tolist())) for k in range(len(SUBTYPES))
    ]
    needed = rates.at_least_one_pct > NULL_AT_LEAST_ONE_MAX_PCT
    return {
        "what": (
            "the bar applied to null data sets: each is a sign flip of every unit inside its "
            "match, shared by the subtypes; per subtype, the sign count over the matches and "
            "a permutation p from fresh inner flips, as the real test; fires_pct is how often "
            "the whole bar passes on the marker quantity, fires_normal_pct the same with the "
            "p replaced by its normal approximation (the one the power simulation uses)"
        ),
        "quantity": "marker displacement along the run, run minus placebo",
        "draws": rates.draws,
        "n_permutations": N_PERMUTATIONS,
        "per_subtype": [
            {
                "subtype": s,
                "pairs": int(n_pairs[k]),
                "units": int(n_units[k]),
                "fires_pct": _round(rates.fires_pct[k], 2),
                "fires_normal_pct": _round(rates.fires_normal_pct[k], 2),
            }
            for k, s in enumerate(SUBTYPES)
        ],
        "at_least_one_pct": _round(rates.at_least_one_pct, 2),
        "at_least_one_normal_pct": _round(rates.at_least_one_normal_pct, 2),
        "hardening": {
            "rule": (
                f"if at_least_one_pct exceeds {NULL_AT_LEAST_ONE_MAX_PCT} the bar hardens "
                "once, in task 49, with the figure written in the protocol's history; it "
                "never loosens"
            ),
            "threshold_pct": NULL_AT_LEAST_ONE_MAX_PCT,
            "needed": needed,
        },
    }, needed


def _power_section(
    pairs: _Pairs,
    counts: dict[int, MatchCounts],
    halves: dict[str, list[int]],
    sds: dict[str, float],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    rng = np.random.default_rng([SEED, STREAM_POWER])
    effects = {
        "marker": design_effect(pairs.marker_m, pairs.units),
        "line": design_effect(pairs.line_m, pairs.units),
    }
    rows: list[dict[str, Any]] = []
    mde: dict[tuple[str, str, str], float | None] = {}
    for k, subtype in enumerate(SUBTYPES):
        for half, ids in halves.items():
            units_per_match = [list(counts[m].analysis_units[k]) for m in ids]
            row: dict[str, Any] = {
                "subtype": subtype,
                "half": half,
                "pairs": int(sum(sum(u) for u in units_per_match)),
                "units": int(sum(len(u) for u in units_per_match)),
                "matches_with_pairs": int(sum(1 for u in units_per_match if u)),
            }
            for quantity in ("marker", "line"):
                power = mde80(
                    units_per_match,
                    sd_pair=sds[f"pair_sd_{quantity}_m"],
                    rho=effects[quantity].rho,
                    sd_placebo=sds[f"placebo_sd_{quantity}_m"],
                    rng=rng,
                )
                mde[(subtype, half, quantity)] = power.mde80_sd
                row[f"mde80_{quantity}_sd"] = power.mde80_sd
                row[f"mde80_{quantity}_m"] = (
                    None
                    if power.mde80_sd is None
                    else _round(power.mde80_sd * sds[f"placebo_sd_{quantity}_m"], 3)
                )
                row[f"pass_rate_by_effect_{quantity}"] = [
                    _round(r, 3) for r in power.pass_rate_by_effect
                ]
            rows.append(row)

    lists = probable_subtypes(mde, halves)
    section = {
        "what": (
            "MDE80 per subtype and half: the smallest effect of the grid, in placebo sd, "
            "that passes the bar in at least 80 % of simulated data sets; each pair carries "
            "the effect plus noise with the pooled sd of the pair values and the measured "
            "within-unit correlation, on the unit sizes of the half's matches (the closed "
            "half contributes counts and nothing else); the p by its normal approximation"
        ),
        "grid_sd": list(MDE_GRID_SD),
        "replications": POWER_REPLICATIONS,
        "target_pass_rate": POWER_TARGET,
        "z_two_sided": _round(Z_TWO_SIDED, 4),
        "design_effect": {
            quantity: {
                "rho_within_unit": _round(e.rho, 4),
                "units_of_two_or_more": e.units_of_two_or_more,
                "pairs_of_pairs": e.pairs_of_pairs,
            }
            for quantity, e in effects.items()
        },
        "rows": rows,
        "probable": {
            "rule": (
                f"MDE80 at most {TESTABILITY_MDE80_SD} placebo sd in both halves; M1 counts "
                "the marker quantity, the forced-direction instrument; the line and the "
                "intersection are listed alongside"
            ),
            "mde80_sd_at_most": TESTABILITY_MDE80_SD,
            **lists,
        },
    }
    return section, lists


def build_probe(data_dir: Path, head: str) -> dict[str, Any]:
    """The whole file for the warehouse under `data_dir`: values of the calibration half
    through `MatchTracking`, counts of both halves through `count_tracking`."""
    calibration = load_half(HALF)
    others = [m for m in counting_match_ids() if m not in calibration]
    probes: list[MatchProbe] = []
    for match_id in calibration:
        probes.append(probe_match(load_tracking(data_dir, match_id), data_dir))
    counts = {m: count_tracking(data_dir, m) for m in (*calibration, *others)}
    for probe in probes:
        c = counts[probe.match_id]
        from_pairs = units_by_subtype(
            [p.subtype for p in probe.pairs], [pair_unit_key(p) for p in probe.pairs]
        )
        if len(probe.pairs) != c.analysis_set or from_pairs != c.analysis_units:
            raise ProbeInputError(
                f"match {probe.match_id}: {len(probe.pairs)} pairs against an analysis set "
                f"of {c.analysis_set}, or their units differ from the counts"
            )
    pairs = _collect(probes)
    sds = {
        "placebo_sd_marker_m": float(pairs.placebo_marker_m.std(ddof=1)),
        "placebo_sd_line_m": float(pairs.placebo_line_m.std(ddof=1)),
        "pair_sd_marker_m": float(pairs.marker_m.std(ddof=1)),
        "pair_sd_line_m": float(pairs.line_m.std(ddof=1)),
    }
    null_section, hardening_needed = _null_section(probes, pairs)
    power_section, probable = _power_section(
        pairs, counts, {HALF: calibration, "other": others}, sds
    )
    instrument = _instrument_section(probes, pairs, sds["placebo_sd_marker_m"])
    m1_dies = len(probable["marker"]) < 2
    m2_dies = not instrument["marker"]["pooled"]["passes_bar"]
    protocol = committed_protocol()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "plan": "tasks/todo.md, P5 'The run that moves nobody'",
        "protocol": {
            "stage": protocol["stage"],
            "fingerprint": protocol["fingerprint"],
            "content_sha256": protocol["content_sha256"],
        },
        "probe": {
            "task": TASK,
            "written": WRITTEN,
            "head": head,
            "half": HALF,
            "matches": calibration,
            "seed": SEED,
            "seed_streams": {
                "instrument": STREAM_INSTRUMENT,
                "null_outer": STREAM_NULL_OUTER,
                "null_inner": STREAM_NULL_INNER,
                "power": STREAM_POWER,
            },
            "funnel": {
                "what": (
                    "runs and pairs of the analysis set per match, both halves, from "
                    "count_tracking (counts; the calibration pairs are cross-checked against "
                    "the pairs the estimator formed)"
                ),
                "per_match": [
                    {
                        "match_id": m,
                        "half": HALF if m in calibration else "other",
                        "runs": counts[m].runs,
                        "pairs": counts[m].analysis_set,
                        "pairs_by_subtype": {
                            s: int(sum(counts[m].analysis_units[k])) for k, s in enumerate(SUBTYPES)
                        },
                    }
                    for m in (*calibration, *others)
                ],
                "total": {
                    HALF: {
                        "runs": sum(counts[m].runs for m in calibration),
                        "pairs": sum(counts[m].analysis_set for m in calibration),
                    },
                    "other": {
                        "runs": sum(counts[m].runs for m in others),
                        "pairs": sum(counts[m].analysis_set for m in others),
                    },
                },
            },
            "cadence": _cadence_section(probes),
            "run_length": _length_section(probes),
            "placebo_design": _placebo_design_section(probes, pairs),
            "units": _units_section(probes, pairs),
            "standardisation": {
                "what": (
                    "sd of the placebo leg's values pooled over the calibration half, the "
                    "unit of every standardised effect from here on, fixed and never "
                    "recomputed; the sd of the pair values (run minus placebo) alongside, "
                    "the noise the power simulates"
                ),
                "pairs": int(pairs.marker_m.size),
                **{k: _round(v, 4) for k, v in sds.items()},
            },
            "instrument": instrument,
            "null": null_section,
            "power": power_section,
            "verdict": {
                "M1": {
                    "rule": "fewer than 2 probable subtypes -> P5 dies",
                    "probable_subtypes": len(probable["marker"]),
                    "probable_by_line": len(probable["line"]),
                    "probable_by_both": len(probable["both"]),
                    "needs_at_least": 2,
                    "dies": m1_dies,
                },
                "M2": {
                    "rule": "the instrument does not pass the bar in calibration -> P5 dies",
                    "instrument_passes_bar": not m2_dies,
                    "dies": m2_dies,
                },
                "bar_hardening_needed": hardening_needed,
                "alive": not (m1_dies or m2_dies),
            },
        },
    }
    return seal(payload)


# --- the command --------------------------------------------------------------------------


def probe_path(reports_dir: Path) -> Path:
    return reports_dir / PROBE_NAME


def consistency_problems(current: dict[str, Any]) -> list[str]:
    """What a file must satisfy whatever warehouse is at hand: the seal, the protocol it
    answers to (the one committed in HEAD), the match list, and a verdict that follows from
    its own figures."""
    problems: list[str] = []
    if not sealed(current):
        problems.append("content_sha256 does not cover the file")
    protocol = committed_protocol()
    for key in ("stage", "fingerprint", "content_sha256"):
        if current.get("protocol", {}).get(key) != protocol[key]:
            problems.append(f"protocol.{key} is not the committed protocol's")
    probe = current.get("probe", {})
    if probe.get("matches") != load_half(HALF):
        problems.append("matches are not the calibration half")
    try:
        pooled = probe["instrument"]["marker"]["pooled"]
        passes = pooled["same_sign_matches"] >= BAR_SAME_SIGN_MATCHES and pooled["p"] <= BAR_P
        if pooled["passes_bar"] != passes:
            problems.append("instrument.marker.pooled.passes_bar does not follow its figures")
        rows = probe["power"]["rows"]
        halves = sorted({r["half"] for r in rows})
        probable = [
            s
            for s in SUBTYPES
            if all(
                any(
                    r["subtype"] == s
                    and r["half"] == h
                    and r["mde80_marker_sd"] is not None
                    and r["mde80_marker_sd"] <= TESTABILITY_MDE80_SD
                    for r in rows
                )
                for h in halves
            )
        ]
        if probe["power"]["probable"]["marker"] != probable:
            problems.append("power.probable.marker does not follow the rows")
        verdict = probe["verdict"]
        if verdict["M1"]["probable_subtypes"] != len(probable) or verdict["M1"]["dies"] != (
            len(probable) < 2
        ):
            problems.append("verdict.M1 does not follow power.probable")
        if verdict["M2"]["dies"] != (not pooled["passes_bar"]):
            problems.append("verdict.M2 does not follow the instrument")
        if verdict["alive"] != (not verdict["M1"]["dies"] and not verdict["M2"]["dies"]):
            problems.append("verdict.alive does not follow M1 and M2")
        needed = probe["null"]["at_least_one_pct"] > NULL_AT_LEAST_ONE_MAX_PCT
        if probe["null"]["hardening"]["needed"] != needed or (
            verdict["bar_hardening_needed"] != needed
        ):
            problems.append("the hardening flag does not follow null.at_least_one_pct")
    except (KeyError, TypeError) as exc:
        problems.append(f"the probe section is incomplete: {exc!r}")
    return problems


def _summary(payload: dict[str, Any], status: str) -> str:
    probe = payload["probe"]
    pooled = probe["instrument"]["marker"]["pooled"]
    verdict = probe["verdict"]
    return (
        f"runs probe: warehouse={status} matches={len(probe['matches'])} "
        f"pairs={pooled['pairs']} units={pooled['units']} "
        f"instrument_mean_m={pooled['mean_m']} same_sign={pooled['same_sign_matches']}/"
        f"{pooled['of_matches']} p={pooled['p']} passes_bar={pooled['passes_bar']} "
        f"null_at_least_one_pct={probe['null']['at_least_one_pct']} "
        f"probable={verdict['M1']['probable_subtypes']} "
        f"M1_dies={verdict['M1']['dies']} M2_dies={verdict['M2']['dies']} "
        f"hardening_needed={verdict['bar_hardening_needed']}"
    )


def run_runs_probe(data_dir: Path, reports_dir: Path, *, check: bool = False) -> int:
    calibration = load_half(HALF)
    every = counting_match_ids()
    at_hand = [m for m in calibration if has_frames(data_dir, m)]
    whole = all(has_frames(data_dir, m) for m in every)
    path = probe_path(reports_dir)
    if not check:
        if not whole:
            print(
                f"runs probe: silver frames for {len(at_hand)} of the {len(calibration)} "
                f"calibration matches under {data_dir} (and the counts need all "
                f"{len(every)}); the file is written from all of them or not at all"
            )
            return 1
        payload = build_probe(data_dir, head=head_commit())
        reports_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(render(payload), encoding="utf-8", newline="\n")
        print(_summary(payload, status=f"FULL {len(calibration)}/{len(calibration)}"))
        print(f"runs probe: {path} ({path.stat().st_size} bytes)")
        return 0 if not payload["probe"]["verdict"]["bar_hardening_needed"] else 2
    if not path.is_file():
        print(f"runs probe --check: {path} missing")
        return 1
    text = path.read_text(encoding="utf-8")
    current = json.loads(text)
    problems = consistency_problems(current)
    if whole and not problems:
        expected = build_probe(data_dir, head=str(current["probe"]["head"]))
        if render(expected) != text:
            problems.append("differs from what the code writes")
        status = f"FULL {len(calibration)}/{len(calibration)} recomputed and equal"
    else:
        status = f"PARTIAL {len(at_hand)}/{len(calibration)} (figures as written)"
    if problems:
        print(f"runs probe --check: {path} " + "; ".join(problems))
        return 1
    print(_summary(current, status=status))
    print(f"runs probe --check: {path} matches ({status})")
    return 0
