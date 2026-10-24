"""Entry angles of the made shots of one basketball match, from the provider's public files.

Lesson 8 of /learn ("At what angle does the ball reach the rim?") shows this file as "Reproduce
it". It needs Python 3 and nothing else: run it in a match folder of SkillCorner's public
basketball bundle, or give it one.

    python entry.py                          # in data/matches/114086
    python entry.py data/matches/114099      # any other match

The method is Track Lab's entry-angle check, written out in full:

1. The shots: every made, unblocked field goal of `<id>_dynamic_events.json` with a start frame,
   an end frame and a distance.
2. The ball: every frame of `<id>_tracking_data.jsonl.gz` with a period and a ball position, in
   metres (1 ft = 0.3048 m), at time frame / 25 s.
3. For each shot, the first ball sample at or after `startFrame` + 2 and the 39 after it; the shot
   is dropped if there are not 40. Of those 40, count the pairs one frame apart, add one, and keep
   that many samples from the start: the run (dropped if under 12).
4. On the run: the horizontal speed v_h is the median of the speeds between the first 8 samples
   (dropped under 4 ft/s); the flight time is T = D / v_h, D the horizontal distance from the first
   sample to the rim's centre (dropped outside 0.6 to 1.6 s); the arrival is sample k = round(T /
   0.04) of the run (dropped past its end).
5. The reported angle: the least-squares slope of z on t over samples max(k - 6, 2) to k, against
   v_h. The required angle: a projectile from the first sample's height that reaches the rim,
   3.048 m, after T under standard gravity; its vertical speed there, against v_h.

It prints the shots kept, the median of each angle, the median gap (required minus reported) and
the share of shot pairs the two angles put in a different order.
"""

import bisect
import gzip
import json
import math
import statistics
import sys
from pathlib import Path

FT = 0.3048
FPS = 25
G = 9.80665  # m/s², standard gravity
RIM_HEIGHT = 10 * FT  # 3.048 m
RIM_X = (91.86 / 2 - 5.17) * FT  # the rim's centre on the court's long axis, either end
V_H_FRAMES = 8
V_H_MIN = 4 * FT
T_MIN, T_MAX = 0.6, 1.6
TAIL_BACK, TAIL_MIN_INDEX = 6, 2
SEARCH_OFFSET = 2
SEG_LEN = 40
MIN_CONTIG = V_H_FRAMES + 4

Sample = tuple[int, float, float, float, float]  # frame, t (s), x, y, z (m)


def load(folder: Path) -> tuple[list[int], list[Sample]]:
    """The start frames of the made shots, and the ball's samples in frame order."""
    match = folder.resolve().name
    events = json.loads((folder / f"{match}_dynamic_events.json").read_text(encoding="utf-8"))
    starts = sorted(
        s["startFrame"]
        for s in events["shots"]
        if s.get("outcome") is True
        and s.get("blocked") is False
        and None not in (s.get("startFrame"), s.get("endFrame"), s.get("distance"))
    )
    samples: list[Sample] = []
    with gzip.open(folder / f"{match}_tracking_data.jsonl.gz", "rt", encoding="utf-8") as lines:
        for line in lines:
            frame = json.loads(line)
            xyz = (frame.get("ball") or {}).get("xyz")
            if frame.get("period") is None or not xyz or xyz[2] is None:
                continue
            f = frame["frameIdx"]
            samples.append((f, f * 1000 // FPS / 1000, xyz[0] * FT, xyz[1] * FT, xyz[2] * FT))
    samples.sort()
    return starts, samples


def slope(t: list[float], z: list[float]) -> float:
    """The least-squares slope of z on t."""
    tbar, zbar = sum(t) / len(t), sum(z) / len(z)
    num = sum((a - tbar) * (b - zbar) for a, b in zip(t, z, strict=True))
    return num / sum((a - tbar) ** 2 for a in t)


def flight(run: list[Sample]) -> dict[str, float] | str:
    """Step 4 and 5 on a run: v_h, D, T, k and the two angles in degrees, or why it is dropped."""
    x0, y0, z0 = run[0][2], run[0][3], run[0][4]
    rim_x = RIM_X if x0 > 0 else -RIM_X
    first = run[:V_H_FRAMES]
    speeds = []
    for a, b in zip(first, first[1:], strict=False):
        dt = b[1] - a[1]
        speeds.append(math.hypot(b[2] - a[2], b[3] - a[3]) / dt if dt > 0 else 0.0)
    v_h = statistics.median(speeds)
    if v_h < V_H_MIN:
        return "slow_ball"
    d = math.hypot(rim_x - x0, -y0)
    t_flight = d / v_h
    if not T_MIN <= t_flight <= T_MAX:
        return "bad_flight_time"
    k = round(t_flight / (1 / FPS))
    if k >= len(run):
        return "arrival_beyond_run"
    tail = run[max(k - TAIL_BACK, TAIL_MIN_INDEX) : k + 1]
    v_z = slope([s[1] - tail[0][1] for s in tail], [s[4] for s in tail])
    v_z0 = (RIM_HEIGHT - z0 + 0.5 * G * t_flight * t_flight) / t_flight
    return {
        "v_h": v_h,
        "d": d,
        "t": t_flight,
        "k": k,
        "reported": math.degrees(math.atan2(abs(v_z), v_h)),
        "required": math.degrees(math.atan2(abs(v_z0 - G * t_flight), v_h)),
    }


def run_of(samples: list[Sample], start: int) -> list[Sample] | str:
    """Step 3: the run of a shot, or why it is dropped."""
    frames = [s[0] for s in samples]
    i0 = bisect.bisect_left(frames, start + SEARCH_OFFSET)
    if i0 + SEG_LEN >= len(samples):
        return "no_window"
    seg = samples[i0 : i0 + SEG_LEN]
    n = sum(1 for a, b in zip(seg, seg[1:], strict=False) if b[0] - a[0] == 1) + 1
    return seg[:n] if n >= MIN_CONTIG else "short_run"


def summary(starts: list[int], samples: list[Sample]) -> dict[str, float | int | None]:
    pairs = []
    for start in starts:
        run = run_of(samples, start)
        got = flight(run) if not isinstance(run, str) else run
        if not isinstance(got, str):
            pairs.append((got["reported"], got["required"]))
    rep = [a for a, _ in pairs]
    req = [b for _, b in pairs]
    disagree = total = 0
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            a, b = rep[i] - rep[j], req[i] - req[j]
            if a != 0 and b != 0:
                total += 1
                disagree += (a > 0) != (b > 0)

    def median(xs: list[float]) -> float | None:
        return round(statistics.median(xs), 4) if xs else None

    return {
        "shots": len(pairs),
        "reported": median(rep),
        "required": median(req),
        "gap": median([b - a for a, b in pairs]),
        "reordered_pct": round(100 * disagree / total, 4) if total else None,
    }


def main(folder: str = ".") -> dict[str, float | int | None]:
    figures = summary(*load(Path(folder)))
    for name, value in figures.items():
        print(f"{name} {value}")
    return figures


if __name__ == "__main__":
    main(*sys.argv[1:])
