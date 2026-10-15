"""The metric of task 61 (`tracklab.pose.metric`), written before task 60's freeze (phase B2)
and tested on runners written by hand in a throwaway repository: no real pose is read.

The repository is frozen at W 50, cap 20; the second time runs on the hand-made 1925299 and its
verdict is committed, which opens the guard; then the metric reads both matches.

Mutations, each applied, seen failing and restored (tasks/todo.md, tasks 60 and 61): the rows
ordered by cadence instead of team and number; 1925299 not compared with the committed
verdict; M4 judged with the half IQR of 1996435's own squad.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracklab.pose import data, metric, sweep, verdict
from tracklab.pose.coverage import coverage_match
from tracklab.pose.data import load_players
from tracklab.runs.protocol import fingerprint, seal

REPORTS = Path(__file__).resolve().parents[2] / "reports"
W, CAP = 50, 20


def squad(kit: SimpleNamespace, first: int, players: int, base: float) -> list[Any]:
    """Per player a high stretch (6 m/s, five windows of 50) at his cadence + 0.3 Hz and a low
    one (4 m/s) at his cadence; cadences `base` + 0.08 Hz per player."""
    bodies = []
    for p in range(players):
        cadence = base + 0.08 * p
        pid = first + p
        bodies.append(kit.runner(pid, start=0, n=250, speed_m_s=6.0, cadence_hz=cadence + 0.3))
        bodies.append(kit.runner(pid, start=1000, n=250, speed_m_s=4.0, cadence_hz=cadence))
    return bodies


@pytest.fixture
def opened(pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path) -> SimpleNamespace:
    """Frozen, the second time committed, both matches written: what the metric needs."""
    reports = pose_repo.root / "pipeline" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPORTS / sweep.SWEEP_NAME, reports / sweep.SWEEP_NAME)
    pose_repo.commit(pose_repo.frozen(W, CAP), "frozen")
    root = tmp_path / "data"
    pose_kit.write_bronze(root, pose_kit.calibration, squad(pose_kit, 100, 10, 2.6))
    pose_kit.write_bronze(root, pose_kit.confirmation, squad(pose_kit, 200, 10, 2.7))
    # the lineup's order is not the ids': team 2 first, numbers backwards
    for match, first in ((pose_kit.calibration, 100), (pose_kit.confirmation, 200)):
        lineup = [(first + p, 2 if p % 2 else 1, 30 - p) for p in range(10)]
        pose_kit.write_lineup(root, match, lineup)
    assert verdict.run_pose_verdict(root, reports) == 0
    pose_repo.commit(None, "verdict")
    return SimpleNamespace(repo=pose_repo, reports=reports, root=root)


def test_the_metric_reads_both_matches_once_open_and_writes_the_same_bytes(
    opened: SimpleNamespace, pose_kit: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert metric.run_pose_metric(opened.root, opened.reports) == 0
    path = opened.reports / metric.METRIC_NAME
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    v = payload["verdicts"]
    assert v["calibration"]["dies_at"] is None
    assert v["confirmation"]["status"] == "replicated" and v["p6"] == "alive"
    assert (
        v["thresholds"]["m4_half_iqr_hz"]
        == json.loads((opened.reports / verdict.VERDICT_NAME).read_text(encoding="utf-8"))["m4"][
            "half_iqr_hz"
        ]
    )
    assert payload["protocol"]["fingerprint"] == data.committed_protocol()["fingerprint"]
    assert len(payload["head"]) == 40 and payload["code_tree_sha"] == data.code_tree_sha()
    # untracked, the file dirties the tree and the guard closes: committed first, as in the plan
    assert metric.run_pose_metric(opened.root, opened.reports) == 1
    assert "dirty" in capsys.readouterr().out
    path.write_text(text, encoding="utf-8")
    opened.repo.commit(None, "metric")
    # the second run is the check: everything recomputed with the recorded head, same bytes
    assert metric.run_pose_metric(opened.root, opened.reports, check=True) == 0
    assert "FULL 2/2 recomputed and equal" in capsys.readouterr().out
    assert metric.run_pose_metric(opened.root.parent / "empty", opened.reports, check=True) == 0
    assert "PARTIAL 0/2" in capsys.readouterr().out

    # rows by team, then number, then player; every player's windows within his coverage
    columns = payload["columns"]
    for match, rows in payload["matches"].items():
        keys = [(r[0], r[1]) for r in rows]
        assert keys == sorted(keys), match
        assert [r[0] for r in rows[:3]] == [1, 1, 1]
        coverage = {p["player_id"]: p for p in coverage_match(opened.root, int(match))["players"]}
        for r in rows:
            row = dict(zip(columns, r, strict=True))
            if row["period"] != "all":
                continue
            player = coverage[row["player_id"]]
            assert row["windows"] <= player["with_pose"] // W
            assert player["runs_ge_50"] >= 1

    # the cap touched after the freeze: the committed fingerprint moves, the check fails
    moved = opened.repo.frozen(W, CAP)
    moved["design"]["windows"] = {"caps_cm": [15]}
    opened.repo.commit(seal({**moved, "fingerprint": fingerprint(moved["design"])}), "moved")
    assert metric.run_pose_metric(opened.root, opened.reports, check=True) == 1
    assert "fingerprint" in capsys.readouterr().out


def test_1925299_must_say_what_the_committed_verdict_says(
    opened: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """The verdict committed with one more positive player than the frozen code finds:
    nothing is written."""
    path = opened.reports / verdict.VERDICT_NAME
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["verdict"]["M2"]["positive"] -= 1
    path.write_text(verdict._render(seal(changed)), encoding="utf-8")
    opened.repo.commit(None, "a verdict that is not the code's")
    assert metric.run_pose_metric(opened.root, opened.reports) == 1
    assert "1925299 recomputed differs from pose_verdict.json" in capsys.readouterr().out
    assert not (opened.reports / metric.METRIC_NAME).exists()


def test_m4_is_unreplicated_without_coverage_and_judged_with_1925299s_half_iqr(
    opened: SimpleNamespace, pose_kit: SimpleNamespace
) -> None:
    rows = {m: load_players(opened.root, m) for m in (pose_kit.calibration, pose_kit.confirmation)}
    windows = {m: verdict.window_estimates(r, W, CAP, draws=20) for m, r in rows.items()}
    cal, conf = windows[pose_kit.calibration], windows[pose_kit.confirmation]
    few = [w for w in conf if w.player_id < 203]  # three players: under the minima
    assert metric.match_verdicts(cal, few, 0.1)["confirmation"]["status"] == "unreplicated"
    assert metric.match_verdicts(cal, few, 0.1)["p6"] == "unreplicated"
    # a frozen half IQR far under any propagated sd: the precision clause fails in 1996435
    tight = metric.match_verdicts(cal, conf, 1e-4)["confirmation"]
    assert tight["status"] == "replication_failed" and tight["m4"]["dies_at"] == "m2_precision"
    assert tight["m4"]["half_iqr_hz"] == 1e-4
