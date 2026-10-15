"""The P6 protocol as code (`tracklab.pose.protocol`, task 60, phase B2), on the versioned sweep
and coverage and on a bronze written by hand: no real pose is read.

The plan's mutation is a test here: a threshold of the JSON moved by hand, and resealed so the
seal is not what catches it, fails `--check`. Mutations of the code, each applied, seen failing
and restored (tasks/todo.md, task 60, phase B2): the denominators taken from the file instead
of the bronze; the sweep's sha not read from its bytes; the high band from above 5.5 m/s; the
frozen check without comparing the chosen cell or the calibration's seal.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracklab.pose import criteria, gait, sweep
from tracklab.pose.coverage import COVERAGE_NAME
from tracklab.pose.protocol import (
    BAND_HIGH_M_S,
    BAND_LOW_M_S,
    CALIBRATION_NAME,
    PROTOCOL_NAME,
    SANE_DELTA_HZ,
    SANE_P_DIES_MAX,
    SANE_SIGMA_B_HZ,
    band,
    file_sha256,
    freeze_payload,
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


def _calibration(chosen: dict[str, int] | None) -> dict[str, Any]:
    """A sealed first time of the probe whose rule chose `chosen`: what the freeze reads."""
    return seal({"match_id": 1925299, "rule_w_cap": {"chosen": chosen}})


def test_the_freeze_keeps_the_design_and_check_reads_the_frozen_file(
    reports: Path, whole: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`freeze_payload` (what `pose freeze` writes) turns the design to frozen at the chosen
    cell; `--check` passes on it with the calibration beside, and fails when the frozen
    (W, cap) is moved, the calibration beside it is another, the design is edited, the
    history loses its frozen entry or the file is not resealed. Write mode never rewrites it."""
    assert run_pose_protocol(whole, reports) == 0
    path = reports / PROTOCOL_NAME
    design = json.loads(path.read_text(encoding="utf-8"))
    calibration = _calibration({"width": 50, "cap_cm": 25})
    (reports / CALIBRATION_NAME).write_text(json.dumps(calibration), encoding="utf-8")
    frozen = freeze_payload(design, calibration, code_tree="a" * 40, date="2026-10-16")
    assert frozen["design"] == design["design"] and frozen["fingerprint"] == design["fingerprint"]
    assert (frozen["frozen"]["width"], frozen["frozen"]["cap_cm"]) == (50, 25)
    assert frozen["history"][-1]["stage"] == "frozen" and sealed(frozen)
    path.write_text(render(frozen), encoding="utf-8")
    assert run_pose_protocol(whole, reports, check=True) == 0
    assert "stage frozen" in _status(capsys)
    assert run_pose_protocol(whole, reports) == 1  # never rewritten
    assert json.loads(path.read_text(encoding="utf-8")) == frozen

    def fails(payload: dict[str, Any], message: str) -> None:
        path.write_text(render(payload), encoding="utf-8")
        assert run_pose_protocol(whole, reports, check=True) == 1
        assert message in _status(capsys)
        path.write_text(render(frozen), encoding="utf-8")

    moved = json.loads(json.dumps(frozen))
    moved["frozen"]["cap_cm"] = 20  # the plan's mutation of task 61: the cap touched after
    fails(seal(moved), "not the cell the calibration's rule chose")
    edited = json.loads(json.dumps(frozen))
    edited["design"]["windows"]["caps_cm"] = [15, 20]
    fails(seal({**edited, "fingerprint": fingerprint(edited["design"])}), "design differs")
    fails(seal({**frozen, "history": frozen["history"][:-1]}), "history has no frozen entry")
    fails({**frozen, "stage": "frozen ", "content_sha256": frozen["content_sha256"]}, "unknown")
    unsealed = json.loads(json.dumps(frozen))
    unsealed["frozen"]["date"] = "2026-10-17"
    fails(unsealed, "content_sha256 does not cover the file")
    other = _calibration({"width": 50, "cap_cm": 25}) | {"note": "another file"}
    (reports / CALIBRATION_NAME).write_text(json.dumps(seal(other)), encoding="utf-8")
    fails(frozen, "calibration_from is not the pose_calibration.json beside it")


def test_the_freeze_refuses_what_it_cannot_freeze(reports: Path, whole: Path) -> None:
    assert run_pose_protocol(whole, reports) == 0
    design = json.loads((reports / PROTOCOL_NAME).read_text(encoding="utf-8"))
    chosen = _calibration({"width": 50, "cap_cm": 25})
    with pytest.raises(ValueError, match="chose no"):
        freeze_payload(design, _calibration(None), code_tree="a" * 40, date="2026-10-16")
    with pytest.raises(ValueError, match="tree sha"):
        freeze_payload(design, chosen, code_tree="abc", date="2026-10-16")
    frozen = freeze_payload(design, chosen, code_tree="a" * 40, date="2026-10-16")
    with pytest.raises(ValueError, match="only a protocol in stage"):
        freeze_payload(frozen, chosen, code_tree="a" * 40, date="2026-10-16")


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
    rule = design["rule_w_cap"]
    assert (rule["sane_delta_hz"], rule["sane_sigma_b_hz"]) == (SANE_DELTA_HZ, SANE_SIGMA_B_HZ)
    assert (SANE_DELTA_HZ, SANE_SIGMA_B_HZ, SANE_P_DIES_MAX) == (0.05, 0.1, 0.05)
    assert "the cadence does not rise 0.05 Hz" in design["death_criteria"]["M2"]
    assert "pose_verdict.json" in design["death_criteria"]["M4"]
    assert "is_detected" in design["windows"]


def test_the_bands_are_half_open() -> None:
    assert [band(v) for v in (2.999, 3.0, 5.499, 5.5, 9.0)] == [
        "below",
        "low",
        "low",
        "high",
        "high",
    ]


def test_the_versioned_protocol_is_sealed_in_design_and_names_the_versioned_files(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`reports/pose_protocol.json` as committed before the probe: in design (the freeze, in
    the second part of phase B2, changes this test on purpose), its sweep and coverage the
    versioned ones, the denominators 32 and 30, and `--check` PARTIAL on the fixtures."""
    payload = json.loads((REPORTS / PROTOCOL_NAME).read_text(encoding="utf-8"))
    assert payload["stage"] == "design" and sealed(payload)
    assert payload["fingerprint"] == fingerprint(payload["design"])
    assert payload["design"]["sweep"]["sha256"] == file_sha256(REPORTS / sweep.SWEEP_NAME)
    seen = payload["design"]["seen_of_confirmation"]["coverage"]
    assert seen["sha256"] == file_sha256(REPORTS / COVERAGE_NAME)
    assert payload["evidence"]["denominators"]["per_match"] == {
        "1925299": {"players_listed": 32, "players_with_pose": 32},
        "1996435": {"players_listed": 30, "players_with_pose": 30},
    }
    assert run_pose_protocol(FIXTURES, REPORTS, check=True) == 0
    assert "PARTIAL 0/2" in _status(capsys)
