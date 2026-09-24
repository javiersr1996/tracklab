"""The gravity estimator on flights whose g is known (task 26).

Each treatment is applied to a track longer than the window and the window is cut
after, as a tracker would smooth or interpolate the whole track. The reference
ranges are the ones `skillcorner_screens` measured for the same treatments
(probes/probe_l_redo.py): -2.4% to +4.3%.
"""

from __future__ import annotations

import pytest

from tracklab.quality.flight import (
    G,
    apparent_g,
    fit_quadratic,
    knots_every,
    moving_average,
    parabola,
    with_noise,
)

FPS, HALF, MARGIN = 25, 10, 10  # basketball: +-0.4 s around the apex
SCREENS_RANGE = (-2.4, 4.3)


def _bias(z: list[float], t: list[float]) -> float:
    cut = slice(MARGIN, len(t) - MARGIN)
    return 100.0 * (apparent_g(t[cut], z[cut]) / G - 1.0)


@pytest.mark.parametrize(("fps", "half"), [(25, 10), (25, 6), (10, 4), (10, 6)])
def test_a_raw_parabola_gives_back_its_g(fps: int, half: int) -> None:
    t, z = parabola(fps, half)
    assert apparent_g(t, z) == pytest.approx(G, rel=5e-3)


def test_the_fit_does_not_depend_on_the_clock_origin() -> None:
    t, z = parabola(FPS, HALF)
    late = [ti + 3_600.0 for ti in t]
    assert apparent_g(late, z) == pytest.approx(G, rel=1e-6)
    assert fit_quadratic(late, z)[2] == pytest.approx(-G / 2, rel=1e-6)


def test_sensor_noise_averages_out() -> None:
    t, z = parabola(FPS, HALF + MARGIN)
    biases = [_bias(with_noise(z, 0.1 * 0.3048, seed), t) for seed in range(200)]
    mean = sum(biases) / len(biases)
    print(f"noise 0.1 ft: mean bias {mean:+.2f}% over {len(biases)} flights")
    assert abs(mean) < 1.0


def test_a_centred_moving_average_keeps_the_curvature() -> None:
    t, z = parabola(FPS, HALF + MARGIN)
    bias = _bias(moving_average(z, 5), t)
    print(f"moving average of 5: bias {bias:+.2f}%")
    assert abs(bias) < 0.5


def test_knots_every_five_frames_stay_in_the_range_screens_measured() -> None:
    t, z = parabola(FPS, HALF + MARGIN)
    biases = [_bias(knots_every(z, 5, phase), t) for phase in range(5)]
    print("knots every 5 frames, by phase:", [f"{b:+.2f}%" for b in biases])
    lo, hi = SCREENS_RANGE
    assert all(lo <= b <= hi for b in biases)


def test_a_window_that_does_not_span_three_times_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        apparent_g([0.0, 0.04], [1.0, 1.0])
    with pytest.raises(ValueError, match="degenerate"):
        apparent_g([0.0, 0.0, 0.0], [1.0, 2.0, 3.0])
