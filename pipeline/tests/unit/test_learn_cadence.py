"""The script of lesson 5's "Reproduce it" (`tracklab/learn/cadence.py`) against the pipeline.

It runs on the two hook clips under `web/public/data/pose/`, which are versioned, so this runs in
CI. Its cadence must be the one `pose/gait.py` reads from the same s(t), to the last bit, and lie
within a hundredth of a step per second of what P6 published from the unrounded joints.

Mutations checked by hand, each restored: the cadence without the x 2, and the parabola's shift
with its sign flipped (each fails `test_the_script_reads_the_cadence_gait_reads` on both clips);
`BAND_Z` at 1.0 (these windows' peaks sit near 1 and cannot see it; on the white noise below 77
of 200 windows get a cadence instead of 12, and that test fails).
"""

from __future__ import annotations

import ast
import json
import math
import random
from pathlib import Path

import numpy as np
import pytest

from tracklab.learn import cadence as script
from tracklab.pose.gait import cadence_hz

REPO = Path(__file__).resolve().parents[3]
CLIPS = sorted((REPO / "web" / "public" / "data" / "pose").glob("hook_*.json"))


def test_there_are_clips_to_check() -> None:
    assert len(CLIPS) == 2


@pytest.mark.parametrize("path", CLIPS, ids=lambda p: p.stem)
def test_the_script_reads_the_cadence_gait_reads(path: Path) -> None:
    clip = json.loads(path.read_text("utf-8"))
    s, sigma, fps, w = script.signal(clip)
    assert len(s) == len(w["s_mm"]) == w["frame_hi"] - w["frame_lo"] + 1
    assert script.cadence(s, fps) == cadence_hz(np.array(s), fps=fps)
    # From joints in whole centimetres, against P6's from the unrounded ones.
    assert abs(script.cadence(s, fps) - w["cadence_hz"]) < 0.01
    # s(t) from the joints is the published s(t) to the centimetre the joints are written in.
    assert max(abs(a * 1000 - b) for a, b in zip(s, w["s_mm"], strict=True)) < 10
    assert all(0 < x < 0.5 for x in sigma)


@pytest.mark.parametrize("path", CLIPS, ids=lambda p: p.stem)
def test_main_prints_a_finite_sd_over_every_draw(
    path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    c, spread, valid = script.main(str(path))
    out = capsys.readouterr().out
    assert f"cadence {c:.4f} steps/s" in out
    assert valid == script.DRAWS
    assert 0 < spread < 0.2


def test_white_noise_has_no_cadence_most_of_the_time() -> None:
    rng = random.Random(1)
    noise = [[rng.gauss(0, 1) for _ in range(50)] for _ in range(200)]
    resolved = sum(math.isfinite(script.cadence(s, 25)) for s in noise)
    assert resolved < 40


def test_mulberry32_is_the_pages_generator() -> None:
    # The first three draws of mulberry32(59) in the browser (lib/learn/gravity.ts).
    rng = script.mulberry32(59)
    assert [rng() for _ in range(3)] == [
        0.39534148410893977,
        0.6137918157037348,
        0.2674006081651896,
    ]


def test_the_script_needs_only_the_standard_library() -> None:
    nodes = list(ast.walk(ast.parse(Path(script.__file__).read_text("utf-8"))))
    names = {a.name.split(".")[0] for n in nodes if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in nodes if isinstance(n, ast.ImportFrom)}
    assert names <= {"json", "math", "sys", "urllib", "collections", "typing"}
