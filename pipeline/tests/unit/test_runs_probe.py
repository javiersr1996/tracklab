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
shared-flip test; `argmax` for the cadence fails the five-frame slope test.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_runs_windows import (  # the synthetic match and the throwaway design repo of task 48
    CI_FIXTURE_MATCH,
    PLANTED_LINE_M,
    PLANTED_MARKER_M,
    _guarded,
    _synthetic_raw,
    _write_warehouse,
    design_repo,  # noqa: F401  (a fixture)
    needs_the_whole_warehouse,
)

from tracklab.cli import build_parser
from tracklab.paths import data_root
from tracklab.runs import probe, windows
from tracklab.runs.coverage import COVERAGE_NAME
from tracklab.runs.data import counting_match_ids, load_half
from tracklab.runs.probe import (
    PROBE_NAME,
    Z_TWO_SIDED,
    MatchProbe,
    bar_verdict,
    cadence,
    cadence_lag,
    consistency_problems,
    design_effect,
    mde80,
    null_fire_rates,
    permutation_p,
    run_runs_probe,
    unit_sums,
    z_two_sided,
)
from tracklab.runs.protocol import (
    BAR_P,
    BAR_SAME_SIGN_MATCHES,
    N_PERMUTATIONS,
    NULL_AT_LEAST_ONE_MAX_PCT,
    TESTABILITY_MDE80_SD,
    read_protocol,
    seal,
    sealed,
)
from tracklab.runs.windows import SUBTYPES, PairEffect, unit_labels, units_by_subtype

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
    assert Z_TWO_SIDED == z_two_sided(BAR_P) == pytest.approx(3.2051, abs=1e-3)


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


def _probe_of(match_id: int, pairs: list[PairEffect]) -> MatchProbe:
    """A `MatchProbe` with the pairs alone: what `_collect` reads."""
    empty = np.zeros(0)
    return MatchProbe(
        match_id=match_id,
        runs=len(pairs),
        pairs=tuple(pairs),
        length_m=empty,
        line_at_tc_m=empty,
        provider_line_x_m=empty,
        pitch_length_m=105.0,
        runner_in_possession_at_placebo=np.zeros(len(pairs), dtype=np.bool_),
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


def test_null_fire_rates_are_small_and_the_normal_approximation_agrees() -> None:
    values, units, matches, subtypes = _null_pairs(7)
    rates = null_fire_rates(
        values,
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
    assert abs(rates.at_least_one_pct - rates.at_least_one_normal_pct) <= 1.0


def test_the_outer_flips_are_shared_by_the_subtypes() -> None:
    """Two subtypes with the same pairs in the same units fire on the same null draws, so 'at
    least one' equals each one's rate; outer flips drawn per subtype would not."""
    rng = np.random.default_rng(11)
    base = rng.normal(0.0, 1.0, 300)
    values = np.concatenate([base, base])
    units = np.concatenate([np.arange(300), np.arange(300)]).astype(np.intp)
    matches = np.concatenate([np.repeat(np.arange(10), 30)] * 2).astype(np.intp)
    subtypes = np.concatenate([np.zeros(300), np.ones(300)]).astype(np.intp)
    rates = null_fire_rates(
        values,
        units,
        matches,
        subtypes,
        2,
        10,
        np.random.default_rng(3),
        np.random.default_rng(4),
        draws=2000,
    )
    assert rates.fires_pct[0] == rates.fires_pct[1] == rates.at_least_one_pct
    assert rates.fires_normal_pct[0] == rates.fires_normal_pct[1] == rates.at_least_one_normal_pct


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


# --- the command on a synthetic warehouse ---------------------------------------------------


def _synthetic_warehouse(root: Path, marker: float, line: float) -> list[int]:
    """Twenty synthetic matches under the committed split's ids, 30 runs each with their
    placebo candidates in the events; returns the calibration ids."""
    calibration = load_half("calibration")
    for i, match_id in enumerate(counting_match_ids()):
        raw, runs, instants = _synthetic_raw(30, marker, line, seed=100 + i, match_id=match_id)
        _write_warehouse(root, raw, runs, instants)
    return calibration


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
    assert len(p["head"]) == 40
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
    # the line against the provider: the same arrays, so r is 1 and the difference 0
    for row in p["instrument"]["line_against_provider"]["per_match"]:
        assert row["runs_compared"] == 30 and row["pitch_length_m"] == 105.0
        assert row["pearson_r"] >= 0.999 and row["median_difference_m"] == 0.0
    # the placebo design: every placebo 240 s away, no runner on the ball, nothing shared
    design = p["placebo_design"]["pooled"]
    assert design["gap_s_p50"] == design["gap_s_p90"] == 240.0
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
    # the null and the power: every subtype has 30 pairs per half, the hardening not needed
    assert p["null"]["at_least_one_pct"] <= NULL_AT_LEAST_ONE_MAX_PCT
    assert not p["null"]["hardening"]["needed"] and not p["verdict"]["bar_hardening_needed"]
    assert {(r["subtype"], r["half"]) for r in p["power"]["rows"]} == {
        (s, h) for s in SUBTYPES for h in ("calibration", "other")
    }
    assert all(r["pairs"] == r["units"] == 30 for r in p["power"]["rows"])
    assert p["verdict"]["M1"]["probable_subtypes"] == len(p["power"]["probable"]["marker"])
    assert p["verdict"]["alive"] == (not p["verdict"]["M1"]["dies"])
    # no effect per subtype anywhere in the file: the per-subtype rows carry counts, rates
    # and minimum detectable effects, with these keys and no other
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
    assert {k for r in p["null"]["per_subtype"] for k in r} == {
        "subtype",
        "pairs",
        "units",
        "fires_pct",
        "fires_normal_pct",
    }
    assert "mean" not in json.dumps(p["power"]) and "mean" not in json.dumps(p["null"])
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
    assert m.pitch_length_m == 105.0
    assert not m.runner_in_possession_at_placebo.any()
    pitch, lines = probe.load_provider_lines(t, root)
    assert pitch == 105.0 and set(lines) == {r.event_id for r in runs}
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
    assert p["power"]["probable"]["line"] == p["power"]["probable"]["marker"]
    assert p["instrument"]["marker"]["pooled"]["same_sign_matches"] == 10
    assert p["instrument"]["marker"]["pooled"]["p"] == round(1 / (1 + N_PERMUTATIONS), 5)
    assert p["null"]["at_least_one_pct"] <= NULL_AT_LEAST_ONE_MAX_PCT
    assert p["cadence"]["windows"]["changed"] is False
    assert p["run_length"]["changed"] is False
    assert p["power"]["probable"]["mde80_sd_at_most"] == TESTABILITY_MDE80_SD


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
