"""The metric of task 61 (`tracklab.pose.metric`), written before task 60's freeze (phase B2)
and tested on runners written by hand in a throwaway repository: no real pose is read.

The repository is frozen at W 50, cap 20; the second time runs on the hand-made 1925299 and its
verdict is committed, which opens the guard; then the metric reads both matches.

Mutations, each applied, seen failing and restored (tasks/todo.md, tasks 60 and 61): the rows
ordered by cadence instead of team and number; 1925299 not compared with the committed
verdict; M4 judged with the half IQR of 1996435's own squad; and after the second review:
the sd of the cadence over every window instead of the finite ones; the step's sd from the
separation's draws; 1996435 loaded before 1925299 is compared; the PARTIAL check without the
protocol's seal, the code tree or the verdict's seal.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tracklab.pose import criteria, data, gait, metric, sweep, verdict
from tracklab.pose.coverage import coverage_match
from tracklab.pose.data import load_players
from tracklab.pose.verdict import Window
from tracklab.runs.protocol import seal

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
    pose_repo.calibration(rows=5000)  # 10 players x 500 rows of 1925299
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
    for key, value, message in (
        ("code_tree_sha", "0" * 40, "code_tree_sha is not the tree the freeze recorded"),
        ("verdict_from", {"content_sha256": "0" * 64}, "verdict_from is not the pose_verdict"),
    ):
        forged = {k: v for k, v in json.loads(text).items() if k != "content_sha256"}
        path.write_text(sweep.render(seal({**forged, key: value})) + "\n", encoding="utf-8")
        assert metric.run_pose_metric(opened.root.parent / "empty", opened.reports, check=True) == 1
        assert message in capsys.readouterr().out
    path.write_text(text, encoding="utf-8")

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

    # the plan's mutation of task 61: the frozen cap moved after the freeze and resealed;
    # the fingerprint stays, the protocol's seal does not, and the PARTIAL check sees it
    protocol_path = opened.repo.root / data.PROTOCOL_IN_REPO
    moved = json.loads(protocol_path.read_text(encoding="utf-8"))
    moved["frozen"]["cap_cm"] = 25
    opened.repo.commit(seal({k: v for k, v in moved.items() if k != "content_sha256"}), "moved")
    assert data.committed_protocol()["fingerprint"] == payload["protocol"]["fingerprint"]
    empty = opened.root.parent / "empty"
    assert metric.run_pose_metric(empty, opened.reports, check=True) == 1
    assert "protocol is not the one committed in HEAD" in capsys.readouterr().out


def test_1925299_must_say_what_the_committed_verdict_says_before_1996435_is_read(
    opened: SimpleNamespace, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verdict committed with one positive player fewer than the frozen code finds:
    nothing is written, and 1996435 is never loaded."""
    loads: list[int] = []
    real = metric.load_players
    monkeypatch.setattr(metric, "load_players", lambda d, m: (loads.append(m), real(d, m))[1])
    path = opened.reports / verdict.VERDICT_NAME
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["verdict"]["M2"]["positive"] -= 1
    path.write_text(verdict._render(seal(changed)), encoding="utf-8")
    opened.repo.commit(None, "a verdict that is not the code's")
    assert metric.run_pose_metric(opened.root, opened.reports) == 1
    assert "1925299 recomputed differs from pose_verdict.json" in capsys.readouterr().out
    assert not (opened.reports / metric.METRIC_NAME).exists()
    assert loads == [1925299]


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


def _window(pid: int, frame: int, cadence: float, draws: np.ndarray[Any, Any]) -> Window:
    estimate = gait.Gait(cadence, cadence, 1.0 + 0.01 * frame, 1.6 + 0.01 * frame, 6.0)
    return Window(pid, 1, frame, "high", 6.0, 0.0, estimate, 0.0, draws)


def test_each_published_median_has_its_sd_over_the_draws_of_the_same_windows() -> None:
    """Seven high windows of one player, the third NaN in cad_s but with finite draws: the sd
    of the cadence is over the six finite ones, the first five of them give M2's; the step's
    and the separation's are over columns 2 and 1 of the draws; the ratio's, draw by draw."""
    rng = np.random.default_rng(0)
    windows = []
    for k in range(7):
        draws = np.c_[
            3.0 + 0.05 * rng.standard_normal(40),
            1.0 + 0.02 * rng.standard_normal(40),
            1.6 + 0.03 * rng.standard_normal(40),
            3.0 + 0.05 * rng.standard_normal(40),
        ]
        windows.append(_window(1, 50 * k, np.nan if k == 2 else 3.0, draws))
    (row,) = [r for r in metric.player_rows(windows, []) if r[3] == "all"]
    got = dict(zip(metric.COLUMNS, row, strict=True))
    all_draws = np.array([w.draws for w in windows])
    finite = [0, 1, 3, 4, 5, 6]
    assert got["finite_s"] == 6
    assert got["cad_s_sd_hz"] == round(criteria.propagated_sd(all_draws[finite, :, 0]), 6)
    assert got["cad_s_sd_hz"] != round(criteria.propagated_sd(all_draws[:, :, 0]), 6)
    assert got["cad_s_sd_5_hz"] == round(criteria.propagated_sd(all_draws[finite[:5], :, 0]), 6)
    assert got["step_length_sd_m"] == round(criteria.propagated_sd(all_draws[:, :, 2]), 6)
    assert got["ankle_separation_sd_m"] == round(criteria.propagated_sd(all_draws[:, :, 1]), 6)
    assert got["step_length_sd_m"] != got["ankle_separation_sd_m"]
    assert got["separation_over_step_sd"] == round(
        metric.ratio_sd(all_draws[:, :, 1], all_draws[:, :, 2]), 6
    )


def test_the_versioned_metric_crosses_the_coverage_and_follows_the_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`reports/pose_metric.json` as task 61 committed it, against `pose_coverage.json`: every
    player is one the coverage lists, his windows of W frames (both bands) fit in his frames
    with a pose and need a stretch of at least W; rows by team and number; 1925299 says what
    the sealed verdict says; and `--check` PARTIAL on the fixtures."""
    payload = json.loads((REPORTS / metric.METRIC_NAME).read_text(encoding="utf-8"))
    coverage = json.loads((REPORTS / "pose_coverage.json").read_text(encoding="utf-8"))
    sealed_verdict = json.loads((REPORTS / verdict.VERDICT_NAME).read_text(encoding="utf-8"))
    width = payload["width"]
    assert width == W
    columns = payload["columns"]
    for match, rows in payload["matches"].items():
        players = {p["player_id"]: p for p in coverage["matches"][match]["players"]}
        table = [dict(zip(columns, r, strict=True)) for r in rows]
        assert [(r["team_id"], r["number"]) for r in table] == sorted(
            (r["team_id"], r["number"]) for r in table
        )
        windows: dict[int, int] = {}
        for r in table:
            if r["period"] == "all":
                windows[r["player_id"]] = windows.get(r["player_id"], 0) + r["windows"]
        for pid, n in windows.items():
            assert n <= players[pid]["with_pose"] // width, (match, pid)
            assert players[pid][f"runs_ge_{width}"] >= 1, (match, pid)
    assert metric.recompute_problems(payload["verdicts"]["calibration"], sealed_verdict) == []
    fixtures = REPORTS.parent / "tests" / "fixtures" / "data"
    assert metric.run_pose_metric(fixtures, REPORTS, check=True) == 0
    assert "PARTIAL 0/2" in capsys.readouterr().out
