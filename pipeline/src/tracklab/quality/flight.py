"""Apparent gravity of a ball in free flight, and synthetic flights to validate it.

The estimator fits z(t) = c + b*t + a*t^2 by least squares over a window of samples
and reads g = -2a. It is validated on flights whose g is known before it is
pointed at a real ball (task 26): a raw parabola, one with sensor noise, one
smoothed by a moving average, and one whose samples are only true every k frames
and linearly interpolated in between, the shapes `skillcorner_screens` tested.
Everything is in metres and seconds.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

G = 9.80665  # standard gravity, m/s^2


def fit_quadratic(t: Sequence[float], z: Sequence[float]) -> tuple[float, float, float]:
    """(c, b, a) of the least-squares z = c + b*t + a*t^2. Time is centred first,
    so the normal equations stay well conditioned at any absolute t."""
    n = len(t)
    if n < 3 or n != len(z):
        raise ValueError(f"need at least 3 paired samples, got {n} and {len(z)}")
    t0 = sum(t) / n
    u = [ti - t0 for ti in t]
    s1, s2, s3, s4 = (sum(ui**k for ui in u) for k in (1, 2, 3, 4))
    y0 = sum(z)
    y1 = sum(ui * zi for ui, zi in zip(u, z, strict=True))
    y2 = sum(ui * ui * zi for ui, zi in zip(u, z, strict=True))
    # Solve [[n,s1,s2],[s1,s2,s3],[s2,s3,s4]] @ [c,b,a] = [y0,y1,y2] by Cramer's rule.
    m = [[float(n), s1, s2], [s1, s2, s3], [s2, s3, s4]]
    det = _det3(m)
    if abs(det) < 1e-12:
        raise ValueError("degenerate window: the samples do not span three times")
    c = _det3(_with_column(m, 0, (y0, y1, y2))) / det
    b = _det3(_with_column(m, 1, (y0, y1, y2))) / det
    a = _det3(_with_column(m, 2, (y0, y1, y2))) / det
    # Back from centred time: z = c + b(t - t0) + a(t - t0)^2.
    return c - b * t0 + a * t0 * t0, b - 2 * a * t0, a


def apparent_g(t: Sequence[float], z: Sequence[float]) -> float:
    """The g a flight implies, positive for a ball that falls."""
    return -2.0 * fit_quadratic(t, z)[2]


def _det3(m: list[list[float]]) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def _with_column(
    m: list[list[float]], j: int, col: tuple[float, float, float]
) -> list[list[float]]:
    return [[col[i] if k == j else m[i][k] for k in range(3)] for i in range(3)]


# Synthetic flights.


def parabola(
    fps: float, half_window: int, apex_z: float = 4.0, g: float = G
) -> tuple[list[float], list[float]]:
    """Samples of a free flight centred on its apex: t in seconds, z in metres."""
    t = [k / fps for k in range(-half_window, half_window + 1)]
    return t, [apex_z - 0.5 * g * ti * ti for ti in t]


def with_noise(z: Sequence[float], sigma: float, seed: int = 0) -> list[float]:
    rng = random.Random(seed)
    return [zi + rng.gauss(0.0, sigma) for zi in z]


def moving_average(z: Sequence[float], k: int) -> list[float]:
    """Centred, shrinking at the ends so the output has the input's length. Apply it
    to the whole track and cut the window after: the shrunk ends bend a parabola,
    the centred average of one does not (measured: -15% against 0.0%)."""
    h = k // 2
    out = []
    for i in range(len(z)):
        lo, hi = max(0, i - h), min(len(z), i + h + 1)
        out.append(sum(z[lo:hi]) / (hi - lo))
    return out


def knots_every(z: Sequence[float], k: int, phase: int = 0) -> list[float]:
    """True only at every k-th sample from `phase`, linear in between: a tracker that
    measures at a lower rate and interpolates up. Samples outside the first and last
    knot are left as they are, so apply it to the whole track and cut the window after."""
    idx = list(range(phase, len(z), k))
    out = list(z)
    for i0, i1 in zip(idx, idx[1:], strict=False):
        for i in range(i0 + 1, i1):
            w = (i - i0) / (i1 - i0)
            out[i] = z[i0] * (1 - w) + z[i1] * w
    return out
