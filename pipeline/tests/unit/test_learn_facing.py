"""The script of lesson 11's "Reproduce it" (`tracklab/learn/facing.py`) on the published clips.

It runs on the two hook clips under `web/public/data/pose/`, which are versioned, so this runs in
CI. The facing of a skeleton built at a known angle must come back exactly, the heading must be the
central difference (exact on a path whose tangent is known), and on the clips the script's figures
must be an independent numpy computation's to the last bit. `test_learn_browser.py` sets the same
figures against `facing.browser.sql`, so the SQL, the script and (through the e2e) the page agree
at the three decimals the page prints.

Mutations checked by hand, each restored: the normal on the far side of the nose (the sign of
`side` flipped) fails `test_a_rotated_skeleton_faces_where_it_was_built` on every angle; the
heading from the frame itself to the frame after fails `test_a_synthetic_player_on_a_bending_path`
and the browser check of `test_learn_browser.py`; `wrap` into [-180, 180) fails
`test_wrap_and_circular`.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tracklab.learn import browser
from tracklab.learn import facing as script

REPO = Path(__file__).resolve().parents[3]
CLIPS = sorted((REPO / "web" / "public" / "data" / "pose").glob("hook_*.json"))
Joints = tuple[list[float], list[float], list[float]]


def skeleton(deg: float, ahead: float = 15.0, half_width: float = 20.0) -> Joints:
    """Left shoulder, right shoulder and nose of a skeleton facing `deg`."""
    u = (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
    leftward = (-u[1], u[0])
    left = [half_width * leftward[0], half_width * leftward[1]]
    right = [-half_width * leftward[0], -half_width * leftward[1]]
    nose = [ahead * u[0], ahead * u[1]]
    return left, right, nose


def test_there_are_clips_to_check() -> None:
    assert len(CLIPS) == 2


@pytest.mark.parametrize("deg", [-170, -90, -45, 0, 30, 90, 135, 180])
def test_a_rotated_skeleton_faces_where_it_was_built(deg: float) -> None:
    left, right, nose = skeleton(deg)
    assert script.facing_deg(left, right, nose) == pytest.approx(script.wrap(deg), abs=1e-9)
    # Which shoulder is called left does not matter: the nose picks the side.
    assert script.facing_deg(right, left, nose) == pytest.approx(script.wrap(deg), abs=1e-9)
    left, right, nose = skeleton(deg, ahead=-15)
    back = script.facing_deg(left, right, nose)
    assert back == pytest.approx(script.wrap(deg + 180), abs=1e-9)
    assert script.facing_deg([-20, 0], [20, 0], [5, 0]) is None


def test_wrap_and_circular() -> None:
    assert [script.wrap(d) for d in (190, -190, 180, -180, 540, 0)] == [-170, 170, 180, 180, 180, 0]
    mean, length = script.circular([170, -170])
    assert mean == pytest.approx(180, abs=1e-9)
    assert length == pytest.approx(math.cos(math.radians(10)), abs=1e-12)
    assert script.circular([0, 90, 180, -90])[1] < 1e-12


SLOW = {1: (40, 8), 2: (40, 8), 3: (42, 9)}


def synthetic_clip(slow: bool = False) -> dict[str, Any]:
    """One player on x = 20k, y = 2k² cm (the tangent's slope at k is k/5), facing 30° in every
    frame, with no skeleton in frame 5 and missing from frame 9. With `slow`, frames 1 to 3 sit
    at SLOW's positions: frame 2 moves, but under the floor of speed, and 1 and 3 keep a
    neighbour that moved."""
    left, right, nose = skeleton(30)
    xyz = [nose + [150]] + [[0, 0, 0]] * 5 + [left + [150], right + [150]]
    names = ["nose", "a", "b", "c", "d", "e", "lShoulder", "rShoulder"]
    frames = []
    for k in range(12):
        joints = None if k == 5 else [xyz, [80] * 8]
        x, y = SLOW[k] if slow and k in SLOW else (20 * k, 2 * k * k)
        p = [] if k == 9 else [[0, x, y, None, joints]]
        frames.append({"f": 100 + k, "t": 40 * k, "ball": [0, 0, 1], "p": p})
    players = [{"player_id": 1, "team_id": 2, "number": 3}]
    windows = [{"player": 0}]
    return {"fps": 25, "joints": names, "players": players, "windows": windows, "frames": frames}


def test_a_synthetic_player_on_a_bending_path() -> None:
    frames = script.frames_of(synthetic_clip(), 0)
    assert [fr["f"] - 100 for fr in frames] == [1, 2, 3, 4, 6, 7]
    for fr in frames:
        k = fr["f"] - 100
        tangent = math.degrees(math.atan(k / 5))
        assert fr["facing"] == pytest.approx(30, abs=1e-9)
        assert fr["heading"] == pytest.approx(tangent, abs=1e-9)
        assert fr["relative"] == pytest.approx(script.wrap(30 - tangent), abs=1e-9)
        assert fr["speed"] == pytest.approx(math.hypot(40, 8 * k) / 100 / 0.08, abs=1e-9)


def test_a_frame_below_the_floor_of_speed_is_dropped() -> None:
    frames = script.frames_of(synthetic_clip(slow=True), 0)
    assert [fr["f"] - 100 for fr in frames] == [1, 3, 4, 6, 7]
    # Frame 2 moved 2 cm by 1 cm over the two frame steps: well under the floor, not still.
    assert 0 < math.hypot(2, 1) / 100 / 0.08 < script.MIN_SPEED


def test_the_browser_sql_agrees_with_the_script_on_a_synthetic_clip(tmp_path: Path) -> None:
    """The SQL twin on a clip with a slow frame, a frame without a skeleton and a missing frame,
    where the published hook player has none of the three: every rule of the query is exercised
    against the script's, at the decimals the page prints."""
    public = tmp_path / "public"
    (public / "data" / "pose").mkdir(parents=True)
    clip = synthetic_clip(slow=True)
    (public / "data" / "pose" / "hook_1925299.json").write_text(json.dumps(clip), "utf-8")
    rows = browser.run(browser.read("facing"), public)
    assert rows["learn.hook.1925299.frames"] == "5"
    assert rows["learn.hook.1925299.first_frame_id"] == "101"
    assert browser.compare(rows, browser.EXPECT["facing"](public)) == []


def independent(clip: dict[str, Any], player: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The same three angles by numpy, vectorised over the player's frames."""
    names = clip["joints"]
    nose_i, l_i, r_i = (names.index(j) for j in ("nose", "lShoulder", "rShoulder"))
    rows = {fr["f"]: p for fr in clip["frames"] for p in fr["p"] if p[0] == player}
    fs = sorted(f for f in rows if f - 1 in rows and f + 1 in rows and rows[f][4] is not None)
    fs = [f for f in fs if all(rows[f][4][0][j] is not None for j in (nose_i, l_i, r_i))]
    before = np.array([rows[f - 1][1:3] for f in fs], float)
    after = np.array([rows[f + 1][1:3] for f in fs], float)
    left = np.array([rows[f][4][0][l_i][:2] for f in fs], float)
    right = np.array([rows[f][4][0][r_i][:2] for f in fs], float)
    nose = np.array([rows[f][4][0][nose_i][:2] for f in fs], float)
    d = after - before
    speed = np.hypot(d[:, 0], d[:, 1]) / 100 * clip["fps"] / 2
    s = left - right
    n = nose - (left + right) / 2
    side = s[:, 1] * n[:, 0] - s[:, 0] * n[:, 1]
    one = np.stack([s[:, 1], -s[:, 0]], 1)
    normal = np.where((side > 0)[:, None], one, -one)
    keep = (side != 0) & (speed > script.MIN_SPEED)
    facing = np.degrees(np.arctan2(normal[keep, 1], normal[keep, 0]))
    facing = 180 - np.mod(180 - facing, 360)
    heading = np.degrees(np.arctan2(d[keep, 1], d[keep, 0]))
    relative = 180 - np.mod(180 - (facing - heading), 360)
    return facing, heading, relative


@pytest.mark.parametrize("path", CLIPS, ids=lambda p: p.stem)
def test_the_hook_player_of_each_clip(path: Path) -> None:
    clip = json.loads(path.read_text("utf-8"))
    hook = clip["windows"][0]["player"]
    frames = script.frames_of(clip, hook)
    assert len(frames) >= 25
    facing, heading, relative = independent(clip, hook)
    assert len(frames) == len(facing)
    np.testing.assert_allclose([fr["facing"] for fr in frames], facing, rtol=0, atol=1e-9)
    np.testing.assert_allclose([fr["heading"] for fr in frames], heading, rtol=0, atol=1e-9)
    np.testing.assert_allclose([fr["relative"] for fr in frames], relative, rtol=0, atol=1e-9)
    assert all(-180 < fr["relative"] <= 180 for fr in frames)
    s = script.summary(frames)
    assert s["median_abs"] == pytest.approx(float(np.median(np.abs(relative))), abs=1e-9)
    sin, cos = np.sin(np.radians(relative)).mean(), np.cos(np.radians(relative)).mean()
    assert s["circ_mean"] == pytest.approx(math.degrees(math.atan2(sin, cos)), abs=1e-9)
    assert s["resultant"] == pytest.approx(math.hypot(sin, cos), abs=1e-12)
    assert s["circ_var"] == pytest.approx(1 - s["resultant"], abs=1e-12)
    assert s["off_pct"] == pytest.approx(100 * np.mean(np.abs(relative) > 45), abs=1e-9)


@pytest.mark.parametrize("path", CLIPS, ids=lambda p: p.stem)
def test_main_prints_three_decimals_per_frame(
    path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = script.main(str(path))
    out = capsys.readouterr().out.splitlines()
    clip = json.loads(path.read_text("utf-8"))
    frames = script.frames_of(clip, clip["windows"][0]["player"])
    lines = out[3 : 3 + len(frames)]
    assert len(lines) == s["frames"] == len(frames)
    for line, fr in zip(lines, frames, strict=True):
        f, *angles = line.split()
        assert int(f) == fr["f"]
        keys = ("speed", "facing", "heading", "relative")
        assert angles == [f"{fr[k]:.3f}" for k in keys]
    assert out[3 + len(frames)] == f"median |relative| {s['median_abs']:.3f}"
    assert f"circular variance {s['circ_var']:.3f}" in out[4 + len(frames)]


def test_another_player_by_index(capsys: pytest.CaptureFixture[str]) -> None:
    clip = json.loads(CLIPS[0].read_text("utf-8"))
    hook = clip["windows"][0]["player"]
    others = [i for i in range(len(clip["players"])) if i != hook]
    other = next(i for i in others if len(script.frames_of(clip, i)) >= 25)
    s = script.main(str(CLIPS[0]), str(other))
    assert f"player index {other}," in capsys.readouterr().out
    assert s["frames"] == len(script.frames_of(clip, other))


def test_the_script_needs_only_the_standard_library() -> None:
    nodes = list(ast.walk(ast.parse(Path(script.__file__).read_text("utf-8"))))
    names = {a.name.split(".")[0] for n in nodes if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in nodes if isinstance(n, ast.ImportFrom)}
    assert names <= {"json", "math", "statistics", "sys", "urllib", "typing"}
