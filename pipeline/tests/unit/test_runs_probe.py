"""`tracklab runs probe`, death probe 1 of P5 (task 49).

The null, the bar and the power are tested on fabricated pairs where the answer is known;
the whole command on a synthetic warehouse of 20 matches (the committed split's ids) with a
planted effect, and once without. Real data enters only through the versioned
`runs_calibration.json`: its seal, its consistency with the protocol committed in HEAD and
with `runs_coverage.csv`, and, where the whole warehouse is at hand, its recomputation.

Mutations recorded in tasks/todo.md: units labelled over the pairs of every match at once
(a possession id repeats from match to match, so the null would mix matches) fails the
two-match test, where that null fires on no effect; one unit per pair (clusters counted as
independent) fails the clustered test the same way; outer flips drawn per subtype fail the
shared-flip test; `argmax` for the cadence fails the five-frame slope test. Since the review
of task 49: outer flips by the units instead of the blocks fail the hidden-blocks test (the
null then cannot see what the units miss); the power passing on the normal quantile instead
of the bar's count fails the two permutation tests; the write-mode refusal removed fails the
uncommitted-code test; a fixed 52.5 in the provider conversion fails the planted test on its
non-105 m pitches.
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_runs_windows import (  # the synthetic match and the throwaway design repo of task 48
    CI_FIXTURE_MATCH,
    PLANTED_LINE_M,
    PLANTED_MARKER_M,
    _git,
    _guarded,
    _synthetic_raw,
    _write_warehouse,
    design_repo,  # noqa: F401  (a fixture)
    needs_the_whole_warehouse,
)

from tracklab.cli import build_parser
from tracklab.paths import data_root
from tracklab.runs import data, probe, windows
from tracklab.runs.coverage import COVERAGE_NAME
from tracklab.runs.data import counting_match_ids, load_half
from tracklab.runs.probe import (
    BAR_COUNT_AT_MOST,
    PROBE_NAME,
    Z_TWO_SIDED,
    MatchProbe,
    ProbeInputError,
    bar_pass_probability,
    bar_verdict,
    cadence,
    cadence_lag,
    consistency_problems,
    design_effect,
    mde80,
    normal_two_sided_tail,
    null_fire_rates,
    permutation_p,
    probable_subtypes,
    run_runs_probe,
    unit_sums,
)
from tracklab.runs.protocol import (
    BAR_P,
    BAR_SAME_SIGN_MATCHES,
    BAR_Z,
    N_PERMUTATIONS,
    NULL_AT_LEAST_ONE_MAX_PCT,
    TESTABILITY_MDE80_SD,
    read_protocol,
    seal,
    sealed,
    z_two_sided,
)
from tracklab.runs.windows import (
    SUBTYPES,
    PairEffect,
    components,
    unit_labels,
    units_by_subtype,
)

PIPELINE = Path(__file__).resolve().parents[2]
REPORTS = PIPELINE / "reports"
PROBE_FILE = REPORTS / PROBE_NAME
SRC = PIPELINE / "src" / "tracklab" / "runs"


# --- units ----------------------------------------------------------------------------------


def test_unit_labels_link_by_possession_and_by_instant_and_chain() -> None:
    keys = [
        ("p1", (7, 100)),  # 0
        ("p1", (7, 200)),  # 1: shares p1 with 0
        ("p2", (7, 200)),  # 2: shares the instant with 1 -> one unit with 0 and 1
        ("p3", (8, 300)),  # 3: alone
        (None, (9, 400)),  # 4: no possession, alone
        (None, (9, 400)),  # 5: no possession, shares the instant with 4
        (None, (9, 500)),  # 6: no possession, alone (None never links)
    ]
    assert unit_labels(keys) == [0, 0, 0, 1, 2, 2, 3]
    assert unit_labels([]) == []
    # the union-find beneath it, over any keys: a third key per item links what the two
    # of the unit do not (the blocks of the real null add (runner, period) this way)
    assert components([("a",), ("b",), ("c", "a"), ()]) == [0, 1, 0, 2]
    assert components([("a", "x"), ("b", "x"), ("c",)]) == [0, 0, 1]
    # every key links, the third and the fourth too (the null's units carry three, its
    # blocks four): two items alike in their third key only are one component
    assert components([("a", "b", "x"), ("c", "d", "x"), ("e", "f", "g", "d")]) == [0, 0, 0]
    assert components([("a", "b", "x"), ("c", "d", "y")]) == [0, 1]
    assert components([]) == []


def test_units_by_subtype_gives_sorted_sizes_per_protocol_subtype() -> None:
    keys = [("p1", (7, 1)), ("p1", (7, 2)), ("p2", (8, 3)), ("p3", (8, 4)), ("p3", (8, 5))]
    subtypes = ["behind", "support", "behind", "behind", "behind"]
    sizes = units_by_subtype(subtypes, keys)
    assert sizes[SUBTYPES.index("behind")] == (1, 1, 2)  # p1 (1 behind), p2, p3 (2)
    assert sizes[SUBTYPES.index("support")] == (1,)
    assert all(sizes[k] == () for k, s in enumerate(SUBTYPES) if s not in ("behind", "support"))


# --- the bar and its p ---------------------------------------------------------------------


def test_z_two_sided_is_the_normal_quantile() -> None:
    assert z_two_sided(0.05) == pytest.approx(1.959964, abs=1e-5)
    assert Z_TWO_SIDED == BAR_Z == z_two_sided(BAR_P) == pytest.approx(3.2051, abs=1e-3)
    # the protocol's z_equivalent is this quantile, not the 3.0 of a one-sided 0.00135
    assert read_protocol(REPORTS / "runs_protocol.json")["design"]["bar"]["calibration"][
        "z_equivalent"
    ] == round(BAR_Z, 4)


def test_permutation_p_counts_the_two_sided_tail_with_the_plus_one() -> None:
    flipped = np.array([-3.0, -1.0, 0.5, 2.0, 4.0])
    assert permutation_p(2.0, flipped) == (1 + 3) / 6  # |-3|, |2|, |4| >= 2
    assert permutation_p(10.0, flipped) == 1 / 6
    assert permutation_p(0.0, flipped) == 1.0


def _grid(
    n_matches: int, units_per_match: int, size: int, value: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`n_matches` x `units_per_match` units of `size` identical pairs at `value` plus noise."""
    values, units, matches, u = [], [], [], 0
    for m in range(n_matches):
        for _ in range(units_per_match):
            v = value + rng.normal(0.0, 0.1)
            values += [v] * size
            units += [u] * size
            matches += [m] * size
            u += 1
    return np.array(values), np.array(units, dtype=np.intp), np.array(matches, dtype=np.intp)


def test_bar_verdict_needs_the_sign_in_eight_matches_and_the_p() -> None:
    rng = np.random.default_rng(1)
    values, units, matches = _grid(10, 30, 1, 1.0, rng)
    verdict = bar_verdict(values, units, matches, 10, np.random.default_rng(2))
    assert verdict.pairs == verdict.units == 300
    assert verdict.p == 1 / (1 + N_PERMUTATIONS)
    assert verdict.same_sign_matches == 10 and verdict.passes
    # three matches against: the pooled sign still positive, the sign count 7 -> fails
    against = values.copy()
    against[matches >= 7] *= -1.0
    verdict = bar_verdict(against, units, matches, 10, np.random.default_rng(2))
    assert verdict.same_sign_matches == 7 == BAR_SAME_SIGN_MATCHES - 1
    assert verdict.mean > 0 and not verdict.passes
    # all ten agree but nothing there: the p is the whole story
    noise = rng.normal(0.0, 1.0, 300)
    noise[matches == 0] = np.abs(noise[matches == 0])  # keep every match mean positive
    for m in range(1, 10):
        noise[matches == m] += 0.5
    verdict = bar_verdict(noise, units, matches, 10, np.random.default_rng(3))
    assert verdict.same_sign_matches == 10
    assert verdict.passes == (verdict.p <= BAR_P)


def _probe_of(
    match_id: int, pairs: list[PairEffect], second_marker: np.ndarray | None = None
) -> MatchProbe:
    """A `MatchProbe` with the pairs: what `_collect` reads, and, given `second_marker` (the
    marker quantity of a second placebo per pair, at t'1 + 5 in the placebo's period), what
    `_collect_null` reads too. Every run in period 1: one runner, one period, one block."""
    empty = np.zeros(0)
    n = len(pairs)
    has_second = second_marker is not None
    return MatchProbe(
        match_id=match_id,
        runs=n,
        pairs=tuple(pairs),
        run_period=np.ones(n, dtype=np.int64),
        placebo2_period=np.array(
            [p.placebo_period if has_second else -1 for p in pairs], dtype=np.int64
        ),
        placebo2_instant=np.array(
            [p.placebo_instant + 5 if has_second else -1 for p in pairs], dtype=np.int64
        ),
        placebo2_marker_m=np.full(n, np.nan) if second_marker is None else second_marker,
        placebo2_line_m=np.full(n, np.nan),
        length_m=empty,
        line_at_tc_m=empty,
        provider_line_x_m=empty,
        pitch_length_m=104.0,
        provider_identity_residual_half_length_m=0.0,
        provider_identity_residual_52_5_m=0.5,
        runner_in_possession_at_placebo=np.zeros(n, dtype=np.bool_),
        cadence=probe.Cadence(0, 0, 0, math.nan, (0.0,) * 30, 0.0),
    )


def _pair(match_id: int, i: int, possession: str | None, instant: int, value: float) -> PairEffect:
    return PairEffect(
        match_id=match_id,
        run_id=f"r{i}",
        possession_id=possession,
        subtype=SUBTYPES[i % len(SUBTYPES)],
        player_id=7,
        t_c=10 * i,
        placebo_period=1,
        placebo_instant=instant,
        marker_m=value,
        line_m=value,
        placebo_marker_m=0.0,
        placebo_line_m=0.0,
    )


def test_the_null_never_mixes_matches() -> None:
    """Two fabricated matches of different means whose possession ids repeat (as the
    provider's do, `8_1` in every match): inside each match the units are singletons, the
    pooled effect is small against its null and the bar does not fire; a null that labels
    the units over both matches at once merges each possession across them, the unit sums
    cancel, the null collapses and the same data fires (p at the floor). The mutation of the
    plan, 'barajar entre partidos en vez de dentro', is that labelling."""
    rng = np.random.default_rng(49)
    a = [_pair(1, i, f"8_{i}", 1000 + 10 * i, 1.0 + rng.normal(0, 0.1)) for i in range(100)]
    b = [_pair(2, i, f"8_{i}", 1000 + 10 * i, -0.8 + rng.normal(0, 0.1)) for i in range(100)]
    pairs = probe._collect([_probe_of(1, a), _probe_of(2, b)])
    # the units of the two matches are disjoint, whatever their keys
    assert set(pairs.units[pairs.match_of_pair == 0]).isdisjoint(
        set(pairs.units[pairs.match_of_pair == 1])
    )
    assert len(set(pairs.units.tolist())) == 200
    inside = bar_verdict(
        pairs.marker_m, pairs.units, pairs.match_of_pair, 2, np.random.default_rng(1)
    )
    assert inside.mean == pytest.approx(0.1, abs=0.03)
    assert inside.p > 0.05 and not inside.passes
    # the across-match null: one labelling over both matches
    across = np.array(unit_labels([windows.pair_unit_key(p) for p in (*a, *b)]), dtype=np.intp)
    assert len(set(across.tolist())) == 100  # every possession merged across the matches
    mixed = bar_verdict(pairs.marker_m, across, pairs.match_of_pair, 2, np.random.default_rng(1))
    assert mixed.p == 1 / (1 + N_PERMUTATIONS) <= BAR_P  # fires on nothing


def test_pairs_of_a_unit_are_not_counted_as_independent() -> None:
    """Ten matches, twenty units of ten identical pairs each, eleven units up and nine down
    per match: the pooled z over the units is 1.41 and the bar does not fire; one unit per
    pair inflates it by sqrt(10) and fires. The trap of the plan's review list, 'carreras de
    una misma posesión contadas como independientes'."""
    probes = []
    for m in range(10):
        pairs = []
        for u in range(20):
            value = 1.0 if u < 11 else -1.0
            pairs += [_pair(m, 10 * u + j, f"8_{u}", 5000 + 100 * u, value) for j in range(10)]
        probes.append(_probe_of(m, pairs))
    pairs = probe._collect(probes)
    assert len(set(pairs.units.tolist())) == 200
    clustered = bar_verdict(
        pairs.marker_m, pairs.units, pairs.match_of_pair, 10, np.random.default_rng(5)
    )
    assert clustered.same_sign_matches == 10
    assert clustered.p > 0.05 and not clustered.passes
    independent = bar_verdict(
        pairs.marker_m,
        np.arange(pairs.units.size, dtype=np.intp),
        pairs.match_of_pair,
        10,
        np.random.default_rng(5),
    )
    assert independent.p <= BAR_P and independent.passes


# --- the real null ----------------------------------------------------------------------------


def _null_pairs(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Ten matches, every subtype, units of 1 to 3 pairs, no effect."""
    rng = np.random.default_rng(seed)
    values, units, matches, subtypes, u = [], [], [], [], 0
    for m in range(10):
        for _ in range(40):
            size = int(rng.integers(1, 4))
            shared = rng.normal(0.0, 0.5)
            for _ in range(size):
                values.append(shared + rng.normal(0.0, 1.0))
                units.append(u)
                matches.append(m)
                subtypes.append(int(rng.integers(0, len(SUBTYPES))))
            u += 1
    return (
        np.array(values),
        np.array(units, dtype=np.intp),
        np.array(matches, dtype=np.intp),
        np.array(subtypes, dtype=np.intp),
    )


def test_null_fire_rates_are_nominal_when_the_blocks_are_the_units() -> None:
    values, units, matches, subtypes = _null_pairs(7)
    rates = null_fire_rates(
        values,
        units,
        units,
        matches,
        subtypes,
        len(SUBTYPES),
        10,
        np.random.default_rng(1),
        np.random.default_rng(2),
        draws=1000,
    )
    assert rates.draws == 1000
    assert all(0.0 <= r <= 1.0 for r in rates.fires_pct)
    assert rates.at_least_one_pct <= NULL_AT_LEAST_ONE_MAX_PCT
    assert max(rates.fires_pct) <= rates.at_least_one_pct <= sum(rates.fires_pct)


def test_the_outer_flips_are_shared_by_the_subtypes() -> None:
    """Two subtypes with the same pairs in the same units fire on the same null draws, so 'at
    least one' equals each one's rate; outer flips drawn per subtype would not."""
    rng = np.random.default_rng(11)
    base = rng.normal(0.0, 1.0, 300)
    values = np.concatenate([base, base])
    units = np.concatenate([np.arange(300), np.arange(300)]).astype(np.intp)
    blocks = units // 3
    matches = np.concatenate([np.repeat(np.arange(10), 30)] * 2).astype(np.intp)
    subtypes = np.concatenate([np.zeros(300), np.ones(300)]).astype(np.intp)
    rates = null_fire_rates(
        values,
        units,
        blocks,
        matches,
        subtypes,
        2,
        10,
        np.random.default_rng(3),
        np.random.default_rng(4),
        draws=2000,
    )
    assert rates.fires_pct[0] == rates.fires_pct[1] == rates.at_least_one_pct


def test_the_null_section_centres_placebo_1_minus_placebo_2_per_subtype() -> None:
    """Ten fabricated matches of 60 pairs whose placebo 1 minus placebo 2 is 3 m plus noise
    in every pair, one runner in one period, so one block per match holding every unit:
    uncentred, every block carries the same sign and the outer flips make the inner test
    fire in a large share of the draws (the mutation that drops the centring); centred per
    subtype, with the means printed, the null is nominal. The unflipped contrast, on the
    raw difference, sees the 3 m in every subtype."""
    rng = np.random.default_rng(13)
    probes = []
    for m in range(10):
        pairs = [
            replace(
                _pair(m, i, f"p{i}", 1000 + 10 * i, 0.0), placebo_marker_m=3.0 + rng.normal(0, 0.5)
            )
            for i in range(60)
        ]
        probes.append(_probe_of(m, pairs, second_marker=rng.normal(0.0, 0.5, 60)))
    pairs_ = probe._collect(probes)
    section, needed = probe._null_section(probes, pairs_, probe._collect_null(probes))
    assert section["pooled"] == {
        "pairs": 600,
        "units": 600,
        "blocks": 10,
        "largest_block_share": 1.0,
    }
    assert section["pairs_with_second_placebo"] == section["of_pairs"] == 600
    assert section["gap_s_p50"] == section["gap_s_p90"]
    for row in section["per_subtype"]:
        assert row["pairs"] == row["units"] == 60 and row["blocks"] == 10
        assert abs(row["centring_mean_m"] - 3.0) < 0.3
        assert row["unflipped"]["passes_bar"] and row["unflipped"]["same_sign_matches"] == 10
    assert section["at_least_one_pct"] <= NULL_AT_LEAST_ONE_MAX_PCT and not needed


def _hidden_blocks(
    seed: int, correlated: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The reviewer's breaking case: ten matches of 240 pairs, every pair its own unit (what
    the labels say), but the true process puts six consecutive pairs in a block of one
    subtype whose values share a common term (correlation 0.5 inside the block) when
    `correlated`, and nothing anywhere else. No effect: every value has mean zero."""
    n_matches, per_match, block, corr = 10, 240, 6, 0.5
    rng = np.random.default_rng(seed)
    n = n_matches * per_match
    block_of = np.arange(n) // block
    n_blocks = int(block_of.max()) + 1
    subtypes = rng.integers(0, len(SUBTYPES), n_blocks)[block_of].astype(np.intp)
    if correlated:
        common = rng.normal(0.0, math.sqrt(corr), n_blocks)[block_of]
        values = common + rng.normal(0.0, math.sqrt(1.0 - corr), n)
    else:
        values = rng.normal(0.0, 1.0, n)
    return (
        values,
        np.arange(n, dtype=np.intp),
        block_of.astype(np.intp),
        np.repeat(np.arange(n_matches), per_match).astype(np.intp),
        subtypes,
    )


@pytest.mark.parametrize("seed", [1, 2])
def test_the_null_sees_a_dependence_the_units_miss_when_the_blocks_nest_it(seed: int) -> None:
    """With the fabricated blocks as the outer flips, the test on each draw (flipping the
    units alone, as the real test would) fires far above nominal, about 32 % 'at least
    one', which is what the real bar does on fresh data of that process (the reviewer
    measured 31.9 % against a 1.0 % the old null reported); without the hidden correlation
    the same blocks leave it near nominal; and outer flips by the units again (the old null)
    cannot see it, the mutation this test kills. Blocks that do not nest the units are
    refused."""
    values, units, blocks, matches, subtypes = _hidden_blocks(seed, correlated=True)
    n_subtypes = len(SUBTYPES)

    def rates(v: np.ndarray, u: np.ndarray, b: np.ndarray) -> float:
        r = null_fire_rates(v, u, b, matches, subtypes, n_subtypes, 10, rng(3), rng(4), draws=500)
        return r.at_least_one_pct

    def rng(k: int) -> np.random.Generator:
        return np.random.default_rng([seed, k])

    assert rates(values, units, blocks) > 3 * NULL_AT_LEAST_ONE_MAX_PCT
    assert rates(values, units, units) <= NULL_AT_LEAST_ONE_MAX_PCT
    plain, *_ = _hidden_blocks(seed, correlated=False)
    assert rates(plain, units, blocks) <= NULL_AT_LEAST_ONE_MAX_PCT
    with pytest.raises(ProbeInputError, match="nest"):
        rates(values, blocks, units)  # the units coarser than the blocks


# --- the power ----------------------------------------------------------------------------


def test_design_effect_is_the_within_unit_correlation() -> None:
    rng = np.random.default_rng(3)
    units = np.repeat(np.arange(500), 2).astype(np.intp)
    same = np.repeat(rng.normal(0.0, 1.0, 500), 2)
    assert design_effect(same, units).rho == pytest.approx(1.0)
    independent = rng.normal(0.0, 1.0, 1000)
    assert abs(design_effect(independent, units).rho) < 0.1
    singletons = design_effect(independent, np.arange(1000, dtype=np.intp))
    assert math.isnan(singletons.rho) and singletons.pairs_of_pairs == 0
    assert design_effect(same, units).units_of_two_or_more == 500


def test_bar_pass_probability_is_the_binomial_of_the_normal_tail() -> None:
    """At |z| = Z_TWO_SIDED the tail is BAR_P exactly, the expected count 2.7 of 2000, and
    the bar (count at most 1) passes about a quarter of the time; at z = 0 never; far out
    always; monotone in |z| and even in z."""
    assert BAR_COUNT_AT_MOST == 1 and (1 + 2) / (1 + N_PERMUTATIONS) > BAR_P
    assert normal_two_sided_tail(np.array([0.0, Z_TWO_SIDED])) == pytest.approx([1.0, BAR_P])
    q = 1.0 - BAR_P
    exact = q**N_PERMUTATIONS + N_PERMUTATIONS * BAR_P * q ** (N_PERMUTATIONS - 1)
    assert bar_pass_probability(np.array([Z_TWO_SIDED]))[0] == pytest.approx(exact, abs=1e-9)
    assert 0.2 < exact < 0.3
    assert bar_pass_probability(np.array([0.0]))[0] == 0.0
    assert bar_pass_probability(np.array([8.0]))[0] > 0.9999
    z = np.arange(0.0, 6.01, 0.2)
    p = bar_pass_probability(z)
    assert np.array_equal(p, bar_pass_probability(-z)) and (np.diff(p) >= 0).all()
    assert bar_pass_probability(np.array([3.34]))[0] == pytest.approx(0.5, abs=0.03)


def test_bar_pass_probability_matches_the_permutation_count_on_the_same_data_sets() -> None:
    """3000 data sets of 300 independent pairs with an effect of 0.2 sd (z about 3.5): the
    bar's permutation p from 2000 fresh flips of each, against the probability the helper
    assigns from the same z; the quantile alone passes a visible share of data sets whose
    count is 2 or more (the mutation that puts |z| >= Z_TWO_SIDED back)."""
    rng = np.random.default_rng(20)
    reps, n = 3000, 300
    y = rng.normal(0.0, 1.0, (reps, n)) + 0.2
    total = y.sum(axis=1)
    z = total / np.sqrt((y * y).sum(axis=1))
    passes = np.zeros(reps, dtype=np.bool_)
    for lo in range(0, reps, 100):
        flips = rng.integers(0, 2, size=(N_PERMUTATIONS, n)).astype(np.float64) * 2.0 - 1.0
        reference = flips @ y[lo : lo + 100].T  # (N_PERMUTATIONS, 100)
        count = (np.abs(reference) >= np.abs(total[lo : lo + 100])[None, :]).sum(axis=0)
        p = (1 + count) / (1 + N_PERMUTATIONS)
        assert np.array_equal(p <= BAR_P, count <= BAR_COUNT_AT_MOST)
        passes[lo : lo + 100] = p <= BAR_P
    assert 0.35 < passes.mean() < 0.75
    assert abs(passes.mean() - bar_pass_probability(z).mean()) < 0.025
    assert (np.abs(z) >= Z_TWO_SIDED).mean() - passes.mean() > 0.03


def test_mde80_passes_by_the_bars_count_not_the_normal_quantile() -> None:
    """Ten matches of 30 independent pairs at 0.2 sd: the pass rate `mde80` reports is the
    one the bar's count gives (the helper's probability times the sign count, on an
    independent draw of the same model), and strictly below what the normal quantile alone
    would give."""
    sizes = [[1] * 30] * 10
    power = mde80(
        sizes,
        sd_pair=1.0,
        rho=0.0,
        sd_placebo=1.0,
        rng=np.random.default_rng(1),
        replications=20000,
    )
    rate = power.pass_rate_by_effect[probe.MDE_GRID_SD.index(0.2)]
    rng = np.random.default_rng(2)
    y = rng.normal(0.0, 1.0, (20000, 300)) + 0.2
    total = y.sum(axis=1)
    z = total / np.sqrt((y * y).sum(axis=1))
    per_match = y.reshape(20000, 10, 30).sum(axis=2)
    sign_ok = (np.sign(per_match) == np.sign(total)[:, None]).sum(axis=1) >= BAR_SAME_SIGN_MATCHES
    reference = float((bar_pass_probability(z) * sign_ok).mean())
    quantile = float(((np.abs(z) >= Z_TWO_SIDED) & sign_ok).mean())
    assert 0.4 < rate < 0.8
    assert abs(rate - reference) < 0.02
    assert quantile - rate > 0.03


def test_mde80_falls_with_pairs_and_rises_with_clustering() -> None:
    few = mde80([[1] * 20] * 10, sd_pair=1.0, rho=0.0, sd_placebo=1.0, rng=np.random.default_rng(1))
    many = mde80(
        [[1] * 200] * 10, sd_pair=1.0, rho=0.0, sd_placebo=1.0, rng=np.random.default_rng(1)
    )
    assert few.pairs == 200 and many.pairs == 2000
    assert few.mde80_sd is not None and many.mde80_sd is not None
    assert many.mde80_sd < few.mde80_sd
    assert list(many.pass_rate_by_effect) == sorted(many.pass_rate_by_effect)  # monotone
    assert many.pass_rate_by_effect[0] < 0.5  # 0.05 sd on 2000 pairs: z about 2.2
    clustered = mde80(
        [[5] * 40] * 10, sd_pair=1.0, rho=0.9, sd_placebo=1.0, rng=np.random.default_rng(1)
    )
    assert clustered.pairs == 2000 and clustered.units == 400
    assert clustered.mde80_sd is not None and clustered.mde80_sd > many.mde80_sd
    # in metres the effect is the placebo sd times d: a wider pair sd needs a larger d
    wide = mde80(
        [[1] * 200] * 10, sd_pair=2.0, rho=0.0, sd_placebo=1.0, rng=np.random.default_rng(1)
    )
    assert wide.mde80_sd is not None and wide.mde80_sd > many.mde80_sd
    none = mde80([[]] * 10, sd_pair=1.0, rho=0.0, sd_placebo=1.0, rng=np.random.default_rng(1))
    assert none.mde80_sd is None and none.pairs == 0
    tiny = mde80([[1]] * 10, sd_pair=1.0, rho=0.0, sd_placebo=1.0, rng=np.random.default_rng(1))
    assert tiny.mde80_sd is None  # ten pairs never reach z 3.2 at 0.8 sd 80 % of the time


# --- the cadence ----------------------------------------------------------------------------


def _slope_change_every(frames: int, period: int, seed: int) -> windows.MatchTracking:
    """Two players whose positions are piecewise linear on a 1 cm grid, the slope changing
    every `period` frames: null second differences between knots, a spike at each knot."""
    rng = np.random.default_rng(seed)
    x = np.zeros((frames, 2))
    y = np.zeros((frames, 2))
    for j in range(2):
        vx = np.repeat(rng.integers(-30, 31, size=frames // period + 1), period)[:frames] / 100.0
        vy = np.repeat(rng.integers(-30, 31, size=frames // period + 1), period)[:frames] / 100.0
        x[:, j] = np.round(np.cumsum(vx), 2)
        y[:, j] = np.round(np.cumsum(vy), 2)
    return _guarded(
        windows._Tracking(
            match_id=CI_FIXTURE_MATCH,
            frame0=0,
            x=x,
            y=y,
            detected=np.ones((frames, 2), dtype=np.bool_),
            entities=("fb:1", "fb:2"),
            team=("fb:100", "fb:200"),
            is_goalkeeper=np.array([False, False]),
            period_frames={1: (0, frames - 1)},
            attack_sign={(1, "fb:100"): 1, (1, "fb:200"): -1},
        )
    )


def test_probable_counts_the_threshold_itself_both_halves_and_the_marker() -> None:
    """MDE80 sits on a 0.05 grid that holds 0.3 itself (`coming_short` lands there in
    calibration): on the threshold counts. A subtype testable in one half only, or on the
    line only, stays out of the marker list M1 counts."""
    assert TESTABILITY_MDE80_SD in probe.MDE_GRID_SD
    halves = ("calibration", "held_out")
    on_threshold, line_only, one_half = SUBTYPES[0], SUBTYPES[1], SUBTYPES[2]
    mde: dict[tuple[str, str, str], float | None] = {
        (s, h, q): None for s in SUBTYPES for h in halves for q in ("marker", "line")
    }
    for h in halves:
        mde[(on_threshold, h, "marker")] = mde[(on_threshold, h, "line")] = TESTABILITY_MDE80_SD
        mde[(line_only, h, "line")] = 0.2
        mde[(line_only, h, "marker")] = 0.35
    mde[(one_half, "calibration", "marker")] = 0.2
    mde[(one_half, "held_out", "marker")] = 0.35
    assert probable_subtypes(mde, halves) == {
        "marker": [on_threshold],
        "line": [on_threshold, line_only],
        "both": [on_threshold],
    }


def test_cadence_sees_a_slope_change_every_five_frames() -> None:
    t = _slope_change_every(2000, 5, seed=5)
    c = cadence(t)
    assert c.triples == 2 * 1998
    # positions on a 1 cm grid as floats: a null second difference is below half the grid
    # far more often than exactly 0.0 (1e-18 leftovers), the two figures the file reports
    assert c.below_half_grid / c.triples == pytest.approx(0.8, abs=0.01)
    assert c.exactly_zero <= c.below_half_grid
    assert c.grid_m == pytest.approx(0.01)
    ac = probe.pooled_autocorrelation([c])
    assert cadence_lag(ac) == 5  # not 10 or 15, where a periodic train peaks just as high
    assert ac[4] > ac[3] and ac[4] > ac[0]
    assert cadence_lag([0.9, 0.8, 0.7, 0.6]) == 1  # a curve that only decays
    assert cadence_lag([0.51, 0.58, 0.49, 0.43]) == 2
    assert cadence_lag([0.5, 0.4, 0.45, 0.46, 0.2]) == 4
    assert cadence_lag([0.5, 0.6, 0.55, 0.5, 0.9, 0.4]) == 2  # the first, not the highest


# --- the command on a synthetic warehouse ---------------------------------------------------


def _synthetic_warehouse(root: Path, marker: float, line: float) -> list[int]:
    """Twenty synthetic matches under the committed split's ids, 30 runs each with their
    placebo candidates in the events; returns the calibration ids."""
    calibration = load_half("calibration")
    for i, match_id in enumerate(counting_match_ids()):
        raw, runs, instants = _synthetic_raw(30, marker, line, seed=100 + i, match_id=match_id)
        _write_warehouse(root, raw, runs, instants, pitch_length=_pitch_length(i))
    return calibration


def _pitch_length(i: int) -> float:
    """100, 102, 104 and 106 m around the ids, never 105: a reader converting the provider's
    height with a fixed 52.5 lands 0.5 to 2.5 m off the x the provider wrote."""
    return 100.0 + 2.0 * (i % 4)


def _keys(node: object) -> set[str]:
    """Every key of a JSON tree: what a section may hold, whatever its prose says."""
    if isinstance(node, dict):
        return set(node) | set().union(*(_keys(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(_keys(v) for v in node))
    return set()


def _written(tmp_path: Path, marker: float, line: float) -> tuple[Path, Path, dict[str, object]]:
    root, reports = tmp_path / "data", tmp_path / "reports"
    _synthetic_warehouse(root, marker, line)
    assert run_runs_probe(root, reports) == 0
    return root, reports, json.loads((reports / PROBE_NAME).read_text(encoding="utf-8"))


@pytest.mark.usefixtures("design_repo")
def test_the_probe_on_a_planted_effect_passes_m2_and_check_reproduces_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, reports, payload = _written(tmp_path, PLANTED_MARKER_M, PLANTED_LINE_M)
    assert sealed(payload)
    assert consistency_problems(payload) == []
    p = payload["probe"]
    assert p["matches"] == load_half("calibration") and p["half"] == "calibration"
    assert len(p["head"]) == 40 and len(p["code_tree_sha"]) == 40
    committed = read_protocol(PIPELINE / "reports" / "runs_protocol.json")
    assert payload["protocol"]["fingerprint"] == committed["fingerprint"]
    # the funnel: 30 runs and 30 pairs per match, both halves, three per subtype
    assert len(p["funnel"]["per_match"]) == 20
    for row in p["funnel"]["per_match"]:
        assert row["runs"] == row["pairs"] == 30
        assert set(row["pairs_by_subtype"].values()) == {3}
    assert p["funnel"]["total"] == {
        "calibration": {"runs": 300, "pairs": 300},
        "other": {"runs": 300, "pairs": 300},
    }
    # the instrument: the planted 2 m, every match, p at the floor
    pooled = p["instrument"]["marker"]["pooled"]
    assert pooled["pairs"] == pooled["units"] == 300
    assert abs(pooled["mean_m"] - PLANTED_MARKER_M) < 0.1
    assert pooled["same_sign_matches"] == 10 and pooled["p"] == round(1 / (1 + N_PERMUTATIONS), 5)
    assert pooled["passes_bar"] and not p["verdict"]["M2"]["dies"]
    # the line against the provider: the provider wrote the x of the same geometry, so r is
    # 1 and the difference 0 on every pitch length; its identity holds with the match's
    # half length and misses a fixed 52.5 by |L / 2 - 52.5| (0.5 to 2.5 m: no 105 m pitch)
    ids = counting_match_ids()
    for row in p["instrument"]["line_against_provider"]["per_match"]:
        length = _pitch_length(ids.index(row["match_id"]))
        assert row["runs_compared"] == 30 and row["pitch_length_m"] == length != 105.0
        assert row["identity_max_residual_half_length_m"] == 0.0
        assert row["identity_max_residual_52_5_m"] == round(abs(length / 2.0 - 52.5), 4) > 0.0
        assert row["pearson_r"] >= 0.999 and row["median_difference_m"] == 0.0
    assert {r["pitch_length_m"] for r in p["instrument"]["line_against_provider"]["per_match"]} == {
        100.0,
        102.0,
        104.0,
        106.0,
    }
    # the placebo design: every placebo 240 s away, no runner on the ball, nothing shared
    design = p["placebo_design"]["pooled"]
    assert design["gap_s_p50"] == design["gap_s_p90"] == 300.0
    assert design["runner_in_possession_at_placebo_fraction"] == 0.0
    assert design["shared_instants"] == design["shared_possessions"] == 0
    assert p["units"]["pooled"] == {
        "pairs": 300,
        "units": 300,
        "largest_unit": 1,
        "pairs_in_units_of_two_or_more_fraction": 0.0,
    }
    # the run lengths: 10 m runs, none below the minimum; the cadence of a smooth generator
    assert p["run_length"]["pooled"]["below_minimum"] == 0
    assert abs(p["run_length"]["pooled"]["p50_m"] - 10.0) < 0.2
    assert p["cadence"]["windows"]["min_window_s"] > 0 and not p["cadence"]["windows"]["changed"]
    assert (
        0.0
        < p["standardisation"]["placebo_sd_marker_m"]
        < p["standardisation"]["pair_sd_marker_m"] * 2
    )
    # the null: every pair has a second placebo (the farther supported candidate of its
    # scene, 3 s on), its own unit, and two blocks per match (the runner's two periods).
    # The generator's placebo scene pushes the marker in the first placebo's window only
    # (the baseline ramp), so placebo 1 minus placebo 2 is about 1 m everywhere and the
    # unflipped contrast fires: the generator is no null process for a second placebo, and
    # the centring is what keeps the flipped null nominal
    null = p["null"]
    assert null["pairs_with_second_placebo"] == null["of_pairs"] == 300
    assert null["gap_s_p50"] == null["gap_s_p90"] == 303.0
    assert null["pooled"] == {"pairs": 300, "units": 300, "blocks": 20, "largest_block_share": 0.5}
    assert all(r["with_second_placebo"] == 30 and r["blocks"] == 2 for r in null["per_match"])
    assert null["at_least_one_pct"] <= NULL_AT_LEAST_ONE_MAX_PCT
    assert not null["hardening"]["needed"] and not p["verdict"]["bar_hardening_needed"]
    for row in null["per_subtype"]:
        assert row["pairs"] == row["units"] == 30 and row["blocks"] == 20
        assert abs(row["centring_mean_m"] - 1.0) < 0.5 and row["unflipped"]["passes_bar"]
        assert row["unflipped"]["same_sign_matches"] >= BAR_SAME_SIGN_MATCHES  # 3 pairs a match
    # the power: every subtype has 30 pairs per half, the bar simulated as applied
    assert {(r["subtype"], r["half"]) for r in p["power"]["rows"]} == {
        (s, h) for s in SUBTYPES for h in ("calibration", "other")
    }
    assert all(r["pairs"] == r["units"] == 30 for r in p["power"]["rows"])
    assert p["power"]["replications"] == probe.POWER_REPLICATIONS
    assert p["power"]["pass_rate_se_at_target"] == round(
        math.sqrt(0.8 * 0.2 / probe.POWER_REPLICATIONS), 4
    )
    assert p["power"]["bar_simulated"]["count_at_most"] == BAR_COUNT_AT_MOST == 1
    assert p["verdict"]["M1"]["probable_subtypes"] == len(p["power"]["probable"]["marker"])
    assert p["verdict"]["alive"] == (not p["verdict"]["M1"]["dies"])
    # no effect per subtype anywhere in the file: the per-subtype rows carry counts, rates
    # and minimum detectable effects, with these keys and no other; the null's centring
    # mean is placebo 1 minus placebo 2, a placebo quantity
    text = (reports / PROBE_NAME).read_text(encoding="utf-8")
    assert {k for r in p["power"]["rows"] for k in r} == {
        "subtype",
        "half",
        "pairs",
        "units",
        "matches_with_pairs",
        "mde80_marker_sd",
        "mde80_marker_m",
        "pass_rate_by_effect_marker",
        "mde80_line_sd",
        "mde80_line_m",
        "pass_rate_by_effect_line",
    }
    assert {k for r in null["per_subtype"] for k in r} == {
        "subtype",
        "pairs",
        "units",
        "blocks",
        "centring_mean_m",
        "fires_pct",
        "unflipped",
    }
    assert {k for r in null["per_subtype"] for k in r["unflipped"]} == {
        "p",
        "same_sign_matches",
        "passes_bar",
    }
    assert {k for k in _keys(p["power"]) if "mean" in k} == set()
    assert {k for k in _keys(null) if "mean" in k} == {"centring_mean_m"}
    # --check: the whole warehouse recomputes and agrees; a resealed hand edit differs
    capsys.readouterr()
    assert run_runs_probe(root, reports, check=True) == 0
    assert "warehouse=FULL 10/10 recomputed and equal" in capsys.readouterr().out
    doctored = json.loads(text)
    doctored["probe"]["cadence"]["pooled"]["triples"] += 1
    (reports / PROBE_NAME).write_text(
        json.dumps(seal(doctored), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    assert run_runs_probe(root, reports, check=True) == 1
    assert "differs from what the code writes" in capsys.readouterr().out
    # two writes, the same bytes
    again = tmp_path / "again"
    assert run_runs_probe(root, again) == 0
    assert (again / PROBE_NAME).read_bytes() == text.encode("utf-8")
    # --check on a partial warehouse (one calibration match's frames gone) recomputes
    # nothing and says so: what it verified, how many matches it only counted
    frames = root / "silver" / "frames" / "sport=football"
    gone = frames / f"native_match_id={load_half('calibration')[-1]}"
    (gone / "data.parquet").unlink()
    gone.rmdir()
    capsys.readouterr()
    assert run_runs_probe(root, again, check=True) == 0
    out = capsys.readouterr().out
    assert "warehouse=PARTIAL 9/10 at hand, 0/10 recomputed" in out
    assert "figures as written" in out and "FULL" not in out


@pytest.mark.usefixtures("design_repo")
def test_the_probe_without_an_effect_dies_at_m2(tmp_path: Path) -> None:
    _, _, payload = _written(tmp_path, 0.0, 0.0)
    pooled = payload["probe"]["instrument"]["marker"]["pooled"]
    assert abs(pooled["mean_m"]) < 0.1
    assert not pooled["passes_bar"]
    assert payload["probe"]["verdict"]["M2"]["dies"] and not payload["probe"]["verdict"]["alive"]
    assert consistency_problems(payload) == []


@pytest.mark.usefixtures("design_repo")
def test_consistency_problems_see_a_doctored_verdict_or_protocol(tmp_path: Path) -> None:
    _, _, payload = _written(tmp_path, PLANTED_MARKER_M, PLANTED_LINE_M)

    def doctored(**changes: object) -> dict[str, object]:
        p = json.loads(json.dumps(payload))
        for path, value in changes.items():
            node = p
            keys = path.split("__")
            for key in keys[:-1]:
                node = node[key]
            node[keys[-1]] = value
        return seal(p)

    assert consistency_problems(payload) == []
    assert "content_sha256" in " ".join(consistency_problems({**payload, "schema_version": 2}))
    assert any("M2" in s for s in consistency_problems(doctored(probe__verdict__M2__dies=True)))
    flipped = not payload["probe"]["verdict"]["alive"]
    assert any("alive" in s for s in consistency_problems(doctored(probe__verdict__alive=flipped)))
    assert any(
        "probable" in s
        for s in consistency_problems(doctored(probe__power__probable__marker=list(SUBTYPES)))
    )
    assert any(
        "passes_bar" in s
        for s in consistency_problems(doctored(probe__instrument__marker__pooled__passes_bar=False))
    )
    assert any(
        "hardening" in s
        for s in consistency_problems(doctored(probe__null__hardening__needed=True))
    )
    # M1 counted another quantity than the protocol's primary one
    assert any(
        "primary quantity" in s
        for s in consistency_problems(doctored(probe__verdict__M1__primary_quantity="line"))
    )
    assert any(
        "primary quantity" in s
        for s in consistency_problems(doctored(probe__power__probable__primary_quantity="line"))
    )
    assert any(
        "protocol.fingerprint" in s
        for s in consistency_problems(doctored(protocol__fingerprint="0" * 64))
    )
    assert any("calibration half" in s for s in consistency_problems(doctored(probe__matches=[1])))


@pytest.mark.usefixtures("design_repo")
def test_the_probe_refuses_to_write_from_a_partial_warehouse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, reports = tmp_path / "data", tmp_path / "reports"
    calibration = load_half("calibration")
    raw, runs, instants = _synthetic_raw(3, 1.0, 0.0, seed=1, match_id=calibration[0])
    _write_warehouse(root, raw, runs, instants)
    assert run_runs_probe(root, reports) == 1
    assert not (reports / PROBE_NAME).exists()
    assert "1 of the 10 calibration matches" in capsys.readouterr().out
    assert run_runs_probe(root, reports, check=True) == 1  # nothing to check against


@pytest.mark.usefixtures("design_repo")
def test_probe_match_takes_a_match_tracking_and_reads_the_provider_through_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    raw, runs, instants = _synthetic_raw(4, 1.0, 0.5, seed=2, match_id=CI_FIXTURE_MATCH)
    _write_warehouse(root, raw, runs, instants)
    t = windows.load_tracking(root, CI_FIXTURE_MATCH)
    m = probe.probe_match(t, root)
    assert m.runs == 4 and len(m.pairs) == 4
    assert np.isfinite(m.length_m).all() and (np.abs(m.length_m - 10.0) < 0.2).all()
    assert np.allclose(m.line_at_tc_m, m.provider_line_x_m)
    assert m.pitch_length_m == 104.0
    assert m.provider_identity_residual_half_length_m == pytest.approx(0.0, abs=1e-9)
    assert m.provider_identity_residual_52_5_m == pytest.approx(0.5)
    assert not m.runner_in_possession_at_placebo.any()
    provider = probe.load_provider_lines(t, root)
    assert provider.pitch_length_m == 104.0
    assert set(provider.x_start_by_run) == {r.event_id for r in runs}
    assert provider.identity_max_residual_52_5_m == m.provider_identity_residual_52_5_m
    # the second placebo of every pair: the farther supported candidate of the scene, in
    # the placebo's period, 30 frames after the first, with its two quantities; the run's
    # period travels with the pair for the null's blocks
    first = np.array([p.placebo_instant for p in m.pairs])
    assert m.placebo2_instant.tolist() == (first + 30).tolist()
    assert m.placebo2_period.tolist() == [p.placebo_period for p in m.pairs] == [2] * 4
    assert np.isfinite(m.placebo2_marker_m).all() and np.isfinite(m.placebo2_line_m).all()
    assert m.run_period.tolist() == [r.period for r in runs] == [1, 1, 2, 2]
    # the units the counting door reports are the ones the pairs form
    counts = windows.count_tracking(root, CI_FIXTURE_MATCH)
    assert counts.analysis_set == 4
    assert counts.analysis_units == units_by_subtype(
        [p.subtype for p in m.pairs], [windows.pair_unit_key(p) for p in m.pairs]
    )
    # the pairs carry the placebo the generator planted (block n + i, the anchor)
    for i, pair in enumerate(m.pairs):
        assert pair.placebo_instant == instants[(CI_FIXTURE_MATCH, f"r{i}")][-1][1]
        assert pair.t_c == runs[i].frame_start and pair.player_id == 7


@pytest.mark.usefixtures("design_repo")
def test_the_probe_refuses_uncommitted_code_and_records_the_committed_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Write mode names the code that ran: `head` and `code_tree_sha` are HEAD's, so it
    refuses while anything under the `runs/` tree or the protocol is uncommitted (edited,
    or new and untracked), writes nothing, and `--check` still reads; a change elsewhere
    in the tree does not stop it."""
    repo = data.repo_root()  # the throwaway repository the fixture points the guard at
    root, reports, payload = _written(tmp_path, PLANTED_MARKER_M, PLANTED_LINE_M)
    tree = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"HEAD:{data.CODE_IN_REPO}"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    assert payload["probe"]["code_tree_sha"] == tree == data.code_tree_sha() and len(tree) == 40
    assert payload["probe"]["head"] == data.head_commit() != tree
    before = (reports / PROBE_NAME).read_bytes()
    capsys.readouterr()
    code = repo / data.CODE_IN_REPO / "probe.py"
    code.write_text("# edited and not committed\n", encoding="utf-8")
    assert data.dirty_code_paths() == [f"{data.CODE_IN_REPO}/probe.py"]
    assert run_runs_probe(root, reports) == 1
    assert "not committed" in capsys.readouterr().out
    assert (reports / PROBE_NAME).read_bytes() == before
    assert run_runs_probe(root, reports, check=True) == 0
    _git(repo, "checkout", "--", data.CODE_IN_REPO)
    new = repo / data.CODE_IN_REPO / "new.py"
    new.write_text("x = 1\n", encoding="utf-8")
    assert data.dirty_code_paths() == [f"{data.CODE_IN_REPO}/new.py"]
    assert run_runs_probe(root, reports) == 1
    new.unlink()
    protocol = repo / data.PROTOCOL_IN_REPO
    protocol.write_text(protocol.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert data.dirty_code_paths() == [data.PROTOCOL_IN_REPO]
    assert run_runs_probe(root, reports) == 1
    assert (reports / PROBE_NAME).read_bytes() == before
    _git(repo, "checkout", "--", data.PROTOCOL_IN_REPO)
    (repo / "tasks").mkdir()
    (repo / "tasks" / "todo.md").write_text("plan\n", encoding="utf-8")
    assert data.dirty_paths(repo) == ["?? tasks/todo.md"] and data.dirty_code_paths() == []
    again = tmp_path / "again"
    assert run_runs_probe(root, again) == 0
    assert (again / PROBE_NAME).read_bytes() == before


@pytest.mark.usefixtures("design_repo")
def test_the_probe_keeps_the_sections_it_does_not_own(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Inherited (a) of task 50: the file holds the probe's section and task 50's `effect`
    under one seal. A rewrite of the probe keeps what is not its own, byte for byte, and
    `--check` compares what it would write on top of what is there: a foreign section edited
    without resealing fails on the seal, one resealed is the other command's to check."""
    root, reports, payload = _written(tmp_path, PLANTED_MARKER_M, PLANTED_LINE_M)
    path = reports / PROBE_NAME
    foreign = {"effect": {"task": 50, "candidates": ["support"]}}
    with_foreign = seal({**{k: v for k, v in payload.items() if k != "content_sha256"}, **foreign})
    path.write_text(json.dumps(with_foreign, indent=2) + "\n", encoding="utf-8")
    assert list(with_foreign)[-2:] == ["effect", "content_sha256"]
    capsys.readouterr()
    assert run_runs_probe(root, reports, check=True) == 0
    assert "FULL 10/10 recomputed and equal" in capsys.readouterr().out
    assert run_runs_probe(root, reports) == 0
    again = json.loads(path.read_text(encoding="utf-8"))
    assert again["effect"] == foreign["effect"] and again["probe"] == payload["probe"]
    assert sealed(again) and list(again)[-2:] == ["effect", "content_sha256"]
    unsealed = json.loads(path.read_text(encoding="utf-8"))
    unsealed["effect"]["candidates"] = []
    path.write_text(json.dumps(unsealed, indent=2) + "\n", encoding="utf-8")
    capsys.readouterr()
    assert run_runs_probe(root, reports, check=True) == 1
    assert "content_sha256" in capsys.readouterr().out
    path.write_text(json.dumps(seal(unsealed), indent=2) + "\n", encoding="utf-8")
    assert run_runs_probe(root, reports, check=True) == 0


def test_the_probe_names_the_calibration_half_and_no_other_door() -> None:
    text = (SRC / "probe.py").read_text(encoding="utf-8")
    assert 'HALF: Half = "calibration"' in text
    assert "load_half(HALF)" in text
    assert text.count("load_tracking(") == 1  # the one call, on load_half's ids
    assert "_read_tracking" not in text and '"sport=football"' not in text
    assert "frames_attacking" not in text


def test_cli_wires_runs_probe() -> None:
    args = build_parser().parse_args(["runs", "probe", "--check"])
    assert args.check and args.runs_command == "probe"
    assert args.data_dir == data_root() and args.reports_dir == Path("reports")


# --- the versioned file -----------------------------------------------------------------------


def _versioned() -> dict[str, object]:
    return json.loads(PROBE_FILE.read_text(encoding="utf-8"))


def _coverage_rows() -> dict[str, dict[str, str]]:
    with (REPORTS / COVERAGE_NAME).open(encoding="utf-8", newline="") as handle:
        return {r["match_id"]: r for r in csv.DictReader(handle)}


def test_the_versioned_probe_is_sealed_and_answers_to_the_committed_protocol() -> None:
    payload = _versioned()
    assert sealed(payload)
    assert consistency_problems(payload) == []
    p = payload["probe"]
    assert p["task"] == 49 and p["written"] == probe.WRITTEN
    assert p["matches"] == load_half("calibration")


def test_the_versioned_funnel_is_the_coverage_files() -> None:
    rows = _coverage_rows()
    funnel = _versioned()["probe"]["funnel"]["per_match"]
    assert sorted(r["match_id"] for r in funnel) == counting_match_ids()
    for row in funnel:
        versioned = rows[str(row["match_id"])]
        assert row["runs"] == int(versioned["runs"])
        assert row["pairs"] == int(versioned["analysis_set"])
        assert sum(row["pairs_by_subtype"].values()) == row["pairs"]
        assert row["half"] == ("calibration" if versioned["half"] == "calibration" else "other")


def test_the_versioned_verdict_is_pinned() -> None:
    """The figures of task 49 as the plan records them: a change is a change of what was
    preregistered against and must show here, never only in the JSON."""
    p = _versioned()["probe"]
    assert p["verdict"]["alive"] is True
    assert p["verdict"]["M2"]["instrument_passes_bar"] is True
    assert p["verdict"]["bar_hardening_needed"] is False
    assert p["power"]["probable"]["marker"] == ["coming_short", "run_ahead_of_the_ball", "support"]
    # with the bar simulated as applied (review of task 49) the line keeps one of the
    # three: M1 counts the marker, and the record says the two lists no longer agree
    assert p["power"]["probable"]["line"] == ["run_ahead_of_the_ball"]
    assert p["power"]["probable"]["both"] == ["run_ahead_of_the_ball"]
    assert p["instrument"]["marker"]["pooled"]["same_sign_matches"] == 10
    assert p["instrument"]["marker"]["pooled"]["p"] == round(1 / (1 + N_PERMUTATIONS), 5)
    assert p["null"]["at_least_one_pct"] <= NULL_AT_LEAST_ONE_MAX_PCT
    assert p["null"]["pairs_with_second_placebo"] == 3541 and p["null"]["of_pairs"] == 3756
    assert p["null"]["pooled"]["units"] == 2420 and p["null"]["pooled"]["blocks"] == 77
    # the primary quantity M1 counted is the protocol's (decided 2026-10-11): the marker
    assert p["verdict"]["M1"]["primary_quantity"] == "marker"
    assert p["power"]["probable"]["primary_quantity"] == "marker"
    assert (
        p["verdict"]["M1"]["probable_subtypes"] == 3 and p["verdict"]["M1"]["probable_by_line"] == 1
    )
    assert all(r["unflipped"]["passes_bar"] is False for r in p["null"]["per_subtype"])
    assert p["cadence"]["windows"]["changed"] is False
    assert p["run_length"]["changed"] is False
    assert p["power"]["probable"]["mde80_sd_at_most"] == TESTABILITY_MDE80_SD
    # the provider's identity holds with the half length in eight matches and with a fixed
    # 52.5 in two of the 106 m ones: the x is read as given, never converted from the height
    lines = p["instrument"]["line_against_provider"]["per_match"]
    assert {r["pitch_length_m"] for r in lines} == {104.0, 105.0, 106.0}
    assert [r["match_id"] for r in lines if r["identity_max_residual_half_length_m"] > 0] == [
        1959846,
        2010085,
    ]
    assert all(r["pearson_r"] >= 0.995 and -0.7 < r["median_difference_m"] < 0 for r in lines)


@needs_the_whole_warehouse
def test_the_versioned_probe_is_recomputed_from_the_whole_warehouse(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_runs_probe(data_root(), REPORTS, check=True) == 0
    assert "warehouse=FULL 10/10 recomputed and equal" in capsys.readouterr().out


def test_replace_keeps_the_pair_effect_fields() -> None:
    pair = _pair(1, 0, "p", 5, 1.0)
    assert replace(pair, marker_m=2.0).placebo_instant == 5
    assert unit_sums(np.array([1.0, 2.0, 3.0]), np.array([0, 0, 1], dtype=np.intp), 2).tolist() == [
        3.0,
        3.0,
    ]
