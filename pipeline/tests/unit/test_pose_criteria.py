"""M1 and M2 of task 60 (`tracklab.pose.criteria`) and their simulation, phase B1.

The verdict on hand-made players, at each threshold of the protocol, and the simulator on two
kinds of pools: the noise twin of the sweep (no gait: P6 has to die) and a pair of made-up
bands that a sane instrument would give (P6 has to live). Phase B2 runs the simulator with the
probe's counts; nothing here reads data.

Mutations, each applied, seen failing and restored (tasks/todo.md, task 60, phase B1): "fewer
than 3 in 4" read as "at most"; half the IQR read as the whole; the first five windows taken
whether finite or not; M1 counting windows instead of finite ones; the low band drawn from the
high pool; and in phase B2, the sane simulator without the low band lowered or without the
spread between players.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from tracklab.pose import criteria, sweep
from tracklab.pose.criteria import Player, Pool

Array = NDArray[np.float64]

CLIP = Path(__file__).resolve().parents[3] / "web" / "public" / "data" / "pose"
CLIP = CLIP / "1925299_phase406.json"
DRAWS = 40
# Exactly unit sd (ddof 1) over the draws: a player's propagated sd is then the factor on it.
UNIT = np.random.default_rng(0).standard_normal(DRAWS)
UNIT = (UNIT - UNIT.mean()) / UNIT.std(ddof=1)


def player(high: list[float], low: list[float], sd: float = 0.01) -> Player:
    """A player whose high windows each draw `cadence + sd x UNIT` (NaN windows draw NaN)."""
    h = np.array(high, dtype=np.float64)
    return Player(h, np.array(low, dtype=np.float64), h[:, None] + sd * UNIT[None, :])


def plain(n: int, high: float = 4.3, low: float = 3.5) -> list[Player]:
    return [player([high + 0.05 * i] * 5, [low] * 5) for i in range(n)]


def test_m1_counts_players_with_five_finite_high_windows() -> None:
    nine = plain(9) + [player([4.3, 4.3, 4.3, 4.3, np.nan, np.nan], [3.5] * 5)]
    assert criteria.m1_m2(nine).dies_at == "m1"
    assert criteria.m1_m2(nine).m1_players == 9
    ten = plain(9) + [player([4.3, np.nan, 4.3, 4.3, 4.3, 4.3], [3.5] * 5)]
    assert criteria.m1_m2(ten).m1_players == 10
    assert criteria.m1_m2(ten).dies_at is None


def test_m2_needs_ten_players_with_both_bands() -> None:
    players = plain(9) + [player([4.3] * 5, [3.5, 3.5, 3.5, 3.5, np.nan]) for _ in range(3)]
    v = criteria.m1_m2(players)
    assert (v.dies_at, v.m1_players, v.m2_players) == ("m2_coverage", 12, 9)


def test_m2_sign_dies_under_three_in_four_and_lives_at_it() -> None:
    """12 players with both bands: 9 with high above low is 3 in 4 exactly (lives); 8 dies."""

    def match(positive: int) -> list[Player]:
        return [
            player([4.3 + 0.05 * i] * 5, [3.5 if i < positive else 5.0] * 5) for i in range(12)
        ]  # fmt: skip

    assert criteria.m1_m2(match(9)).dies_at is None
    assert criteria.m1_m2(match(9)).m2_positive == 9
    assert criteria.m1_m2(match(8)).dies_at == "m2_sign"


def test_m2_precision_against_half_the_iqr() -> None:
    """Twelve players whose five-window medians run 4.00 to 4.55 Hz by 0.05: the IQR (linear
    percentiles) is 0.275 Hz, half of it 0.1375. A propagated sd of 0.13 lives, 0.15 dies (and
    would live against the whole IQR)."""

    def match(sd: float) -> list[Player]:
        return [player([4.0 + 0.05 * i] * 5, [3.0] * 5, sd) for i in range(12)]

    v = criteria.m1_m2(match(0.13))
    assert abs(v.half_iqr_hz - 0.1375) < 1e-12
    assert abs(v.median_sd_hz - 0.13) < 1e-12 and v.dies_at is None
    assert criteria.m1_m2(match(0.15)).dies_at == "m2_precision"


def test_the_precision_reads_the_first_five_finite_high_windows() -> None:
    """A NaN window is skipped, and windows after the fifth finite one are not read: here they
    are wild, and reading them would move the medians and the sd."""
    players = []
    for i in range(12):
        high = [np.nan, *[4.0 + 0.05 * i] * 5, 9.0, 1.0]
        p = player(high, [3.0] * 5, 0.05)
        draws = p.high_draws.copy()
        draws[6:] = np.random.default_rng(i).uniform(0.0, 20.0, size=(2, DRAWS))
        players.append(Player(p.high, p.low, draws))
    v = criteria.m1_m2(players)
    assert abs(v.half_iqr_hz - 0.1375) < 1e-12 and abs(v.median_sd_hz - 0.05) < 1e-12


def test_the_propagated_sd_ignores_nan_windows_and_invalid_draws() -> None:
    draws = np.array([[1.0, 2.0, np.nan, 4.0], [3.0, np.nan, np.nan, 2.0]])
    # per draw: nanmedian of the column, the all-NaN column dropped: 2.0, 2.0, 3.0
    assert criteria.propagated_sd(draws) == np.std([2.0, 2.0, 3.0], ddof=1)
    assert criteria.propagated_sd(np.array([[np.nan, 1.0], [np.nan, np.nan]])) == np.inf


def test_the_simulator_kills_the_noise_twin_and_spares_a_sane_instrument() -> None:
    """A noise twin of W 50, cap 20 and rho 0 (the sweep's, at 2,000 windows and 40 copies
    each): with 15 players of 200 windows in each band P6 dies in at least 95 % of 200
    repetitions.
    Two made-up bands a sane instrument would give (4.3 and 3.5 Hz, 0.2 Hz between windows, 0.02
    Hz between copies), 12 players of 10 windows: it lives in at least 95 %. The simulator
    draws every player from the same pools, so players differ only by the windows they draw:
    with 0.1 Hz between windows (written first) the second clause of M2 killed 6 % (12 of 200),
    the fifth review's finding about identical players (task 60, record of phase B1)."""
    raw = json.loads(CLIP.read_text(encoding="utf-8"))
    fps, mae = sweep.clip_mae(raw)
    grid = replace(sweep.PROTOCOL, windows_s=2000)
    noise = sweep.noise_pool(mae, fps, width=50, cap=20, rho=0.0, grid=grid, draws=DRAWS)
    dead = criteria.simulate_m1_m2([200] * 15, [200] * 15, noise, noise, seed=1)
    print(f"\nnoise twin: {dead}")
    assert dead["p_dies"] >= 0.95

    rng = np.random.default_rng(2)

    def band(centre: float) -> Pool:
        c = centre + 0.2 * rng.standard_normal(500)
        return Pool(c, c[:, None] + 0.02 * rng.standard_normal((500, DRAWS)))

    sane = criteria.simulate_m1_m2([10] * 12, [10] * 12, band(4.3), band(3.5), seed=3)
    print(f"sane bands: {sane}")
    assert sane["p_dies"] <= 0.05


def test_the_sane_simulator_needs_both_the_rise_between_bands_and_the_spread_of_the_squad() -> None:
    """Pools drawn at 3.0 Hz with 0.02 Hz between windows and 0.01 Hz between copies, twelve
    players of 10 high and 30 low windows, 100 repetitions. With the band rising 0.3 Hz and
    players 0.1 Hz apart P6 lives; with no rise the sign clause kills it; with every player at
    the same cadence the precision clause does (half an IQR of nearly nothing)."""
    rng = np.random.default_rng(4)
    c = 3.0 + 0.02 * rng.standard_normal(400)
    pool = Pool(c, c[:, None] + 0.01 * rng.standard_normal((400, DRAWS)))

    def sim(delta: float, sigma_b: float) -> dict[str, Any]:
        return criteria.simulate_sane(
            [10] * 12, [30] * 12, pool, pool, cadence_hz=3.0, delta_hz=delta,
            sigma_b_hz=sigma_b, reps=100, seed=5,
        )  # fmt: skip

    lives, flat, alike = sim(0.3, 0.1), sim(0.0, 0.1), sim(0.3, 0.0)
    print(f"\nsane: {lives}\nno rise: {flat}\nalike: {alike}")
    assert lives["p_dies"] <= 0.05
    assert flat["p_dies"] >= 0.5 and flat["by"]["m2_sign"] == flat["dies"]
    assert alike["p_dies"] >= 0.5 and alike["by"]["m2_precision"] == alike["dies"]


def test_a_written_verdict_dies_where_its_figures_say() -> None:
    """`verdict_dies_at` reads the death back from the figures a verdict file writes (the
    second time's check and the guard), in the order of `m1_m2`."""
    section: dict[str, Any] = {
        "M1": {"players": 9},
        "M2": {"players_with_both": 9, "positive": 9, "median_sd_hz": 0.01, "half_iqr_hz": 0.1},
    }
    assert criteria.verdict_dies_at(section) == "m1"
    section["M1"]["players"] = 12
    assert criteria.verdict_dies_at(section) == "m2_coverage"
    section["M2"] |= {"players_with_both": 12, "positive": 8}
    assert criteria.verdict_dies_at(section) == "m2_sign"
    section["M2"] |= {"positive": 9, "median_sd_hz": 0.2}
    assert criteria.verdict_dies_at(section) == "m2_precision"
    section["M2"]["median_sd_hz"] = 0.05
    assert criteria.verdict_dies_at(section) is None
