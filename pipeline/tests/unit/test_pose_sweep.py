"""The synthetic sweep of task 60 (`tracklab.pose.sweep`), phase B1.

No data is read: the sweep's only input is the `mae` of the versioned clip
(`web/public/data/pose/1925299_phase406.json`), so every test runs in CI. The whole sweep takes
about a minute and a half; `tracklab pose sweep --check` regenerates it all, and here a sample of
its rows is regenerated against `reports/pose_sweep.json`, a tiny grid exercises the command,
and the sweep's two signals are rebuilt from a whole body through `gait`.

Mutations, each applied, seen failing and restored (tasks/todo.md, task 60, phase B1): the sign
of h under the swap, the lean turning the wrong way, the lift on the wrong foot, a row's seed
taken from its place in the grid, the bar judged at the wrong rho.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from tracklab.pose import gait, sweep
from tracklab.pose.jsonl import JOINTS

Array = NDArray[np.float64]

ROOT = Path(__file__).resolve().parents[3]
CLIP = ROOT / "web" / "public" / "data" / "pose" / "1925299_phase406.json"
VERSIONED = ROOT / "pipeline" / "reports" / sweep.SWEEP_NAME
TINY = replace(
    sweep.PROTOCOL,
    widths=(25, 50),
    caps_cm=(20,),
    cadences_hz=(3.0, 4.3),
    rhos=(0.0, 0.8),
    windows_s=300,
    windows_h=40,
    lifts_m=(0.3,),
    kzs=(1.0,),
    lean_deg=(20,),
)


@pytest.fixture(scope="module")
def clip() -> tuple[float, Array, str]:
    raw = CLIP.read_bytes()
    fps, mae = sweep.clip_mae(json.loads(raw))
    return fps, mae, hashlib.sha256(raw).hexdigest()


def _body(
    w: sweep.Windows,
    i: int,
    rng: np.random.Generator,
    *,
    fps: float,
    cadence: float,
    separation: float,
    lift: float,
    kz: float,
    swap: bool,
    lean_deg: float,
) -> tuple[Array, Array]:
    """Window i of `w` as 29 joints on the pitch and the player's x, y: a body of the test's own
    (random rest offsets, the ankles 0.88 m under midHip), the ankles swung and lifted as the
    sweep's model says, the whole body turned by the lean in its (forward, up) plane, the labels
    of the ankles exchanged where the right one is ahead (swap), and the error of `w` put on the
    ankles (along d and in z; a random share across d, which s must not see) and a random one
    on every other joint, midHip included."""
    width = w.mae.shape[1]
    t = np.arange(width) / fps
    psi = math.pi * cadence * t + w.phase[i]
    rest = rng.uniform(-0.3, 0.3, size=(len(JOINTS), 3))
    rest[gait.MIDHIP] = 0.0
    body = np.repeat(rest[None], width, axis=0)  # (frames, joints, forward/left/up)
    la, ra = gait.L_ANKLE, gait.R_ANKLE
    body[:, la] = (0.0, 0.10, -0.88)
    body[:, ra] = (0.0, -0.10, -0.88)
    body[:, la, 0] += 0.5 * separation * np.sin(psi)
    body[:, ra, 0] -= 0.5 * separation * np.sin(psi)
    body[:, la, 2] += lift * np.maximum(np.cos(psi), 0.0)
    body[:, ra, 2] += lift * np.maximum(-np.cos(psi), 0.0)
    a = math.radians(lean_deg)
    f, z = body[:, :, 0].copy(), body[:, :, 2].copy()
    body[:, :, 0] = f * math.cos(a) - z * math.sin(a)
    body[:, :, 2] = f * math.sin(a) + z * math.cos(a)
    if swap:
        behind = body[:, la, 0] - body[:, ra, 0] < 0
        body[behind, la], body[behind, ra] = body[behind, ra].copy(), body[behind, la].copy()
    heading = rng.uniform(0.0, 2.0 * math.pi)
    d = np.array([math.cos(heading), math.sin(heading)])
    n = np.array([-d[1], d[0]])
    xy = rng.uniform(-40.0, 40.0, size=2) + np.outer(5.5 * t, d)
    joints = np.empty((width, len(JOINTS), 3))
    joints[:, :, :2] = xy[:, None, :] + body[:, :, 0:1] * d + body[:, :, 1:2] * n
    joints[:, :, 2] = 1.0 + body[:, :, 2]
    joints += rng.normal(0.0, 0.1, size=joints.shape)  # every joint's error, midHip's included
    for side, joint in enumerate((la, ra)):
        across = rng.standard_normal(width)
        error = w.mae[i, :, side, None] * (w.along[i, :, side, None] * d + across[:, None] * n)
        joints[:, joint, :2] = xy + body[:, joint, 0:1] * d + body[:, joint, 1:2] * n + error
        assert w.up is not None
        joints[:, joint, 2] = 1.0 + body[:, joint, 2] + kz * w.mae[i, :, side] * w.up[i, :, side]
    return joints, xy


@pytest.mark.parametrize(
    ("kind", "lift", "swap", "lean"),
    [("sane", 0.3, False, 0), ("swap", 0.3, True, 0), ("lean", 0.0, False, 20),
     ("lean_lifted", 0.3, False, 10), ("flat_h", 0.0, False, 0)],
)  # fmt: skip
def test_the_sweep_draws_the_s_and_h_gait_reads_from_a_whole_body(
    clip: tuple[float, Array, str], kind: str, lift: float, swap: bool, lean: int
) -> None:
    """The sweep draws s and h directly; a body of 29 joints built from the same draws gives,
    through `gait.centre_on_midhip`, `gait.direction`, `gait.signal` and `gait.signal_h`, the
    same two signals to 1e-12 m, at rho 0.8 and kz 1.5."""
    fps, mae, _ = clip
    rng = np.random.default_rng(64)
    w = sweep.draw_windows(
        rng, 12, width=37, mae_rows_cm=sweep.under_cap(mae, 20), rho=0.8, vertical=True
    )
    planted = {"cadence_hz": 3.5, "separation_m": 1.2, "lift_m": lift, "kz": 1.5}
    s, h = sweep.signals(w, fps=fps, swap=swap, lean_deg=lean, **planted)
    assert h is not None
    for i in range(12):
        joints, xy = _body(
            w, i, rng, fps=fps, cadence=3.5, separation=1.2, lift=lift, kz=1.5, swap=swap,
            lean_deg=lean,
        )  # fmt: skip
        centred = gait.centre_on_midhip(joints)
        np.testing.assert_allclose(gait.signal(centred, gait.direction(xy)), s[i], atol=1e-12)
        np.testing.assert_allclose(gait.signal_h(centred), h[i], atol=1e-12)


def test_a_row_is_its_key_and_the_noise_pool_is_the_twin(clip: tuple[float, Array, str]) -> None:
    """A row's stream comes from the seed and the row's own key, never from its place in the
    grid: the same row out of a one-row grid and out of a bigger one. `noise_pool` regenerates
    the twin's windows (the same NaN count and median) and adds its Monte Carlo copies."""
    fps, mae, sha = clip
    report = sweep.build_sweep(mae, fps, sha, TINY)
    g = TINY
    keys = [
        (w, c, f, r) for w in g.widths for c in g.caps_cm for f in g.cadences_hz for r in g.rhos
    ]
    assert [tuple(r[:4]) for r in report["s_rows"]["rows"]] == keys  # the grid's order
    alone = replace(TINY, widths=(50,), cadences_hz=(4.3,), rhos=(0.8,))
    assert sweep.s_row(mae, fps, alone, 50, 20, 4.3, 0.8) in report["s_rows"]["rows"]
    twin = next(r for r in report["noise_twins"]["rows"] if r[:3] == [50, 20, 0.8])
    pool = sweep.noise_pool(mae, fps, width=50, cap=20, rho=0.8, grid=TINY, draws=20)
    assert pool.cadence.shape == (TINY.windows_s,) and pool.draws.shape == (TINY.windows_s, 20)
    assert int(np.sum(np.isnan(pool.cadence))) == twin[4]
    assert round(float(np.nanmedian(pool.cadence)), 6) == twin[6]
    assert 0.5 < float(np.mean(np.isnan(pool.draws))) < 1.0  # noise on noise: mostly NaN


def test_the_bar_is_judged_on_every_cadence_at_rho_0_only(clip: tuple[float, Array, str]) -> None:
    fps, mae, sha = clip
    report = sweep.build_sweep(mae, fps, sha, TINY)
    rows = report["s_rows"]["rows"]
    for cell in report["bar"]["cells"]:
        at_0 = [r for r in rows if r[:2] == [cell["width"], cell["cap_cm"]] and r[3] == 0.0]
        assert len(at_0) == len(TINY.cadences_hz)
        assert cell["passes"] == all(r[-1] for r in at_0)
        assert cell["failing_cadences_hz"] == [r[2] for r in at_0 if not r[-1]]
    for r in rows:
        nan_ok = r[5] <= sweep.BAR_NAN * r[4]
        assert r[-1] == (r[8] is not None and r[8] <= sweep.BAR_P95 and nan_ok)


def test_the_command_writes_the_same_bytes_twice_and_check_sees_a_changed_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reports = tmp_path / "reports"
    assert sweep.run_pose_sweep(reports, CLIP, check=True, grid=TINY) == 1  # nothing yet
    assert sweep.run_pose_sweep(reports, CLIP, grid=TINY) == 0
    target = reports / sweep.SWEEP_NAME
    first = target.read_bytes()
    assert sweep.run_pose_sweep(reports, CLIP, grid=TINY) == 0
    assert target.read_bytes() == first
    assert sweep.run_pose_sweep(reports, CLIP, check=True, grid=TINY) == 0
    assert "FULL" in capsys.readouterr().out
    text = first.decode()
    target.write_text(text.replace('"seed": 60', '"seed": 61', 1), encoding="utf-8", newline="\n")
    assert sweep.run_pose_sweep(reports, CLIP, check=True, grid=TINY) == 1
    assert sweep.run_pose_sweep(reports, tmp_path / "no_clip.json", grid=TINY) == 1


def test_the_versioned_sweep_holds_the_protocol_and_regenerates_on_a_sample(
    clip: tuple[float, Array, str],
) -> None:
    """`reports/pose_sweep.json` carries the protocol's grid, seed and clip; a sample of its
    rows (the near tie of W 37, cap 25 and 2.5 Hz among them) comes back from the code as
    written, every row's key is in the grid's order, and the bar's flags and cells follow the
    rows with today's constants. The whole file is `pose sweep --check`'s, which CI runs."""
    fps, mae, sha = clip
    v = json.loads(VERSIONED.read_text(encoding="utf-8"))
    g = sweep.PROTOCOL
    assert v["seed"] == g.seed and v["source"]["sha256"] == sha
    p = v["parameters"]
    assert (p["widths"], p["caps_cm"], p["cadences_hz"], p["rhos"]) == (
        list(g.widths), list(g.caps_cm), list(g.cadences_hz), list(g.rhos)
    )  # fmt: skip
    assert (p["windows_s"], p["windows_h"], p["lifts_m"], p["kzs"]) == (
        40_000, 400, [round(0.10 + 0.05 * i, 2) for i in range(11)], [1.0, 1.5]
    )  # fmt: skip
    assert (p["swap_lift_m"], p["lean_deg"], p["band_z"]) == (
        g.swap_lift_m, list(g.lean_deg), gait.BAND_Z
    )  # fmt: skip
    assert p["separation_m"] == round(g.separation_m, 6)
    rows = v["s_rows"]["rows"]
    keys = [
        (w, c, f, r) for w in g.widths for c in g.caps_cm for f in g.cadences_hz for r in g.rhos
    ]
    assert [tuple(r[:4]) for r in rows] == keys  # every row, in the grid's order
    twins = [(w, c, r) for w in g.widths for c in g.caps_cm for r in g.rhos]
    assert [tuple(r[:3]) for r in v["noise_twins"]["rows"]] == twins
    h_keys = [
        (k, s["width"], s["cap"], s["cadence"], s["rho"], s["kz"], s["lift"], s["lean"])
        for k, s in sweep._h_specs(g)
    ]
    assert [tuple(r[:8]) for r in v["h_rows"]["rows"]] == h_keys
    assert len(rows) == 144 and len(twins) == 36 and len(h_keys) == 4392
    assert all(r[-1] == sweep.meets_bar(r) for r in rows)  # the flags, with today's bar
    for key in ((37, 25, 2.5, 0.0), (25, 15, 3.0, 0.9)):
        assert sweep.s_row(mae, fps, g, *key) in rows
    assert sweep.twin_row(mae, fps, g, 37, 20, 0.5) in v["noise_twins"]["rows"]
    h_rows = v["h_rows"]["rows"]
    seen: set[str] = set()
    for kind, spec in sweep._h_specs(g):
        if kind not in seen and spec["width"] == 37 and spec["rho"] == 0.5 and spec["kz"] == 1.5:
            seen.add(kind)
            assert sweep.h_row(mae, fps, g, kind, spec) in h_rows
    assert seen == {"sane", "no_gait", "flat_h", "swap", "lean"}
    assert v["bar"]["cells"] == sweep.bar_cells(rows, g)
