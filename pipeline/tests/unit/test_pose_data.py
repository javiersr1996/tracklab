"""The guard on 1996435 (`tracklab.pose.data`, task 60, phase B2), on a throwaway repository and
a Body Pose bronze written by hand: no real pose is read.

The confirmation match opens only when the protocol committed in HEAD is frozen, with a frozen
entry after the design ones; the `pose/` tree of HEAD is the one the freeze recorded; the
installed numpy is the design's; HEAD holds the second time's verdict, sealed, answering to that
frozen protocol, computed by that tree, alive and with a finite half IQR; and the tree is clean.
Behavioural, not lexical: every public name of every module of `tracklab.pose` is classified,
the ones that could return pose values are called with 1996435 while the protocol is in design
and must refuse, and what the counting ones return is walked for floats. The lexical part says
where the bronze is read: one call, in `data._read_players`, whose only caller is
`load_players`; nothing outside `data.py` names its private parts, imports the format reader or
names `bodypose_players`.

Mutations, each applied, seen failing and restored (tasks/todo.md, task 60, phase B2): the guard
removed from `load_players`; the guard removed from `PoseRows.__post_init__`; each condition of
`assert_confirmation_open` removed in turn (frozen entry, code tree, numpy, verdict in HEAD, its
seal, its protocol, its tree, alive, finite half IQR, dirty tree); the `match_id` check removed
from `_read_players`; `z_range_m` returning every z; the reviewer's `pose/peek.py`.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tracklab.pose import coverage, data, metric, probe, protocol, verdict
from tracklab.pose.coverage import COVERAGE_NAME, coverage_match, run_pose_coverage
from tracklab.pose.data import CountingHandle, PoseRows, load_players, require_readable
from tracklab.pose.sweep import SWEEP_NAME
from tracklab.runs.data import HeldOutLocked
from tracklab.runs.protocol import seal

POSE = Path(data.__file__).parent
SRC = POSE.parent
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


def test_a_file_of_another_match_under_this_name_is_refused(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    """1996435's rows saved as 1925299's file: `_read_players` reads `match_id` and refuses."""
    root = tmp_path / "data"
    body = pose_kit.runner(7, start=100, n=30, speed_m_s=6.0)
    pose_kit.write_bronze(root, pose_kit.calibration, [body], stored_as=pose_kit.confirmation)
    with pytest.raises(ValueError, match="rows of another match"):
        load_players(root, pose_kit.calibration)


def test_frozen_with_its_verdict_and_clean_opens_and_the_rows_are_sorted(
    pose_repo: Any, pose_kit: SimpleNamespace, tmp_path: Path
) -> None:
    root = _two_matches(pose_kit, tmp_path / "data")
    pose_repo.commit(pose_repo.frozen(), "frozen")
    with pytest.raises(HeldOutLocked, match="holds no"):  # frozen, but no verdict yet
        load_players(root, pose_kit.confirmation)
    pose_repo.open()
    rows = load_players(root, pose_kit.confirmation)
    assert [p for p, _ in rows.players()] == [7, 8]
    for _, sl in rows.players():
        assert np.all(np.diff(rows.frame[sl]) == 1)
    assert rows.joints.shape == (100, 29, 3) and rows.mae_cm.shape == (100, 29)
    assert set(rows.period.tolist()) == {1, 2}


def test_a_dirty_tree_closes_it(pose_repo: Any) -> None:
    pose_repo.open()
    data.assert_confirmation_open()
    (pose_repo.root / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(HeldOutLocked, match="dirty"):
        data.assert_confirmation_open()


def test_a_frozen_stage_without_its_history_entry_opens_nothing(pose_repo: Any) -> None:
    frozen = pose_repo.open()
    cut = seal({**frozen, "history": frozen["history"][:1]})
    pose_repo.commit(cut, "frozen without the entry")
    with pytest.raises(HeldOutLocked, match="history has no frozen entry"):
        data.assert_confirmation_open()
    first = seal({**frozen, "history": frozen["history"][::-1]})
    pose_repo.commit(first, "frozen entry first")
    with pytest.raises(HeldOutLocked, match="history has no frozen entry"):
        data.assert_confirmation_open()


def test_a_code_commit_after_the_freeze_closes_it(pose_repo: Any) -> None:
    pose_repo.open()
    data.assert_confirmation_open()
    (pose_repo.root / data.CODE_IN_REPO / "gait.py").write_text("# changed\n", encoding="utf-8")
    pose_repo.commit(None, "code after the freeze")
    with pytest.raises(HeldOutLocked, match="not the one the freeze recorded"):
        data.assert_confirmation_open()


def test_another_numpy_than_the_designs_closes_it(
    pose_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pose_repo.open()
    data.assert_confirmation_open()
    real = data.importlib.metadata.version
    monkeypatch.setattr(
        data.importlib.metadata,
        "version",
        lambda name: "0.0.1" if name == "numpy" else real(name),
    )
    with pytest.raises(HeldOutLocked, match="numpy 0.0.1"):
        data.assert_confirmation_open()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"alive": False}, "P6 died on 1925299"),
        ({"half_iqr_hz": None}, "no finite m4.half_iqr_hz"),
        ({"code_tree_sha": "0" * 40}, "not computed by the frozen code"),
        ({"answers_to": "design"}, "answers to another protocol"),
        ({"unsealed": True}, "fails its content_sha256"),
    ],
)
def test_the_verdict_in_head_must_be_sealed_alive_and_of_the_frozen_protocol_and_code(
    pose_repo: Any, change: dict[str, Any], message: str
) -> None:
    """Each condition the guard reads in pose_verdict.json, broken alone; the rest as `open`
    commits them, which opens (the test's own first assertion)."""
    frozen = pose_repo.open()
    data.assert_confirmation_open()
    if change.get("answers_to") == "design":
        change = {"answers_to": seal({**frozen, "stage": "design"})}
    if change.pop("unsealed", False):
        broken = pose_repo.verdict(frozen)
        broken["m4"]["half_iqr_hz"] = 0.2  # edited after the seal
    else:
        broken = pose_repo.verdict(frozen, **change)
    pose_repo.commit(broken, "broken verdict", at=data.VERDICT_IN_REPO)
    with pytest.raises(HeldOutLocked, match=message):
        data.assert_confirmation_open()


def test_an_edited_or_missing_protocol_is_refused(
    pose_repo: Any, pose_kit: SimpleNamespace
) -> None:
    edited = pose_repo.frozen()
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
    "verdict.window_estimates",  # the same
    "verdict.build_verdict",  # the same
}
TAKES_POSE_ROWS = {
    "probe.admitted",
    "probe.window_rows",
    "probe.mae_rows",
    "probe.z_rows",
    "probe.build_calibration",
    "verdict.window_estimates",
    "verdict.build_verdict",
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
CALIBRATION_ONLY = {"probe.run_pose_probe", "verdict.run_pose_verdict"}
# Both matches, the confirmation one through `load_players`: refused while the guard is closed.
BOTH_PAST_THE_GUARD = {"metric.run_pose_metric"}
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
# Arithmetic on what the caller passes (windows already estimated, tables, figures), git and
# the protocol, the sweep's synthetic runners (from the versioned clip of the sample, not a
# match's bronze), or no input at all.
READS_NO_POSE = {
    "data.repo_root",
    "data.head_commit",
    "data.code_tree_sha",
    "data.dirty_code_paths",
    "data.dirty_among",
    "data.committed_protocol",
    "data.committed_verdict",
    "data.committed_split",
    "coverage.match_ids",
    "protocol.band",
    "protocol.file_sha256",
    "protocol.design",
    "protocol.build_protocol",
    "protocol.render",
    "protocol.freeze_payload",
    "protocol.frozen_problems",
    "freeze.run_pose_freeze",
    "probe.cap_mae",
    "probe.window_speeds",
    "probe.window_summary",
    "probe.counts_for_rule",
    "probe.sd_rows",
    "probe.kinematics_rows",
    "probe.classify",
    "probe.kills_the_noise",
    "probe.spares_the_sane",
    "probe.is_eligible",
    "probe.choose",
    "probe.candidates",
    "probe.amplitude_for",
    "probe.adjusted_bar",
    "probe.rule_w_cap",
    "probe.cell_counts",
    "probe.protocol_record",
    "probe.protocol_problems",
    "probe.consistency_problems",
    "verdict.Window",
    "verdict.criteria_players",
    "verdict.second_time",
    "verdict.verdict_dies_at",
    "verdict.frozen_here",
    "verdict.consistency_problems",
    "metric.player_rows",
    "metric.admitted_minima",
    "metric.m_verdict",
    "metric.match_verdicts",
    "metric.build_metric",
    "metric.recompute_problems",
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
# of `CountingHandle`'s coverage and the shares and means coverage computes from integers.
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
        BOTH_PAST_THE_GUARD,
        FORMAT_READER,
        READS_NO_POSE,
    )
    assert PUBLIC == set().union(*groups)
    assert sum(len(g) for g in groups) == len(PUBLIC)  # pairwise disjoint
    assert TAKES_POSE_ROWS <= REFUSES_THE_CONFIRMATION_MATCH
    held = pose_kit.confirmation
    root = tmp_path / "data"
    pose_kit.write_bronze(root, held, [pose_kit.runner(7, start=100, n=60, speed_m_s=6.0)])
    pose_kit.write_lineup(root, held, [(7, 100, 9)])

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
        "lineup",
    }
    for name, method in methods.items():
        if name not in ("mae_cm", "z_range_m"):
            counted("data.CountingHandle", method((25,)) if name == "runs" else method())
    # the two listed exceptions, by shape: four quantiles, 29 joints of four; two numbers
    (overall, by_joint) = handle.mae_cm()
    assert len(overall) == 4 and len(by_joint) == 29 and {len(j) for j in by_joint} == {4}
    z = handle.z_range_m()
    assert isinstance(z, tuple) and len(z) == 2 and all(isinstance(v, float) for v in z)
    assert handle.frames_present() == {7: 60} and handle.lineup() == [(7, 100, 9)]
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
    assert not (reports / protocol.CALIBRATION_NAME).exists()
    assert "no whole bronze of 1925299" in capsys.readouterr().out
    assert verdict.run_pose_verdict(root, reports) == 1
    assert not (reports / verdict.VERDICT_NAME).exists()
    # both matches past the guard: with the protocol in design, nothing is read nor written
    _two_matches(pose_kit, root)
    assert metric.run_pose_metric(root, reports) == 1
    assert not (reports / metric.METRIC_NAME).exists()
    assert "1996435 stays closed" in capsys.readouterr().out


# --- where the bronze is read: lexical ---------------------------------------------------------

PRIVATE_DOORS = re.compile(r"\b_read_players\b|\._rows\b|\._con\b")
# Every file of src/ allowed to name the players' table: the builder, the fixtures' cut, the
# asset registry and the guard itself.
NAMES_THE_TABLE = {
    "bronze/football/bodypose.py",
    "fixtures.py",
    "dagster_defs/assets_bronze.py",
    "pose/data.py",
}


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


def lexical_problems(src: Path) -> list[str]:
    """What breaks the one-door rule under `src` (a `tracklab` package directory)."""
    problems = []
    readers = {"duckdb", "pyarrow", "pyarrow.parquet", "pandas", "polars"}
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        text = path.read_text(encoding="utf-8")
        if "bodypose_players" in text and rel not in NAMES_THE_TABLE:
            problems.append(f"{rel} names bodypose_players")
        if not rel.startswith("pose/") or rel in ("pose/data.py", "pose/jsonl.py"):
            continue
        if PRIVATE_DOORS.search(text):
            problems.append(f"{rel} names a private door of data.py")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {a.name for a in node.names}
                if names & readers or any(n.endswith("jsonl") for n in names):
                    problems.append(f"{rel} imports {sorted(names)}")
            if isinstance(node, ast.ImportFrom):
                module = ("." * node.level) + (node.module or "")
                names = {a.name for a in node.names}
                if module in readers or module.split(".")[0] in readers:
                    problems.append(f"{rel} imports from {module}")
                if module.endswith("jsonl") and names != {"JOINTS"}:
                    problems.append(f"{rel} imports {sorted(names)} from {module}")
                if "jsonl" in names:
                    problems.append(f"{rel} imports the jsonl module from {module}")
        if re.search(r"\bjsonl\b", text.replace("from tracklab.pose.jsonl import JOINTS", "")):
            problems.append(f"{rel} names jsonl beyond its JOINTS")
        if _calls(tree, "read_table") or _calls(tree, "connect"):
            problems.append(f"{rel} opens a Parquet file or a database")
    return problems


def test_the_bronze_is_read_in_one_place_whose_only_caller_is_load_players() -> None:
    """One read of `bodypose_players` rows: `pq.read_table`, in `_read_players`, called from
    `load_players` alone, after the guard; no other module of `tracklab.pose` names a private
    part of `data.py`, imports a Parquet or database reader or the format reader (save its
    JOINTS), and no file of src/ outside four names the table."""
    assert lexical_problems(SRC) == []
    tree = ast.parse((POSE / "data.py").read_text(encoding="utf-8"))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert [f for f, node in functions.items() if _calls(node, "read_table")] == ["_read_players"]
    callers = [f for f, node in functions.items() if _calls(node, "_read_players")]
    assert callers == ["load_players"]
    load = functions["load_players"]
    first = load.body[1] if isinstance(load.body[0], ast.Expr) else load.body[0]
    assert _calls(first, "require_readable"), "the guard is the first statement"


def test_the_lexical_rule_catches_a_module_that_peeks_past_it(tmp_path: Path) -> None:
    """The reviewer's mutation: a `pose/peek.py` reaching `_read_players`, `CountingHandle._rows`
    and the format reader. Copied beside the real package, every rule sees it."""
    src = tmp_path / "tracklab"
    for path in SRC.rglob("*.py"):
        target = src / path.relative_to(SRC)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (src / "pose" / "peek.py").write_text(
        "from tracklab.bronze.common import bronze_path\n"
        "from tracklab.pose import data, jsonl\n\n\n"
        "def _peek(data_dir, match_id):\n"
        '    path = bronze_path(data_dir, "football", "bodypose_players", match_id)\n'
        "    rows = data._read_players(path, match_id)\n"
        '    raw = data.CountingHandle(data_dir, match_id)._rows("select joints", "players")\n'
        "    return rows, raw, jsonl.iter_frames\n",
        encoding="utf-8",
    )
    found = lexical_problems(src)
    assert "pose/peek.py names bodypose_players" in found
    assert "pose/peek.py names a private door of data.py" in found
    assert "pose/peek.py imports the jsonl module from tracklab.pose" in found
    (src / "pose" / "peek.py").write_text("from .jsonl import iter_frames\n", encoding="utf-8")
    assert lexical_problems(src) == [
        "pose/peek.py imports ['iter_frames'] from .jsonl",
        "pose/peek.py names jsonl beyond its JOINTS",
    ]
