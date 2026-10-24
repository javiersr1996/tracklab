"""`tracklab learn hypotheses` (task 87): lesson 1's hypotheses next to P3's kept flights.

The synthetic flights are exact parabolas, so every half window gives the same g and a bin's
median is that g; the distances from the shot's start are set by hand, so a bin edge moved by one
frame changes a count. The published file is checked against `quality.json` here too: both are in
git, so CI compares them even without the warehouse.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracklab.learn.hypotheses import (
    HALF_WINDOWS,
    START_BINS,
    _p3_problems,
    g_at,
    match_figures,
    run_learn_hypotheses,
)
from tracklab.quality.flight import apparent_g
from tracklab.quality.gravity import BB_HALF, Sample

PUBLIC = Path(__file__).resolve().parents[3] / "web" / "public" / "data"
FPS = 25


def window(apex: int, g: float) -> list[Sample]:
    out = []
    for k in range(-BB_HALF, BB_HALF + 1):
        u = k / FPS
        out.append((apex + k, (apex + k) / FPS, 0.0, 0.0, 4.0 - g * u * u / 2))
    return out


def test_the_bins_split_the_frames_from_the_start() -> None:
    assert START_BINS == ((0, 4), (5, 9), (10, None))
    # The window starts at apex - 10: these starts put it -1, 0, 4, 5, 9 and 10 frames after.
    apex = 1000
    distances = [-1, 0, 4, 5, 9, 10]
    flights = [(apex - BB_HALF - d, window(apex, 9.0 + i / 10)) for i, d in enumerate(distances)]
    fig = match_figures(flights)
    assert fig["before_start"] == 1
    assert [b["n"] for b in fig["by_frames_from_start"]] == [2, 2, 1]
    assert [b["g_median"] for b in fig["by_frames_from_start"]] == [9.15, 9.35, 9.5]
    assert fig["frames_from_start_median"] == 4.5
    assert fig["flights"] == len(distances)


def test_every_half_window_of_a_parabola_gives_its_g() -> None:
    w = window(500, 8.5)
    assert g_at(w, BB_HALF) == pytest.approx(apparent_g([s[1] for s in w], [s[4] for s in w]))
    fig = match_figures([(480, w), (481, window(700, 8.5))])
    assert set(fig["g_median_by_half_window"]) == {str(h) for h in HALF_WINDOWS}
    assert all(v == 8.5 for v in fig["g_median_by_half_window"].values())


def test_an_empty_bin_has_no_median() -> None:
    fig = match_figures([(1000 - BB_HALF - 7, window(1000, 9.0))])
    assert [b["g_median"] for b in fig["by_frames_from_start"]] == [None, 9.0, None]


def test_the_published_file_gives_quality_json_at_p3s_window() -> None:
    payload = json.loads((PUBLIC / "learn" / "gravity.json").read_text("utf-8"))
    assert len(payload["matches"]) == 10
    assert _p3_problems(payload, PUBLIC / "quality.json") == []
    payload["matches"][0]["g_median_by_half_window"][str(BB_HALF)] += 0.0001
    assert len(_p3_problems(payload, PUBLIC / "quality.json")) == 1


def test_check_is_partial_without_silver_and_bronze(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, quality = PUBLIC / "learn" / "gravity.json", PUBLIC / "quality.json"
    assert run_learn_hypotheses(tmp_path / "nowhere", out, quality, check=True) == 0
    assert "PARTIAL 0/10" in capsys.readouterr().out
