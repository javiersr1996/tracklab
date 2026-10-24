"""`tracklab learn hypotheses`: what the data add to lesson 1's hypotheses (task 87, P9).

Lesson 1 asks why the ball's apparent g sits under 9.80665 and answers two hypotheses with the
hook and synthetic flights only: the window (bias and variance) and a smoothing that reaches the
shooter's hand. This module puts real flights next to them, match by match, from the flights P3's
gravity check keeps (`quality/gravity.py`, its own helpers, unchanged: the shot's apex +-10
frames, every frame tracked, no rebound after the apex, a residual RMS under 1 ft):

- the window: on each kept flight, the g of a window of half-width H (`HALF_WINDOWS`) centred on
  the same apex, and per match the median of each. H 10 is P3's window, so its median is P3's
  `g_median`, which `--check` confirms against `quality.json`;
- the hand: the frames from the shot's `startFrame` to the window's first frame (apex - 10),
  their median, how many windows start before `startFrame`, and the median g (H 10) of the
  flights in each bin of that distance (`START_BINS`), with its n.

Writes `web/public/data/learn/gravity.json` (LF, deterministic). `--check` rebuilds the file from
silver and bronze and compares its bytes when they hold every match of the file, or runs the code
on the slice at hand (the CI fixtures) and says so: `FULL n/n` or `PARTIAL k/n`.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from tracklab.quality.flight import G, apparent_g
from tracklab.quality.gravity import (
    BB_HALF,
    BB_REASONS,
    CALIBRATION,
    Sample,
    Tally,
    Tracked,
    _ball_samples,
    _fit_or_drop,
    _rebounds,
    _shot_window,
    _shots,
)

HALF_WINDOWS = (4, 6, 8, 10)
# Frames from `startFrame` to the window's first frame: 0 to 4, 5 to 9, 10 or more.
START_BINS: tuple[tuple[int, int | None], ...] = ((0, 4), (5, 9), (10, None))
DIGITS = 4


def kept_flights(
    ball: dict[int, Tracked], shots: list[tuple[int, int | None, bool]]
) -> list[tuple[int, list[Sample]]]:
    """(startFrame, apex +-10 window) of every flight P3 keeps, with P3's filters in P3's order."""
    tally = Tally(dict.fromkeys(BB_REASONS, 0))
    out: list[tuple[int, list[Sample]]] = []
    for start, end, blocked in shots:
        if blocked:
            continue
        window = _shot_window(ball, start, end)
        if window is None or any(_rebounds(s) for s in window[BB_HALF + 1 :]):
            continue
        before = len(tally.g)
        _fit_or_drop(tally, window)
        if len(tally.g) > before:
            out.append((start, window))
    return out


def g_at(window: list[Sample], h: int) -> float:
    """The g of the window's central 2h + 1 samples, around the same apex."""
    part = window[BB_HALF - h : BB_HALF + h + 1]
    return apparent_g([s[1] for s in part], [s[4] for s in part])


def _median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), DIGITS) if xs else None


def in_bin(d: int, lo: int, hi: int | None) -> bool:
    return d >= lo and (hi is None or d <= hi)


def match_figures(flights: list[tuple[int, list[Sample]]]) -> dict[str, Any]:
    by_h = {h: [g_at(w, h) for _, w in flights] for h in HALF_WINDOWS}
    distance = [w[0][0] - start for start, w in flights]
    g10 = by_h[BB_HALF]
    return {
        "flights": len(flights),
        "g_median_by_half_window": {str(h): _median(gs) for h, gs in by_h.items()},
        "frames_from_start_median": float(statistics.median(distance)) if distance else None,
        "before_start": sum(d < 0 for d in distance),
        "by_frames_from_start": [
            {
                "n": sum(in_bin(d, lo, hi) for d in distance),
                "g_median": _median(
                    [g for g, d in zip(g10, distance, strict=True) if in_bin(d, lo, hi)]
                ),
            }
            for lo, hi in START_BINS
        ],
    }


def build(data_dir: Path) -> dict[str, Any]:
    balls = _ball_samples(data_dir)
    matches = []
    for (native, match_id), shots in sorted(_shots(data_dir).items()):
        flights = kept_flights(balls.get(("basketball", native), {}), shots)
        matches.append(
            {
                "match_id": match_id,
                "is_calibration": native in CALIBRATION,
                **match_figures(flights),
            }
        )
    if not matches:
        raise FileNotFoundError(f"no basketball shots under {data_dir / 'bronze'}")
    return {
        "schema_version": 1,
        "g_real": G,
        "half_windows": list(HALF_WINDOWS),
        "p3_half_window": BB_HALF,
        "start_bins": [[lo, hi] for lo, hi in START_BINS],
        "matches": matches,
    }


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _published(quality: Path) -> dict[str, tuple[int, float]]:
    """Basketball match id -> (flights, g_median) of quality.json."""
    rows = json.loads(quality.read_text(encoding="utf-8"))["checks"]["gravity"]
    flights = {r["match_id"]: int(r["value"]) for r in rows if r["metric"] == "flights"}
    medians = {r["match_id"]: float(r["value"]) for r in rows if r["metric"] == "g_median"}
    return {m: (n, medians[m]) for m, n in flights.items() if m.startswith("bb:") and m in medians}


def _p3_problems(payload: dict[str, Any], quality: Path) -> list[str]:
    """Matches whose flights or H 10 median are not quality.json's."""
    published = _published(quality)
    problems = []
    for m in payload["matches"]:
        want = published.get(m["match_id"])
        got = (m["flights"], m["g_median_by_half_window"][str(BB_HALF)])
        if want is None or got[0] != want[0] or got[1] != want[1]:
            problems.append(f"{m['match_id']}: {got}, quality.json {want}")
    return problems


def run_learn_hypotheses(data_dir: Path, out: Path, quality: Path, *, check: bool = False) -> int:
    if not check:
        payload = build(data_dir)
        problems = _p3_problems(payload, quality)
        if problems:
            print(f"learn hypotheses: H {BB_HALF} is not P3's: {problems}")
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(payload), encoding="utf-8", newline="\n")
        print(f"learn hypotheses: {out} ({out.stat().st_size} bytes)")
        return 0

    raw = out.read_bytes()
    if b"\r" in raw:
        print(f"learn hypotheses --check: {out.name} has CR line ends")
        return 1
    on_disk = json.loads(raw.decode("utf-8"))
    total = len(on_disk["matches"])
    problems = _p3_problems(on_disk, quality)
    if problems:
        print(
            f"learn hypotheses --check: {out.name} is not quality.json's at H {BB_HALF}: {problems}"
        )
        return 1
    shots = data_dir / "bronze" / "basketball" / "events_shots"
    have = {f"bb:{p.stem}" for p in shots.glob("*.parquet")} if shots.is_dir() else set()
    if have == {m["match_id"] for m in on_disk["matches"]}:
        if render(build(data_dir)).encode("utf-8") != raw:
            print(f"learn hypotheses --check: {out.name} differs from what silver and bronze give")
            return 1
        print(
            f"learn hypotheses --check: FULL {total}/{total}: the bytes of {out.name} rebuilt "
            f"from silver and bronze; its flights and H {BB_HALF} medians are quality.json's"
        )
        return 0
    if have:
        for m in build(data_dir)["matches"]:
            print(
                f"learn hypotheses {m['match_id']} (slice, not compared): flights={m['flights']} "
                f"by_h={m['g_median_by_half_window']}"
            )
    print(
        f"learn hypotheses --check: PARTIAL 0/{total}: the code ran on {len(have)} match(es) "
        f"at hand, not compared; {out.name}'s flights and H {BB_HALF} medians are quality.json's"
    )
    return 0
