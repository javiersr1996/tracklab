"""The probe of task 60, first time (`tracklab.pose.probe`, phase B2), on bodies written by hand
and a throwaway repository: no real pose is read, and no cadence is computed.

Mutations, each applied, seen failing and restored (tasks/todo.md, task 60, phase B2): one
period for the whole player in `admitted` (a window crosses the period change); the heels'
cap folded into the wrong ankle column; the rule choosing the greatest W, or the least cap;
`kills_the_noise` read from the first rho only.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tracklab.pose import criteria, probe, protocol, sweep
from tracklab.pose.coverage import COVERAGE_NAME
from tracklab.pose.data import load_players
from tracklab.pose.jsonl import JOINTS
from tracklab.runs.protocol import seal

PIPELINE = Path(__file__).resolve().parents[2]
REPORTS = PIPELINE / "reports"
CLIP = PIPELINE.parent / "web" / "public" / "data" / "pose" / "1925299_phase406.json"
TINY = replace(sweep.PROTOCOL, rhos=(0.0, 0.9), windows_s=400)


def _commit_real_design(pose_repo: Any, reports: Path) -> None:
    """The protocol `pose protocol` writes, with the versioned sweep's sha, in HEAD."""
    evidence = {"1925299": None, "1996435": None}
    payload = protocol.build_protocol(
        protocol.file_sha256(reports / sweep.SWEEP_NAME),
        protocol.file_sha256(reports / COVERAGE_NAME),
        [1925299, 1996435],
        evidence,
    )
    pose_repo.commit(payload, "design")


@pytest.fixture
def reports(tmp_path: Path) -> Path:
    out = tmp_path / "reports"
    out.mkdir()
    for name in (sweep.SWEEP_NAME, COVERAGE_NAME):
        shutil.copy(REPORTS / name, out / name)
    return out


def test_a_window_that_crosses_the_period_change_does_not_count(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    """A player whose 80 consecutive frames run 40 in period 1 and 40 in period 2, at 6 m/s:
    at W 25 one window in each period (three if the change were crossed), at W 50 none (one)."""
    periods = np.r_[np.full(40, 1), np.full(40, 2)]
    body = pose_kit.runner(7, start=1000, n=80, speed_m_s=6.0, period=periods)
    root = pose_kit.write_bronze(tmp_path / "data", pose_kit.calibration, [body])
    counts = probe.admitted(load_players(root, pose_kit.calibration))["counts"]
    for joints in probe.JOINT_SETS:
        assert counts[(7, 1, joints, 25, 20, "high")] == 1
        assert counts[(7, 2, joints, 25, 20, "high")] == 1
        assert sum(counts[(7, p, joints, 50, 20, b)] for p in (1, 2) for b in probe.BANDS) == 0
    table = probe.window_rows(load_players(root, pose_kit.calibration), counts)
    assert [7, 1, "ankles", 25, 20, 0, 0, 1] in table
    assert [7, 2, "ankles", 37, 20, 0, 0, 1] in table


def test_the_cap_on_ankles_and_heels_holds_on_all_four(pose_kit: SimpleNamespace) -> None:
    mae = np.full((3, len(JOINTS)), 12.0)
    mae[1, JOINTS.index("lHeel")] = 30.0
    mae[2, JOINTS.index("rHeel")] = np.nan
    assert np.array_equal(probe.cap_mae(mae, "ankles"), mae, equal_nan=True)
    capped = probe.cap_mae(mae, "ankles_heels")
    left, right = JOINTS.index("lAnkle"), JOINTS.index("rAnkle")
    assert capped[1, left] == 30.0 and capped[1, right] == 12.0
    assert np.isnan(capped[2, right]) and capped[2, left] == 12.0
    assert mae[1, left] == 12.0  # the caller's array untouched


def test_bands_kinematics_and_features_of_a_steady_runner(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    bodies = [
        pose_kit.runner(1, start=0, n=50, speed_m_s=6.0),
        pose_kit.runner(2, start=0, n=50, speed_m_s=4.0),
        pose_kit.runner(3, start=0, n=50, speed_m_s=2.0),
    ]
    root = pose_kit.write_bronze(tmp_path / "data", pose_kit.calibration, bodies)
    rows = load_players(root, pose_kit.calibration)
    found = probe.admitted(rows)
    counts = found["counts"]
    assert counts[(1, 1, "ankles", 50, 15, "high")] == 1
    assert counts[(2, 1, "ankles", 50, 15, "low")] == 1
    assert counts[(3, 1, "ankles", 50, 15, "below")] == 1
    assert ("1", 50, 15, "below") not in found["features"]  # (a') and (f): low and high only
    (kin,) = [r for r in probe.kinematics_rows(found["features"]) if r[:4] == ["1", 50, 15, "high"]]
    columns = dict(zip(probe.KIN_COLUMNS, kin, strict=True))
    assert columns["head_p50_m_s"] == pytest.approx(6.0) and columns["plateau"] == 1
    assert columns["path_chord_max"] == pytest.approx(1.0)
    (sd,) = [r for r in probe.sd_rows(found["features"]) if r[:4] == ["1", 50, 15, "high"]]
    columns = dict(zip(probe.SD_COLUMNS, sd, strict=True))
    # s swings 1.2 sin(.) along the travel: its sd over whole cycles is 1.2 / sqrt(2)
    assert columns["s_sd_p50_m"] == pytest.approx(1.2 / np.sqrt(2), rel=0.05)
    assert columns["ankle_mae_p50_cm"] == pytest.approx(12.0)
    z = {r[0]: r for r in probe.z_rows(rows)}
    assert z[1][3] == pytest.approx(0.7 - 0.16) and z[1][4] == 1.0  # nose above midHip
    assert z[1][6] == 0.0  # the ankles below it in every frame
    accel = probe.classify(np.array([5.0, 6.0, 6.0]), np.array([6.0, 6.2, 5.0]), np.full(3, 6.0))
    assert accel.tolist() == ["accelerating", "plateau", "braking"]


def _cell(width: int, cap: int, kills: bool) -> dict[str, Any]:
    return {"width": width, "cap_cm": cap, "kills_the_noise": kills}


def test_a_cell_kills_the_noise_only_when_every_rho_does() -> None:
    rows = [[0.0, 1.0, 200, 0, 0, 0], [0.5, 0.95, 0, 0, 190, 0], [0.9, 0.94, 0, 0, 188, 0]]
    assert probe.kills_the_noise(rows[:2]) is True  # 0.95 is enough
    assert probe.kills_the_noise(rows) is False  # the last rho spares it
    assert probe.kills_the_noise(rows, 0.9) is True


def test_the_rule_takes_the_least_w_then_the_greatest_cap_and_none_is_death() -> None:
    cells = [_cell(37, 15, True), _cell(37, 20, True), _cell(50, 25, True), _cell(25, 25, False)]
    assert probe.choose(cells) == {"width": 37, "cap_cm": 20}
    assert probe.choose([_cell(37, 20, False), _cell(50, 15, True)]) == {"width": 50, "cap_cm": 15}
    assert probe.choose([_cell(37, 20, False), _cell(50, 25, False)]) is None


def test_the_rule_simulates_only_the_cells_of_the_bar_on_their_own_twins() -> None:
    """A tiny grid (400 windows per twin, rho 0 and 0.9, 20 copies, 40 repetitions): fifteen
    players with 60 high and 60 low windows; the failing cell is not simulated; a cell kills
    the noise when every rho does, and its row says which criterion killed."""
    raw = json.loads(CLIP.read_text(encoding="utf-8"))
    fps, mae = sweep.clip_mae(raw)
    table = [[pid, 1, "ankles", 37, 20, 0, 60, 60] for pid in range(15)]
    table += [[pid, 1, "ankles_heels", 37, 20, 0, 0, 0] for pid in range(15)]
    bar = [
        {"width": 25, "cap_cm": 20, "passes": False},
        {"width": 37, "cap_cm": 20, "passes": True},
    ]
    rule = probe.rule_w_cap(table, bar, mae, fps, grid=TINY, draws=20, reps=40)
    (cell,) = rule["cells"]
    assert (cell["width"], cell["cap_cm"], cell["players"]) == (37, 20, 15)
    assert cell["players_ge_min_high"] == cell["players_ge_min_both"] == 15
    rows = cell["noise"]["rows"]
    assert [r[0] for r in rows] == [0.0, 0.9]
    for r in rows:
        assert r[1] == sum(r[2:]) / 40  # p_dies is the deaths over the repetitions
    print(f"\ntiny rule: {rows}")
    assert cell["kills_the_noise"] == all(r[1] >= protocol.P_DIES_NOISE_MIN for r in rows)
    assert rule["chosen"] == ({"width": 37, "cap_cm": 20} if cell["kills_the_noise"] else None)
    again = probe.rule_w_cap(
        [[pid, 1, "ankles", 37, 20, 0, 60, 60] for pid in range(15)],
        bar,
        mae,
        fps,
        grid=TINY,
        draws=20,
        reps=40,
    )
    assert again["cells"][0]["noise"] == cell["noise"]  # seeded: the same figures again


def test_the_probe_writes_the_same_bytes_twice_and_check_sees_a_change(
    pose_repo: Any,
    pose_kit: SimpleNamespace,
    reports: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _commit_real_design(pose_repo, reports)
    monkeypatch.setattr(
        probe, "rule_w_cap", partial(probe.rule_w_cap, grid=TINY, draws=10, reps=20)
    )
    bodies = [
        pose_kit.runner(p, start=10, n=120, speed_m_s=v, period=per)
        for p, v, per in ((1, 6.0, 1), (2, 4.0, 1), (3, 6.5, 2))
    ]
    root = pose_kit.write_bronze(tmp_path / "data", pose_kit.calibration, bodies)
    assert probe.run_pose_probe(root, reports, CLIP) == 0
    path = reports / probe.CALIBRATION_NAME
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["match_id"] == 1925299 and payload["protocol"]["stage"] == "design"
    assert len(payload["head"]) == 40 and len(payload["code_tree_sha"]) == 40
    assert payload["inputs"]["rows"] == 360
    assert probe.run_pose_probe(root, reports, CLIP) == 0
    assert path.read_text(encoding="utf-8") == text  # two runs, the same bytes
    assert probe.run_pose_probe(root, reports, CLIP, check=True) == 0
    assert "FULL 1/1 recomputed and equal" in capsys.readouterr().out
    assert probe.run_pose_probe(tmp_path / "empty", reports, CLIP, check=True) == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out

    moved = json.loads(text)
    moved["windows"]["rows"][0][-1] += 1  # a count moved, resealed
    path.write_text(probe._render(seal(moved)), encoding="utf-8")
    assert probe.run_pose_probe(root, reports, CLIP, check=True) == 1
    assert "differs from what the code writes" in capsys.readouterr().out
    unsealed = json.loads(text)
    unsealed["windows"]["rows"][0][-1] += 1
    path.write_text(probe._render(unsealed), encoding="utf-8")
    assert probe.run_pose_probe(tmp_path / "empty", reports, CLIP, check=True) == 1
    assert "content_sha256" in capsys.readouterr().out
    lying = json.loads(text)
    for cell in lying["rule_w_cap"]["cells"]:
        cell["kills_the_noise"] = not cell["kills_the_noise"]
    path.write_text(probe._render(seal(lying)), encoding="utf-8")
    assert probe.run_pose_probe(tmp_path / "empty", reports, CLIP, check=True) == 1
    assert "does not follow its figures" in capsys.readouterr().out

    (pose_repo.root / "pipeline" / "src" / "tracklab" / "pose" / "new.py").write_text("x = 1\n")
    path.write_text(text, encoding="utf-8")
    assert probe.run_pose_probe(root, reports, CLIP) == 1  # uncommitted code: nothing written
    assert "commit them first" in capsys.readouterr().out


def test_the_counts_the_rule_reads_are_the_ankles_cap_summed_over_periods() -> None:
    table = [
        [9, 1, "ankles", 37, 20, 5, 3, 4],
        [9, 2, "ankles", 37, 20, 5, 2, 6],
        [9, 1, "ankles_heels", 37, 20, 0, 100, 100],
        [9, 1, "ankles", 50, 20, 0, 100, 100],
        [4, 1, "ankles", 37, 20, 0, 0, 0],
    ]
    assert probe.counts_for_rule(table, 37, 20) == ([0, 10], [0, 5])
    assert criteria.MIN_WINDOWS == 5


def test_the_versioned_calibration_answers_to_the_committed_protocol_and_follows_its_rule(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`reports/pose_calibration.json` as the first time wrote it: sealed, the calibration
    match, the protocol and the sweep committed in HEAD, a rule that follows its own figures,
    no cadence in it, and `--check` PARTIAL on the fixtures (a slice of 1925299)."""
    text = (REPORTS / probe.CALIBRATION_NAME).read_text(encoding="utf-8")
    payload = json.loads(text)
    assert probe.consistency_problems(payload, 1925299) == []
    assert payload["time"] == probe.TIME  # "first: no cadence computed", the one mention
    assert text.count("cadence") == 1 and "cad_" not in text
    assert payload["inputs"]["players_with_pose"] == 32
    fixtures = PIPELINE / "tests" / "fixtures" / "data"
    assert probe.run_pose_probe(fixtures, REPORTS, CLIP, check=True) == 0
    assert "PARTIAL 0/1" in capsys.readouterr().out
