"""The second time of the probe (`tracklab.pose.verdict`, task 60, phase B2), on runners written
by hand and a throwaway repository whose protocol is frozen: no real pose is read.

Twelve runners, each with his own cadence (2.6 to 3.48 Hz), 0.3 Hz faster in the high band
than in the low one: M1 and M2 keep P6 alive, the verdict carries M4's half IQR, and once it is
committed the guard opens. The Monte Carlo of each window has its own seed.

Mutations, each applied, seen failing and restored (tasks/todo.md, task 60, phase B2): one seed
for every window (`seed=gait.SEED` in `window_estimates`); the verdict's `alive` not following
its figures in `consistency_problems`; the second time run on code committed after the freeze
or on another numpy than the design's.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tracklab.pose import data, sweep, verdict
from tracklab.pose.data import load_players
from tracklab.runs.protocol import seal

REPORTS = Path(__file__).resolve().parents[2] / "reports"


def squad(kit: SimpleNamespace, players: int = 12, base: float = 2.6) -> list[Any]:
    """Per player a high stretch (6 m/s, 250 frames: five windows of 50) at his cadence + 0.3
    Hz and a low one (4 m/s, frames 1000 on) at his cadence."""
    bodies = []
    for p in range(players):
        cadence = base + 0.08 * p
        bodies.append(kit.runner(100 + p, start=0, n=250, speed_m_s=6.0, cadence_hz=cadence + 0.3))
        bodies.append(kit.runner(100 + p, start=1000, n=250, speed_m_s=4.0, cadence_hz=cadence))
    return bodies


@pytest.fixture
def frozen_repo(pose_repo: Any) -> Any:
    """The throwaway repository frozen at W 50, cap 20, with the versioned sweep in its
    reports (the second time reads its rows of h)."""
    reports = pose_repo.root / "pipeline" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPORTS / sweep.SWEEP_NAME, reports / sweep.SWEEP_NAME)
    pose_repo.commit(pose_repo.frozen(50, 20), "frozen")
    return pose_repo


def test_every_window_draws_its_own_noise(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    """Two players with the very same body in the same frames, and one player with the same
    body again 1,000 frames later: three windows whose inputs are identical, three Monte
    Carlos that are not (the seed is the match, the player and the window's first frame)."""
    body = pose_kit.runner(1, start=0, n=50, speed_m_s=6.0)
    twin = pose_kit.Body(2, body.frames, body.periods, body.x, body.y, body.joints, body.mae_cm)
    later = pose_kit.Body(
        1, body.frames + 1000, body.periods, body.x, body.y, body.joints, body.mae_cm
    )
    root = pose_kit.write_bronze(tmp_path / "data", pose_kit.calibration, [body, twin, later])
    windows = verdict.window_estimates(load_players(root, pose_kit.calibration), 50, 20, draws=8)
    assert [(w.player_id, w.frame) for w in windows] == [(1, 0), (1, 1000), (2, 0)]
    assert windows[0].estimate == windows[1].estimate == windows[2].estimate
    draws = [w.draws for w in windows]
    assert all(d is not None and d.shape == (8, 4) for d in draws)
    # NaN draws compare equal here: identical streams must not pass for different ones
    assert not np.array_equal(draws[0], draws[1], equal_nan=True)  # another frame
    assert not np.array_equal(draws[0], draws[2], equal_nan=True)  # another player
    assert np.array_equal(draws[0], draws[0].copy(), equal_nan=True)


def test_the_second_time_writes_a_verdict_that_opens_the_guard_once_committed(
    frozen_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reports = frozen_repo.root / "pipeline" / "reports"
    root = pose_kit.write_bronze(tmp_path / "data", pose_kit.calibration, squad(pose_kit))
    frozen_repo.calibration(rows=6000)  # 12 players x 500 rows, as the first time counted
    assert verdict.run_pose_verdict(root, reports) == 0
    path = reports / verdict.VERDICT_NAME
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    v = payload["verdict"]
    assert (v["M1"]["players"], v["M2"]["players_with_both"], v["M2"]["positive"]) == (12, 12, 12)
    assert v["alive"] is True and v["dies_at"] is None
    assert payload["m4"]["half_iqr_hz"] == v["M2"]["half_iqr_hz"] > v["M2"]["median_sd_hz"]
    assert payload["inputs"]["rows"] == 6000
    assert payload["protocol"]["stage"] == "frozen"
    assert payload["code_tree_sha"] == data.code_tree_sha()
    assert {r[0] for r in payload["nan_rates"]["rows"]} == {"low", "high"}
    assert [r[:2] for r in payload["slope_h_on_s"]["rows"]] == [
        [0.0, 30.0],
        [30.0, 60.0],
        [60.0, 90.0],
    ]
    assert payload["slope_h_on_s"]["rows"][0][2] == 60  # every runner goes along x
    assert payload["cad_s_distribution"]["swap"]  # the sweep's blind spot beside
    assert verdict.run_pose_verdict(root, reports, check=True) == 0
    assert "FULL 1/1 recomputed and equal" in capsys.readouterr().out
    assert verdict.run_pose_verdict(tmp_path / "empty", reports, check=True) == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out

    with pytest.raises(data.HeldOutLocked, match="holds no"):
        data.assert_confirmation_open()
    frozen_repo.commit(None, "verdict")
    data.assert_confirmation_open()  # frozen, its verdict alive in HEAD, clean: open

    lying = json.loads(text)
    lying["verdict"]["alive"] = False
    path.write_text(verdict._render(seal(lying)), encoding="utf-8")
    assert verdict.run_pose_verdict(tmp_path / "empty", reports, check=True) == 1
    assert "verdict does not follow its figures" in capsys.readouterr().out
    path.write_text(text, encoding="utf-8")


def test_the_second_time_runs_only_on_the_designs_numpy(
    frozen_repo: Any,
    pose_kit: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = frozen_repo.root / "pipeline" / "reports"
    root = pose_kit.write_bronze(tmp_path / "data", pose_kit.calibration, squad(pose_kit, 2))
    real = verdict.importlib.metadata.version
    monkeypatch.setattr(
        verdict.importlib.metadata,
        "version",
        lambda name: "0.0.1" if name == "numpy" else real(name),
    )
    assert verdict.run_pose_verdict(root, reports) == 1
    assert "numpy 0.0.1" in capsys.readouterr().out
    assert not (reports / verdict.VERDICT_NAME).exists()


def test_the_second_time_refuses_a_design_or_code_after_the_freeze(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reports = pose_repo.root / "pipeline" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPORTS / sweep.SWEEP_NAME, reports / sweep.SWEEP_NAME)
    pose_repo.commit(None, "the sweep")
    root = pose_kit.write_bronze(tmp_path / "data", pose_kit.calibration, squad(pose_kit, 2))
    assert verdict.run_pose_verdict(root, reports) == 1  # the protocol is in design
    assert "stage 'design'" in capsys.readouterr().out
    pose_repo.commit(pose_repo.frozen(50, 20), "frozen")
    (pose_repo.root / data.CODE_IN_REPO / "gait.py").write_text("# after\n", encoding="utf-8")
    pose_repo.commit(None, "code after the freeze")
    assert verdict.run_pose_verdict(root, reports) == 1
    assert "not the one the freeze recorded" in capsys.readouterr().out
    assert not (reports / verdict.VERDICT_NAME).exists()
