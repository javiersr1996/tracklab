"""The guard on 1996435 (`tracklab.pose.data`, task 60, phase B2), on a throwaway repository and
a Body Pose bronze written by hand: no real pose is read.

The confirmation match opens only when the protocol committed in HEAD is frozen, with a frozen
entry after the design ones, the `pose/` tree of HEAD is the one the freeze recorded, and the
tree is clean. Behavioural, not lexical: every public name of every module of `tracklab.pose`
is classified, the ones that could return pose values are called with 1996435 while the
protocol is in design and must refuse, and what the counting ones return is walked for floats.
The lexical part says where the bronze is read: one call, in `data._read_players`, whose only
caller is `load_players`.

Mutations, each applied, seen failing and restored (tasks/todo.md, task 60, phase B2): the guard
removed from `load_players`; the guard removed from `PoseRows.__post_init__`; the frozen-entry
check, the code-tree check and the dirty-tree check removed from `assert_confirmation_open`.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tracklab.pose import coverage, data, probe, protocol
from tracklab.pose.coverage import COVERAGE_NAME, coverage_match, run_pose_coverage
from tracklab.pose.data import CountingHandle, PoseRows, load_players, require_readable
from tracklab.pose.sweep import SWEEP_NAME
from tracklab.runs.data import HeldOutLocked
from tracklab.runs.protocol import seal

POSE = Path(data.__file__).parent
REPORTS = Path(__file__).resolve().parents[2] / "reports"


def _two_matches(kit: SimpleNamespace, root: Path) -> Path:
    for match in (kit.calibration, kit.confirmation):
        kit.write_bronze(
            root,
            match,
            [
                kit.runner(7, start=100, n=60, speed_m_s=6.0),
                kit.runner(8, start=100, n=40, speed_m_s=4.0, period=2),
            ],
        )
    return root


# --- the guard -----------------------------------------------------------------------------


def test_the_confirmation_match_is_closed_while_the_protocol_is_in_design(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    root = _two_matches(pose_kit, tmp_path / "data")
    with pytest.raises(HeldOutLocked, match="'design'"):
        require_readable(pose_kit.confirmation)
    with pytest.raises(HeldOutLocked, match="'design'"):
        load_players(root, pose_kit.confirmation)
    rows = load_players(root, pose_kit.calibration)
    assert rows.match_id == pose_kit.calibration and len(rows.frame) == 100
    with pytest.raises(ValueError, match="neither"):
        require_readable(1874553)


def test_load_players_refuses_before_it_opens_anything(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    """The plan's mutation: with the guard taken out of `load_players`, this asks for a file
    that is not there and fails with FileNotFoundError instead of the guard's refusal."""
    with pytest.raises(HeldOutLocked):
        load_players(tmp_path / "nowhere", pose_kit.confirmation)


def test_no_pose_rows_of_the_confirmation_match_come_into_being(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    root = _two_matches(pose_kit, tmp_path / "data")
    rows = load_players(root, pose_kit.calibration)
    with pytest.raises(HeldOutLocked):
        replace(rows, match_id=pose_kit.confirmation)  # a calibration one relabelled
    arrays = {f.name: getattr(rows, f.name) for f in fields(rows) if f.name != "match_id"}
    with pytest.raises(HeldOutLocked):
        PoseRows(pose_kit.confirmation, **arrays)  # built by hand


def test_frozen_and_clean_opens_and_the_rows_are_sorted(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    root = _two_matches(pose_kit, tmp_path / "data")
    pose_repo.commit(pose_repo.frozen(), "frozen")
    rows = load_players(root, pose_kit.confirmation)
    assert [p for p, _ in rows.players()] == [7, 8]
    for _, sl in rows.players():
        assert np.all(np.diff(rows.frame[sl]) == 1)
    assert rows.joints.shape == (100, 29, 3) and rows.mae_cm.shape == (100, 29)
    assert set(rows.period.tolist()) == {1, 2}


def test_a_dirty_tree_closes_it_even_frozen(pose_repo: Any) -> None:
    pose_repo.commit(pose_repo.frozen(), "frozen")
    data.assert_confirmation_open()
    (pose_repo.root / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(HeldOutLocked, match="dirty"):
        data.assert_confirmation_open()


def test_a_frozen_stage_without_its_history_entry_opens_nothing(
    pose_repo: Any, pose_kit: SimpleNamespace
) -> None:
    frozen = pose_repo.frozen()
    cut = seal({**frozen, "history": frozen["history"][:1]})
    pose_repo.commit(cut, "frozen without the entry")
    with pytest.raises(HeldOutLocked, match="history has no frozen entry"):
        data.assert_confirmation_open()
    first = seal({**frozen, "history": frozen["history"][::-1]})
    pose_repo.commit(first, "frozen entry first")
    with pytest.raises(HeldOutLocked, match="history has no frozen entry"):
        data.assert_confirmation_open()


def test_a_code_commit_after_the_freeze_closes_it(pose_repo: Any) -> None:
    pose_repo.commit(pose_repo.frozen(), "frozen")
    data.assert_confirmation_open()
    (pose_repo.root / data.CODE_IN_REPO / "gait.py").write_text("# changed\n", encoding="utf-8")
    pose_repo.commit(None, "code after the freeze")
    with pytest.raises(HeldOutLocked, match="not the one the freeze recorded"):
        data.assert_confirmation_open()


def test_an_edited_or_missing_protocol_is_refused(
    pose_repo: Any, pose_kit: SimpleNamespace
) -> None:
    edited = pose_repo.frozen()
    edited["stage"] = "frozen"
    edited["design"]["split"]["calibration"] = [pose_kit.confirmation]  # not resealed
    pose_repo.commit(edited, "edited by hand")
    with pytest.raises(HeldOutLocked, match="content_sha256"):
        require_readable(pose_kit.calibration)
    (pose_repo.root / data.PROTOCOL_IN_REPO).unlink()
    pose_repo.commit(None, "no protocol")
    with pytest.raises(HeldOutLocked, match="holds no"):
        require_readable(pose_kit.calibration)


# --- every public name, by what it does with the confirmation match ---------------------------

REFUSES_THE_CONFIRMATION_MATCH = {
    "data.require_readable",
    "data.load_players",
    "data.PoseRows",
    "data.assert_confirmation_open",
    "probe.admitted",  # takes PoseRows, of which the confirmation match has none
    "probe.window_rows",  # the same
    "probe.mae_rows",  # the same
    "probe.z_rows",  # the same
    "probe.build_calibration",  # the same
}
TAKES_POSE_ROWS = {
    "probe.admitted",
    "probe.window_rows",
    "probe.mae_rows",
    "probe.z_rows",
    "probe.build_calibration",
}
COUNTS_ONLY = {
    "data.CountingHandle",
    "coverage.coverage_match",
    "coverage.build_report",
    "coverage.run_pose_coverage",
    "protocol.denominators",
    "protocol.run_pose_protocol",
}
# No match id: the calibration one comes from the committed protocol.
CALIBRATION_ONLY = {"probe.run_pose_probe"}
# The format reader the bronze is built with (tasks 55 and 58): it takes a path or lines, no
# match id, and nothing under `tracklab.pose` calls it (the lexical test below).
FORMAT_READER = {
    "jsonl.PoseFormatError",
    "jsonl.PosePlayer",
    "jsonl.PoseFrame",
    "jsonl.parse_frame",
    "jsonl.iter_frames",
    "jsonl.open_lines",
}
# Arithmetic on what the caller passes, git and the protocol, the sweep's synthetic runners
# (from the versioned clip of the sample, not a match's bronze), or no input at all.
READS_NO_POSE = {
    "data.repo_root",
    "data.head_commit",
    "data.code_tree_sha",
    "data.dirty_code_paths",
    "data.committed_protocol",
    "data.committed_split",
    "coverage.match_ids",
    "protocol.band",
    "protocol.file_sha256",
    "protocol.design",
    "protocol.build_protocol",
    "protocol.render",
    "probe.cap_mae",
    "probe.window_speeds",
    "probe.window_summary",
    "probe.counts_for_rule",
    "probe.sd_rows",
    "probe.kinematics_rows",
    "probe.classify",
    "probe.kills_the_noise",
    "probe.choose",
    "probe.rule_w_cap",
    "probe.protocol_record",
    "probe.protocol_problems",
    "probe.consistency_problems",
}


def _public_names(module: ModuleType) -> set[str]:
    short = module.__name__.rsplit(".", 1)[-1]
    return {
        f"{short}.{n}"
        for n, v in vars(module).items()
        if not n.startswith("_")
        and (inspect.isfunction(v) or inspect.isclass(v))
        and v.__module__ == module.__name__
    }


PUBLIC = set[str]().union(
    *(
        _public_names(importlib.import_module(f"tracklab.pose.{m.name}"))
        for m in pkgutil.iter_modules([str(POSE)])
    )
)
for _module in ("gait", "criteria", "sweep"):  # arithmetic and synthetic runners, all of them
    READS_NO_POSE |= _public_names(importlib.import_module(f"tracklab.pose.{_module}"))

# Floats a counting result may hold, by the last key of their path: the two listed exceptions
# of `CountingHandle` and the shares and means coverage computes from integers.
FLOAT_KEYS = {
    "mae_cm",
    "z_m",
    "share_frames_with_pose",
    "share_player_frames_with_pose",
    "mean_over_frames_with_pose",
}


def _floats_inside(obj: object, path: str = "value") -> list[str]:
    """Where `obj` holds an array or a float, outside `FLOAT_KEYS`."""
    if isinstance(obj, np.ndarray | np.floating | float):
        return [path]
    if is_dataclass(obj) and not isinstance(obj, type):
        return [
            p for f in fields(obj) for p in _floats_inside(getattr(obj, f.name), f"{path}.{f.name}")
        ]
    if isinstance(obj, Mapping):
        return [
            p
            for k, v in obj.items()
            if k not in FLOAT_KEYS
            for p in _floats_inside(v, f"{path}[{k!r}]")
        ]
    if isinstance(obj, list | tuple | set):
        return [p for i, v in enumerate(obj) for p in _floats_inside(v, f"{path}[{i}]")]
    return []


def test_the_walk_sees_a_float_wherever_it_hides() -> None:
    assert _floats_inside({"a": [(1, np.float64(2.0))]}) == ["value['a'][0][1]"]
    assert _floats_inside({"mae_cm": 1.5, "n": [1, 2], "z_m": {"min": -0.5}}) == []
    assert _floats_inside({"x": np.zeros(2)}) == ["value['x']"]


def test_every_public_name_of_pose_refuses_the_confirmation_match_or_counts_only(
    pose_repo: Any,
    pose_kit: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = (
        REFUSES_THE_CONFIRMATION_MATCH,
        COUNTS_ONLY,
        CALIBRATION_ONLY,
        FORMAT_READER,
        READS_NO_POSE,
    )
    assert PUBLIC == set().union(*groups)
    assert sum(len(g) for g in groups) == len(PUBLIC)  # pairwise disjoint
    assert TAKES_POSE_ROWS <= REFUSES_THE_CONFIRMATION_MATCH
    held = pose_kit.confirmation
    root = tmp_path / "data"
    pose_kit.write_bronze(root, held, [pose_kit.runner(7, start=100, n=60, speed_m_s=6.0)])

    # refusals
    with pytest.raises(HeldOutLocked):
        require_readable(held)
    with pytest.raises(HeldOutLocked):
        load_players(root, held)
    with pytest.raises(HeldOutLocked):
        data.assert_confirmation_open()
    for qualified in sorted(TAKES_POSE_ROWS):
        module_name, name = qualified.split(".")
        function = getattr(importlib.import_module(f"tracklab.pose.{module_name}"), name)
        first = next(iter(inspect.signature(function).parameters.values()))
        assert first.annotation == "PoseRows", qualified

    # counts only: called with the confirmation match, what comes back walked
    exercised: set[str] = set()

    def counted(name: str, value: object) -> object:
        assert name in COUNTS_ONLY, name
        assert _floats_inside(value) == [], name
        exercised.add(name)
        return value

    handle = CountingHandle(root, held)
    methods = {
        n: getattr(handle, n)
        for n, v in vars(CountingHandle).items()
        if inspect.isfunction(v) and not n.startswith("_")
    }
    assert set(methods) == {
        "exists",
        "is_whole",
        "frames_by_period",
        "players_by_period",
        "frames_present",
        "frames_posed",
        "runs",
        "run_lengths",
        "mae_cm",
        "z_range_m",
    }
    for name, method in methods.items():
        value = method((25,)) if name == "runs" else method()
        if name in ("mae_cm", "z_range_m"):  # the two listed exceptions: no position
            continue
        counted("data.CountingHandle", value)
    assert handle.frames_present() == {7: 60}
    m = counted("coverage.coverage_match", coverage_match(root, held))
    assert isinstance(m, dict) and m["periods"]["total"]["with_pose"] == 60
    report, skipped = coverage.build_report(root, [held])
    counted("coverage.build_report", (report, skipped))
    reports = tmp_path / "reports"
    monkeypatch.setattr(coverage, "match_ids", lambda _path=None: [held])
    assert counted("coverage.run_pose_coverage", run_pose_coverage(root, reports)) == 0
    assert (reports / COVERAGE_NAME).is_file()
    assert counted("protocol.denominators", protocol.denominators(root, held)) == {
        "players_listed": 1,
        "players_with_pose": 1,
    }
    # both matches of the manifest: 1925299 has no bronze here, so nothing is written
    (reports / SWEEP_NAME).write_bytes((REPORTS / SWEEP_NAME).read_bytes())
    assert counted("protocol.run_pose_protocol", protocol.run_pose_protocol(root, reports)) == 1
    assert "whole bronze for 1 of 2" in capsys.readouterr().out
    assert not (reports / protocol.PROTOCOL_NAME).exists()
    assert exercised == COUNTS_ONLY

    # calibration only: on a root that holds the confirmation match alone, nothing is written
    assert probe.run_pose_probe(root, reports) == 1
    assert not (reports / probe.CALIBRATION_NAME).exists()
    assert "no whole bronze of 1925299" in capsys.readouterr().out


def _calls(tree: ast.AST, name: str) -> list[ast.AST]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == name)
            or (isinstance(n.func, ast.Name) and n.func.id == name)
        )
    ]


def test_the_bronze_is_read_in_one_place_whose_only_caller_is_load_players() -> None:
    """One read of `bodypose_players` rows: `pq.read_table`, in `_read_players`, called from
    `load_players` alone; no other module of the package imports a Parquet or database reader
    or the format reader, so nothing else under `tracklab.pose` opens a match."""
    readers = {"duckdb", "pyarrow", "pyarrow.parquet", "pandas", "polars"}
    for path in sorted(POSE.glob("*.py")):
        if path.name in ("data.py", "jsonl.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not imported & readers, path.name
        from_jsonl = {
            a.name
            for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module == "tracklab.pose.jsonl"
            for a in n.names
        }
        assert from_jsonl <= {"JOINTS"}, path.name  # the constant, not the readers beside it
        assert not _calls(tree, "read_table") and not _calls(tree, "connect"), path.name
    tree = ast.parse((POSE / "data.py").read_text(encoding="utf-8"))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert [f for f, node in functions.items() if _calls(node, "read_table")] == ["_read_players"]
    callers = [f for f, node in functions.items() if _calls(node, "_read_players")]
    assert callers == ["load_players"]
    load = functions["load_players"]
    first = load.body[1] if isinstance(load.body[0], ast.Expr) else load.body[0]
    assert _calls(first, "require_readable"), "the guard is the first statement"
