"""`tracklab runs protocol` and the held-out guard (task 47).

The split regenerates from the 20 rows the committed protocol carries, so it runs on the CI
fixtures (one match) as on the real warehouse; where the warehouse at hand holds every
match, `--check` also regenerates the rows and the placebo counts from it. The guard is
exercised on throwaway git repositories, one per stage, and on this repository's own HEAD.

Mutations recorded in tasks/todo.md: the guard removed from `load_half` fails the three
closed-half tests; the alternation parity flipped in `split_matches` fails the regeneration
and the fabricated-rows tests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tracklab.cli import _cmd_runs_protocol, build_parser
from tracklab.paths import data_root
from tracklab.runs.data import HeldOutLocked, head_stage, load_half
from tracklab.runs.placebo import placebo_counts
from tracklab.runs.protocol import (
    STAGE_DESIGN,
    MatchRow,
    fingerprint,
    partition_flags,
    read_protocol,
    rows_from_protocol,
    run_runs_protocol,
    split_matches,
    warehouse_kickoffs,
)

PIPELINE = Path(__file__).resolve().parents[2]
REPORTS = PIPELINE / "reports"
PROTOCOL = REPORTS / "runs_protocol.json"
CI_FIXTURE_MATCH = 1874553


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --- the split -------------------------------------------------------------------------


def test_split_regenerates_from_the_committed_rows() -> None:
    payload = read_protocol(PROTOCOL)
    rows = rows_from_protocol(payload)
    assert len(rows) == 20
    calibration, held_out = split_matches(rows)
    split = payload["design"]["split"]
    assert (calibration, held_out) == (split["calibration"], split["held_out"])
    assert len(calibration) == 10
    assert len(held_out) == 10
    assert not set(calibration) & set(held_out)
    by_id = {r.match_id: r for r in rows}
    for half in (calibration, held_out):
        assert sum(by_id[m].event_coords_exact for m in half) == 5
    assert CI_FIXTURE_MATCH in calibration


def test_the_earliest_match_of_each_group_opens_calibration() -> None:
    rows = rows_from_protocol(read_protocol(PROTOCOL))
    calibration, _ = split_matches(rows)
    for exact in (True, False):
        group = [r for r in rows if r.event_coords_exact is exact]
        first = min(group, key=lambda r: (r.kickoff_utc, r.match_id))
        assert first.match_id in calibration


def test_split_alternates_by_kickoff_inside_each_group_and_breaks_ties_by_id() -> None:
    rows = [
        MatchRow(5, "2025-01-01T00:00:00Z", True, False),
        MatchRow(1, "2025-01-02T00:00:00Z", True, False),
        MatchRow(3, "2025-01-03T00:00:00Z", True, True),
        MatchRow(9, "2024-12-01T00:00:00Z", False, False),
        MatchRow(8, "2024-12-01T00:00:00Z", False, False),
    ]
    assert split_matches(rows) == ([3, 5, 8], [1, 9])


def test_the_committed_rows_carry_the_flags_of_quality_partitions() -> None:
    flags = partition_flags(REPORTS)
    rows = rows_from_protocol(read_protocol(PROTOCOL))
    assert {r.match_id for r in rows} == set(flags)
    for row in rows:
        assert row.event_coords_exact == flags[row.match_id]["event_coords_exact"]
        assert row.layout_extra_footage == flags[row.match_id]["layout_extra_footage"]


# --- the committed file against the code ------------------------------------------------


def test_the_committed_protocol_is_what_the_code_writes() -> None:
    assert run_runs_protocol(data_root(), REPORTS, check=True) == 0


def test_the_protocol_is_in_design_with_the_plans_bar() -> None:
    """Decision 4 and the null, as Javier confirmed them; a change here is a change of the
    preregistration and must show as a diff of this test, never only of the JSON."""
    payload = read_protocol(PROTOCOL)
    assert payload["stage"] == STAGE_DESIGN
    bar = payload["design"]["bar"]
    assert bar["calibration"] == {
        "same_sign_matches_at_least": 8,
        "of_matches": 10,
        "p_at_most": 0.00135,
        "z_equivalent": 3.0,
    }
    assert bar["testability"]["mde80_sd_at_most"] == 0.3
    assert bar["held_out"]["same_sign_matches_at_least"] == 8
    assert bar["held_out"]["p_at_most"] == 0.01
    assert payload["design"]["null"]["n_permutations"] == 2000
    assert set(payload["design"]["death_criteria"]) >= {"M1", "M2", "M3", "M4", "M5a", "M5b"}
    assert payload["design"]["placebo"]["teammates_runs"]["excluded"] is True


def test_fingerprint_follows_the_design_and_nothing_else() -> None:
    payload = read_protocol(PROTOCOL)
    assert payload["fingerprint"] == fingerprint(payload["design"])
    moved = json.loads(json.dumps(payload["design"]))
    moved["bar"]["calibration"]["p_at_most"] = 0.05
    assert fingerprint(moved) != payload["fingerprint"]
    without = {k: v for k, v in payload.items() if k != "content_sha256"}
    assert payload["content_sha256"] == fingerprint(without)


def test_protocol_names_no_local_machine(assert_no_local_traces: Callable[[object], None]) -> None:
    assert_no_local_traces(read_protocol(PROTOCOL))


@pytest.fixture
def reports_copy(tmp_path: Path) -> Path:
    reports = tmp_path / "reports"
    reports.mkdir()
    shutil.copy(REPORTS / "quality_partitions.csv", reports)
    shutil.copy(PROTOCOL, reports)
    return reports


def test_check_passes_on_an_untouched_copy(reports_copy: Path) -> None:
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 0


def _move_a_threshold(p: dict[str, Any]) -> None:
    p["design"]["bar"]["calibration"]["p_at_most"] = 0.05


def _swap_a_match(p: dict[str, Any]) -> None:
    split = p["design"]["split"]
    split["held_out"].append(split["calibration"].pop(0))


def _flip_a_flag(p: dict[str, Any]) -> None:
    row = p["design"]["split"]["matches"][0]
    row["event_coords_exact"] = not row["event_coords_exact"]


def _change_the_seed(p: dict[str, Any]) -> None:
    p["design"]["null"]["seed"] += 1


def _edit_a_count(p: dict[str, Any]) -> None:
    p["evidence"]["placebo_counts_calibration"]["per_match"][0]["team_overlap"] += 1


def _freeze_by_hand(p: dict[str, Any]) -> None:
    p["stage"] = "frozen"


@pytest.mark.parametrize(
    "edit",
    [
        _move_a_threshold,
        _swap_a_match,
        _flip_a_flag,
        _change_the_seed,
        _edit_a_count,
        _freeze_by_hand,
    ],
)
def test_check_fails_when_the_protocol_is_edited_by_hand(
    reports_copy: Path, edit: Callable[[dict[str, Any]], None]
) -> None:
    path = reports_copy / PROTOCOL.name
    payload = read_protocol(path)
    edit(payload)
    _write(path, payload)
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 1


def test_check_fails_when_the_protocol_is_missing(reports_copy: Path) -> None:
    (reports_copy / PROTOCOL.name).unlink()
    assert run_runs_protocol(data_root(), reports_copy, check=True) == 1


def test_write_mode_reproduces_the_committed_bytes_or_refuses_a_partial_warehouse(
    reports_copy: Path,
) -> None:
    (reports_copy / PROTOCOL.name).unlink()
    code = run_runs_protocol(data_root(), reports_copy, check=False)
    if set(partition_flags(REPORTS)) <= set(warehouse_kickoffs(data_root())):
        assert code == 0
        assert (reports_copy / PROTOCOL.name).read_bytes() == PROTOCOL.read_bytes()
    else:
        assert code == 1
        assert not (reports_copy / PROTOCOL.name).exists()


def test_cli_wires_runs_protocol() -> None:
    args = build_parser().parse_args(["runs", "protocol", "--check"])
    assert args.func is _cmd_runs_protocol
    assert args.check is True
    assert args.data_dir == data_root()


# --- placebo counts: coverage only ------------------------------------------------------


def test_placebo_counts_nest_from_runs_down_to_the_strictest_rule() -> None:
    """On the data root at hand (the fixture match in CI): the rules are nested, so the counts
    must be too, and every run finds its possession."""
    rows = placebo_counts(data_root(), [CI_FIXTURE_MATCH])
    assert [r.match_id for r in rows] == [CI_FIXTURE_MATCH]
    r = rows[0]
    assert r.runs > 0
    assert r.runs_without_possession == 0
    assert r.runs >= r.with_candidate >= r.runner_overlap >= r.team_overlap >= 0
    assert r.with_candidate >= r.runner_start >= r.team_start >= 0
    assert r.runner_start >= r.runner_overlap
    assert r.team_start >= r.team_overlap


def test_placebo_counts_of_an_absent_match_are_no_row() -> None:
    assert placebo_counts(data_root(), [1]) == []


# --- the guard on the held-out half -----------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "ci@example.invalid")
    _git(tmp_path, "config", "user.name", "ci")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def _commit_protocol(repo: Path, stage: str) -> Path:
    path = repo / "pipeline" / "reports" / PROTOCOL.name
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = read_protocol(PROTOCOL)
    payload["stage"] = stage
    _write(path, payload)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", f"protocol in stage {stage}")
    return path


def test_held_out_is_closed_while_the_committed_protocol_is_in_design(repo: Path) -> None:
    path = _commit_protocol(repo, STAGE_DESIGN)
    with pytest.raises(HeldOutLocked, match="'design'"):
        load_half("held_out", path)


def test_held_out_is_closed_in_a_dirty_tree_even_when_frozen(repo: Path) -> None:
    path = _commit_protocol(repo, "frozen")
    (repo / "pipeline" / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(HeldOutLocked, match="dirty"):
        load_half("held_out", path)


def test_held_out_is_closed_when_head_has_no_protocol(repo: Path) -> None:
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "no protocol yet")
    path = repo / "pipeline" / "reports" / PROTOCOL.name
    path.parent.mkdir(parents=True)
    _write(path, {"stage": "frozen", "design": {"split": {"held_out": [1]}}})
    with pytest.raises(HeldOutLocked, match="None"):
        load_half("held_out", path)


def test_held_out_opens_only_frozen_in_a_clean_tree(repo: Path) -> None:
    path = _commit_protocol(repo, "frozen")
    expected = read_protocol(PROTOCOL)["design"]["split"]["held_out"]
    assert load_half("held_out", path) == expected


def test_calibration_needs_no_guard() -> None:
    expected = read_protocol(PROTOCOL)["design"]["split"]["calibration"]
    assert load_half("calibration", PROTOCOL) == expected
    assert len(expected) == 10


def test_this_repositorys_head_keeps_the_held_out_closed() -> None:
    """Until task 50 commits the freeze, HEAD's protocol is in design (or absent, before the
    commit of task 47) and the real guard refuses; task 50 rewrites this test."""
    assert head_stage(PROTOCOL) != "frozen"
    with pytest.raises(HeldOutLocked):
        load_half("held_out", PROTOCOL)
