"""Steps per second from one published pose clip, and the sd its ankles' predicted error gives.

Lesson 5 of /learn ("How many steps per second?") shows this file as "Reproduce it". It needs
Python 3 and nothing else: it reads the clip Pitch & Parquet publishes, takes the window the clip
names, builds s(t), the two ankles' separation along the direction of travel, reads the cadence
from the first peak of its autocorrelation, and moves every sample by the ankles' predicted error
to see how far the cadence moves.

    python cadence.py                       # the clip on the site
    python cadence.py hook_1925299.json     # the same file, saved
"""

import json
import math
import sys
import urllib.request
from collections.abc import Callable
from typing import Any

URL = "https://pitchandparquet.vercel.app/data/pose/hook_1925299.json"
BAND_Z = 1.96  # white noise stays inside +-1.96 / sqrt(n - k) 95 % of the time
DRAWS = 200
SEED = 59


def load(source: str) -> Any:
    if source.startswith("https://"):
        with urllib.request.urlopen(source) as response:
            return json.load(response)
    with open(source, encoding="utf-8") as f:
        return json.load(f)


def signal(clip: Any) -> tuple[list[float], list[float], float, Any]:
    """s(t) in metres and the sd of each sample, for the clip's window."""
    w = clip["windows"][0]
    left, right = clip["joints"].index("lAnkle"), clip["joints"].index("rAnkle")
    rows = [
        p
        for frame in clip["frames"]
        if w["frame_lo"] <= frame["f"] <= w["frame_hi"]
        for p in frame["p"]
        if p[0] == w["player"]
    ]
    # A row: [player, x cm, y cm, detected, [joints as [dx, dy, dz] cm, predicted errors in mm]]
    dx, dy = rows[-1][1] - rows[0][1], rows[-1][2] - rows[0][2]
    norm = math.hypot(dx, dy)
    s, sigma = [], []
    for p in rows:
        xyz, mae = p[4]
        along = (xyz[left][0] - xyz[right][0]) * dx + (xyz[left][1] - xyz[right][1]) * dy
        s.append(along / norm / 100)
        sigma.append(math.hypot(mae[left], mae[right]) / 1000)
    return s, sigma, clip["fps"], w


def cadence(s: list[float], fps: float) -> float:
    """2 x fps / lag of the first peak of the autocorrelation after it turns negative."""
    n = len(s)
    m = sum(s) / n
    s0 = [v - m for v in s]
    r = []
    for k in range(n):
        total = 0.0
        for i in range(n - k):
            total += s0[i] * s0[i + k]
        r.append(total / (n - k))
    negative = next((k for k in range(n) if r[k] < 0), None)
    if not r[0] > 0 or negative is None:
        return math.nan
    for k in range(negative + 1, n - 1):
        if r[k] > 0 and r[k] > r[k - 1] and r[k] >= r[k + 1]:
            if r[k] / r[0] <= BAND_Z / math.sqrt(n - k):
                return math.nan
            curvature = r[k - 1] - 2 * r[k] + r[k + 1]
            shift = 0.5 * (r[k - 1] - r[k + 1]) / curvature if curvature < 0 else 0.0
            return 2 * fps / (k + shift)
    return math.nan


def mulberry32(seed: int) -> Callable[[], float]:
    """The page's generator, so these draws are its draws."""
    state = seed & 0xFFFFFFFF

    def imul(a: int, b: int) -> int:
        return (a * b) & 0xFFFFFFFF

    def draw() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        x = imul(state ^ (state >> 15), state | 1)
        x ^= (x + imul(x ^ (x >> 7), x | 61)) & 0xFFFFFFFF
        return ((x ^ (x >> 14)) & 0xFFFFFFFF) / 4294967296

    return draw


def gaussian(rng: Callable[[], float]) -> float:
    u1 = 1 - rng()
    u2 = rng()
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def main(source: str = URL) -> tuple[float, float, int]:
    s, sigma, fps, w = signal(load(source))
    rng = mulberry32(SEED)
    noisy = [[v + sd * gaussian(rng) for v, sd in zip(s, sigma, strict=True)] for _ in range(DRAWS)]
    ok = [c for c in (cadence(x, fps) for x in noisy) if math.isfinite(c)]
    mean = sum(ok) / len(ok)
    spread = math.sqrt(sum((c - mean) ** 2 for c in ok) / (len(ok) - 1))
    print(f"cadence {cadence(s, fps):.4f} steps/s")
    print(f"sd {spread:.4f} over {len(ok)} of {DRAWS} noisy copies")
    print(f"published {w['cadence_hz']} +- {w['cadence_sd_hz']}")
    return cadence(s, fps), spread, len(ok)


if __name__ == "__main__":
    main(*sys.argv[1:])
