"""The P6 protocol as code (`tracklab.pose.protocol`, task 60, phase B2), on the versioned sweep
and coverage and on a bronze written by hand: no real pose is read.

The plan's mutation is a test here: a threshold of the JSON moved by hand, and resealed so the
seal is not what catches it, fails `--check`. Mutations of the code, each applied, seen failing
and restored (tasks/todo.md, task 60, phase B2): the denominators taken from the file instead
of the bronze; the sweep's sha not read from its bytes; the high band from above 5.5 m/s.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracklab.pose import criteria, gait, sweep
from tracklab.pose.coverage import COVERAGE_NAME
from tracklab.pose.protocol import (
    BAND_HIGH_M_S,
    BAND_LOW_M_S,
    PROTOCOL_NAME,
    band,
    file_sha256,
    render,
    run_pose_protocol,
)
from tracklab.runs.protocol import fingerprint, seal, sealed

PIPELINE = Path(__file__).resolve().parents[2]
REPORTS = PIPELINE / "reports"
FIXTURES = PIPELINE / "tests" / "fixtures" / "data"


@pytest.fixture
def reports(tmp_path: Path) -> Path:
    out = tmp_path / "reports"
    out.mkdir()
    for name in (sweep.SWEEP_NAME, COVERAGE_NAME):
        shutil.copy(REPORTS / name, out / name)
    return out


@pytest.fixture
def whole(pose_kit: SimpleNamespace, tmp_path: Path) -> Path:
    """Both matches whole: 2 and 3 players."""
    root = tmp_path / "data"
    pose_kit.write_bronze(
        root,
        pose_kit.calibration,
        [pose_kit.runner(p, start=10, n=30, speed_m_s=6.0) for p in (1, 2)],
    )
    pose_kit.write_bronze(
        root,
        pose_kit.confirmation,
        [pose_kit.runner(p, start=10, n=30, speed_m_s=6.0) for p in (1, 2, 3)],
    )
    return root


def _status(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


def test_full_on_whole_bronze_partial_elsewhere_and_the_same_bytes(
    reports: Path, whole: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_pose_protocol(whole, reports) == 0
    assert "FULL 2/2" in _status(capsys)
    text = (reports / PROTOCOL_NAME).read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["stage"] == "design" and sealed(payload)
    assert payload["fingerprint"] == fingerprint(payload["design"])
    assert payload["evidence"]["denominators"]["per_match"] == {
        "1925299": {"players_listed": 2, "players_with_pose": 2},
        "1996435": {"players_listed": 3, "players_with_pose": 3},
    }
    assert run_pose_protocol(whole, reports) == 0  # a second run, the same bytes
    assert (reports / PROTOCOL_NAME).read_text(encoding="utf-8") == text
    assert run_pose_protocol(whole, reports, check=True) == 0
    assert "FULL 2/2" in _status(capsys)
    assert run_pose_protocol(tmp_path / "empty", reports, check=True) == 0
    assert "PARTIAL 0/2" in _status(capsys)
    assert run_pose_protocol(FIXTURES, reports, check=True) == 0  # a slice of 1925299
    assert "PARTIAL 0/2" in _status(capsys)
    assert run_pose_protocol(tmp_path / "empty", reports) == 1  # nothing written from nothing
    assert (reports / PROTOCOL_NAME).read_text(encoding="utf-8") == text


def test_a_threshold_moved_by_hand_fails_check(
    reports: Path, whole: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The plan's mutation: a number of the design edited and the file resealed, so neither
    the seal nor the fingerprint is what catches it: the code writes another file."""
    assert run_pose_protocol(whole, reports) == 0
    path = reports / PROTOCOL_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    for edit in (("numbers", "min_players", 9), ("rule_w_cap", "p_dies_min", 0.9)):
        moved = json.loads(json.dumps(payload))
        moved["design"][edit[0]][edit[1]] = edit[2]
        moved["fingerprint"] = fingerprint(moved["design"])
        path.write_text(render(seal(moved)), encoding="utf-8")
        for root in (whole, tmp_path / "empty"):
            assert run_pose_protocol(root, reports, check=True) == 1, edit
            assert "differs from what the code writes" in _status(capsys)
    path.write_text(render(payload), encoding="utf-8")
    assert run_pose_protocol(whole, reports, check=True) == 0


def test_the_sweeps_bytes_and_the_bronze_counts_are_inside_what_check_compares(
    reports: Path, whole: Path, pose_kit: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_pose_protocol(whole, reports) == 0
    sweep_path = reports / sweep.SWEEP_NAME
    original = sweep_path.read_bytes()
    sweep_path.write_bytes(original + b"\n")
    assert run_pose_protocol(whole, reports, check=True) == 1
    sweep_path.write_bytes(original)
    pose_kit.write_bronze(  # a fourth player in 1996435: the recount differs from the file
        whole,
        pose_kit.confirmation,
        [pose_kit.runner(p, start=10, n=30, speed_m_s=6.0) for p in (1, 2, 3, 4)],
    )
    assert run_pose_protocol(whole, reports, check=True) == 1
    assert "players_listed={'1925299': 2, '1996435': 4}" in _status(capsys)


def test_a_file_that_is_not_in_design_is_neither_rewritten_nor_checked_here(
    reports: Path, whole: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_pose_protocol(whole, reports) == 0
    path = reports / PROTOCOL_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(render(seal({**payload, "stage": "frozen"})), encoding="utf-8")
    frozen = path.read_text(encoding="utf-8")
    assert run_pose_protocol(whole, reports) == 1
    assert path.read_text(encoding="utf-8") == frozen
    assert run_pose_protocol(whole, reports, check=True) == 1
    assert "written with the freeze" in _status(capsys)


def test_the_design_carries_the_numbers_of_the_code_that_applies_it(
    reports: Path, whole: Path
) -> None:
    assert run_pose_protocol(whole, reports) == 0
    design = json.loads((reports / PROTOCOL_NAME).read_text(encoding="utf-8"))["design"]
    assert design["split"] == {
        "calibration": [1925299],
        "confirmation": [1996435],
        "rule": "the plan's (task 60): 1925299 calibrates, 1996435 confirms",
        "matches": [1925299, 1996435],
        "source": "manifest/sources.json",
    }
    assert design["numbers"]["min_players"] == criteria.MIN_PLAYERS == 10
    assert design["numbers"]["min_windows"] == criteria.MIN_WINDOWS == 5
    assert design["numbers"]["sign_share"] == criteria.SIGN_SHARE == 0.75
    assert design["rule_w_cap"]["reps"] == criteria.REPS == 200
    assert design["rule_w_cap"]["draws"] == gait.DRAWS == 200
    assert design["sweep"]["bar"]["p95_rel_err_max"] == sweep.BAR_P95
    assert design["sweep"]["sha256"] == file_sha256(REPORTS / sweep.SWEEP_NAME)
    assert design["windows"]["cap_joints"] == ["lAnkle", "rAnkle"]
    assert design["bands"]["low_m_s"] == [BAND_LOW_M_S, BAND_HIGH_M_S] == [3.0, 5.5]


def test_the_bands_are_half_open() -> None:
    assert [band(v) for v in (2.999, 3.0, 5.499, 5.5, 9.0)] == [
        "below",
        "low",
        "low",
        "high",
        "high",
    ]
