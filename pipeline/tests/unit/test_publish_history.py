"""`tracklab publish history` (task 131): `history.json` only grows, one entry per build record,
a v1 record's missing dbt and contract facts come from outside or stay `null`, and `--check`
compares the records with the file (a mutated duration in the file must fail it)."""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tracklab.cli import main
from tracklab.publish.history import run_publish_history

V1_ID = "20261013T150000Z_aaaaaaa"
V2_ID = "20261102T190000Z_bbbbbbb"
REQUIRE_FULL = "TRACKLAB_REQUIRE_FULL"


def _v1() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "git_sha": "a" * 40,
        "select": "group:silver or group:gold",
        "started_utc": "2026-10-13T15:00:00+00:00",
        "finished_utc": "2026-10-13T15:10:00+00:00",
        "wall_seconds": 600.5,
        "steps": [
            {
                "step_key": "silver",
                "assets": ["silver_frames"],
                "group": "silver",
                "status": "success",
                "duration_ms": 120000.25,
                "dbt_seconds": {"silver_frames": 2.0},
            },
            {
                "step_key": "gold",
                "assets": ["gold_x"],
                "group": "gold",
                "status": "success",
                "duration_ms": 8000.5,
                "dbt_seconds": {},
            },
            {
                "step_key": "quality_noise",
                "assets": ["quality_noise"],
                "group": "quality",
                "status": "not_run",
                "duration_ms": None,
                "dbt_seconds": {},
            },
        ],
    }


def _dbt(tests: dict[str, int], elapsed: float = 10.0) -> dict[str, Any]:
    return {
        "tests": {"pass": 0, "fail": 0, "warn": 0, "error": 0, "skipped": 0, **tests},
        "nodes": {"success": 12, "error": 0, "skipped": 0},
        "elapsed_seconds": elapsed,
    }


def _v2() -> dict[str, Any]:
    record = _v1()
    record.update(
        schema_version=2,
        run_id="739e1aee-88cc-4da7-8778-c83f3e4b873a",
        git_sha="b" * 40,
        select=None,
        started_utc="2026-11-02T19:00:00+00:00",
        finished_utc="2026-11-02T19:54:00+00:00",
        contracts={
            "files": 15,
            "executed": True,
            "status": "passed",
            "started_utc": "2026-11-02T19:50:00.000+00:00",
            "finished_utc": "2026-11-02T19:54:00.000+00:00",
            "duration_seconds": 244.5,
            "pytest_exit_code": 0,
            "passed": 104,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
        },
    )
    silver, gold, noise = record["steps"]
    silver.update(
        started_utc="2026-11-02T19:00:43.793+00:00",
        finished_utc="2026-11-02T19:05:51.039+00:00",
        dbt=_dbt({"pass": 122, "fail": 2}),
        partitions={
            "written": ["basketball/1"],
            "skipped": ["football/2", "football/3"],
            "deleted": [],
        },
        incremental={"mode": "incremental", "reason": "1 of 3 matches changed"},
    )
    gold.update(
        started_utc="2026-11-02T19:06:00.000+00:00",
        finished_utc="2026-11-02T19:06:10.000+00:00",
        dbt=None,
        partitions={"written": [], "skipped": [], "deleted": []},
        incremental={"mode": "skip", "reason": "no input changed since run x"},
    )
    noise.update(started_utc=None, finished_utc=None, dbt=None, partitions=None, incremental=None)
    return record


def _write_record(record_dir: Path, record_id: str, record: dict[str, Any]) -> Path:
    record_dir.mkdir(parents=True, exist_ok=True)
    path = record_dir / f"{record_id}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _run_results(
    target: Path, name: str, generated_at: str, *, passed: int, failed: int = 0
) -> None:
    folder = target / name
    folder.mkdir(parents=True)
    results = [{"unique_id": f"test.p.t{i}", "status": "pass"} for i in range(passed)]
    results += [{"unique_id": f"test.p.f{i}", "status": "fail"} for i in range(failed)]
    results += [{"unique_id": "model.p.m", "status": "success"}]
    payload = {
        "metadata": {"generated_at": generated_at},
        "elapsed_time": 42.0,
        "results": results,
    }
    (folder / "run_results.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A git repo whose commit has two contract files; returns it and the commit's sha."""
    root = tmp_path / "repo"
    (root / "tests" / "contracts").mkdir(parents=True)
    for name in ("test_a.py", "test_b.py", "helper.py"):
        (root / "tests" / "contracts" / name).write_text("", encoding="utf-8")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], cwd=root, check=True)
    subprocess.run([*git, "add", "."], cwd=root, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "x"], cwd=root, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    return root, sha


class _Setup:
    def __init__(self, tmp_path: Path, repo: tuple[Path, str]) -> None:
        self.records = tmp_path / "build"
        self.out = tmp_path / "web"
        self.target = tmp_path / "dbt_target"
        self.target.mkdir()
        self.repo, self.sha = repo

    def run(self, *, check: bool = False) -> int:
        return run_publish_history(
            record_dir=self.records,
            out_dir=self.out,
            check=check,
            dbt_target=self.target,
            pipeline_dir=self.repo,
        )

    def entries(self) -> list[dict[str, Any]]:
        payload = json.loads((self.out / "history.json").read_text(encoding="utf-8"))
        entries: list[dict[str, Any]] = payload["entries"]
        return entries

    def edit(self, change: Callable[[list[dict[str, Any]]], object]) -> None:
        path = self.out / "history.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        change(payload["entries"])
        path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def setup(tmp_path: Path, repo: tuple[Path, str]) -> _Setup:
    return _Setup(tmp_path, repo)


def test_a_v2_record_becomes_one_entry_with_its_own_figures(setup: _Setup) -> None:
    _write_record(setup.records, V2_ID, _v2())

    assert setup.run() == 0

    (entry,) = setup.entries()
    assert (entry["id"], entry["record_version"], entry["sha"]) == (V2_ID, 2, "b" * 40)
    assert entry["select"] is None
    assert entry["wall_seconds"] == 600.5
    silver, gold, noise = entry["steps"]
    assert silver["duration_ms"] == 120000.25
    assert silver["started_utc"] == "2026-11-02T19:00:43.793+00:00"
    assert silver["partitions"] == {"written": 1, "skipped": 2, "deleted": 0}
    assert silver["incremental"]["mode"] == "incremental"
    assert silver["dbt"]["tests"]["pass"] == 122
    assert gold["dbt"] is None
    assert noise["status"] == "not_run" and noise["duration_ms"] is None
    # Only silver ran dbt: the total is silver's, gold's skip adds no zeros.
    assert entry["quality"]["dbt"] == {"tests": silver["dbt"]["tests"], "source": "record"}
    assert entry["quality"]["contracts"] == {
        "files": 15,
        "executed": True,
        "status": "passed",
        "passed": 104,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "duration_seconds": 244.5,
    }


def test_a_v1_takes_its_dbt_from_the_run_results_inside_its_window(setup: _Setup) -> None:
    record = _v1()
    record["git_sha"] = setup.sha
    _write_record(setup.records, V1_ID, record)
    _run_results(
        setup.target, "silver-aaaaaaa-1111111", "2026-10-13T15:05:00.5Z", passed=122, failed=2
    )
    _run_results(setup.target, "gold-aaaaaaa-2222222", "2026-10-13T15:09:00Z", passed=59)
    # Another day, and a step the record does not have: both outside.
    _run_results(setup.target, "silver-ccccccc-3333333", "2026-10-12T15:05:00Z", passed=1)
    _run_results(setup.target, "pose-aaaaaaa-4444444", "2026-10-13T15:05:00Z", passed=1)

    assert setup.run() == 0

    (entry,) = setup.entries()
    silver, gold, noise = entry["steps"]
    assert silver["dbt"]["tests"]["pass"] == 122 and silver["dbt"]["tests"]["fail"] == 2
    assert gold["dbt"]["tests"]["pass"] == 59
    assert noise["dbt"] is None
    assert entry["quality"]["dbt"]["tests"]["pass"] == 181
    assert entry["quality"]["dbt"]["source"] == "run_results"
    # No v2 facts are made up for a v1.
    assert silver["started_utc"] is None and silver["partitions"] is None
    assert silver["incremental"] is None
    assert entry["quality"]["contracts"] == {
        "files": 2,
        "executed": None,
        "status": None,
        "passed": None,
        "failed": None,
        "skipped": None,
        "errors": None,
        "duration_seconds": None,
    }


def test_a_v1_without_run_results_or_sha_has_no_data_never_zero(setup: _Setup) -> None:
    record = _v1()
    record["git_sha"] = "f" * 40  # not in the repo
    _write_record(setup.records, V1_ID, record)

    assert setup.run() == 0

    (entry,) = setup.entries()
    assert [s["dbt"] for s in entry["steps"]] == [None, None, None]
    assert entry["quality"]["dbt"] == {"tests": None, "source": None}
    assert entry["quality"]["contracts"]["files"] is None


def test_two_run_results_in_one_window_are_an_error(
    setup: _Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_record(setup.records, V1_ID, _v1())
    _run_results(setup.target, "silver-aaaaaaa-1111111", "2026-10-13T15:05:00Z", passed=1)
    _run_results(setup.target, "silver-bbbbbbb-2222222", "2026-10-13T15:06:00Z", passed=2)

    assert setup.run() == 1

    assert "2 dbt run_results of step 'silver'" in capsys.readouterr().out
    assert not (setup.out / "history.json").exists()


def test_a_record_that_left_the_disk_stays_and_an_old_entry_is_not_rewritten(
    setup: _Setup,
) -> None:
    first = _write_record(setup.records, V1_ID, _v1())
    assert setup.run() == 0
    kept = setup.entries()[0]

    first.unlink()
    _write_record(setup.records, V2_ID, _v2())
    assert setup.run() == 0

    assert [e["id"] for e in setup.entries()] == [V1_ID, V2_ID]
    assert setup.entries()[0] == kept

    # A changed record does not rewrite its entry: the file keeps what it had...
    changed = _v2()
    changed["wall_seconds"] = 1.0
    _write_record(setup.records, V2_ID, changed)
    assert setup.run() == 0
    assert setup.entries()[1]["wall_seconds"] == 600.5
    # ... and `--check` is what says the two now disagree.
    assert setup.run(check=True) == 1


def test_the_file_is_written_with_lf_and_twice_gives_the_same_bytes(setup: _Setup) -> None:
    _write_record(setup.records, V2_ID, _v2())
    assert setup.run() == 0
    first = (setup.out / "history.json").read_bytes()
    assert setup.run() == 0

    assert b"\r" not in first
    assert (setup.out / "history.json").read_bytes() == first


def test_check_passes_on_a_fresh_file_and_fails_on_a_mutated_duration(
    setup: _Setup, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_record(setup.records, V1_ID, _v1())
    _write_record(setup.records, V2_ID, _v2())
    assert setup.run() == 0
    assert setup.run(check=True) == 0

    def mutate(entries: list[dict[str, Any]]) -> None:
        entries[1]["steps"][0]["duration_ms"] += 1.0

    setup.edit(mutate)
    capsys.readouterr()
    assert setup.run(check=True) == 1
    assert f"{V2_ID}.steps[silver].duration_ms" in capsys.readouterr().out


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e[1].__setitem__("wall_seconds", 1.0),
        lambda e: e[1]["steps"][0]["dbt"]["tests"].__setitem__("fail", 0),
        lambda e: e[1]["steps"][0]["partitions"].__setitem__("written", 9),
        lambda e: e[1]["quality"]["contracts"].__setitem__("passed", 105),
        lambda e: e[0]["quality"]["contracts"].__setitem__("files", 3),
        lambda e: e[0].__setitem__("sha", "c" * 40),
        lambda e: e[0]["steps"].pop(),
        lambda e: e.pop(),
    ],
)
def test_check_catches_each_figure_it_publishes(
    setup: _Setup, mutate: Callable[[list[dict[str, Any]]], object]
) -> None:
    record = _v1()
    record["git_sha"] = setup.sha
    _write_record(setup.records, V1_ID, record)
    _write_record(setup.records, V2_ID, _v2())
    assert setup.run() == 0
    assert setup.run(check=True) == 0

    setup.edit(mutate)

    assert setup.run(check=True) == 1


def test_a_v1_dbt_figure_is_compared_while_run_results_exist_and_kept_when_they_are_gone(
    setup: _Setup,
) -> None:
    _write_record(setup.records, V1_ID, _v1())
    _run_results(setup.target, "silver-aaaaaaa-1111111", "2026-10-13T15:05:00Z", passed=122)
    assert setup.run() == 0

    setup.edit(lambda e: e[0]["steps"][0]["dbt"]["tests"].__setitem__("pass", 5))
    assert setup.run(check=True) == 1

    setup.edit(lambda e: e[0]["steps"][0]["dbt"]["tests"].__setitem__("pass", 122))
    (setup.target / "silver-aaaaaaa-1111111" / "run_results.json").unlink()
    assert setup.run(check=True) == 0


def test_check_fails_when_a_record_is_not_in_the_file_but_others_are(setup: _Setup) -> None:
    _write_record(setup.records, V1_ID, _v1())
    assert setup.run() == 0
    _write_record(setup.records, V2_ID, _v2())

    assert setup.run(check=True) == 1


def test_check_fails_when_there_is_no_file(setup: _Setup) -> None:
    _write_record(setup.records, V2_ID, _v2())

    assert setup.run(check=True) == 1


def test_no_records_is_partial_and_fails_only_under_require_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "publish",
        "history",
        "--check",
        "--record-dir",
        str(tmp_path / "build"),
        "--out-dir",
        str(tmp_path / "web"),
    ]
    monkeypatch.delenv(REQUIRE_FULL, raising=False)
    assert main(argv) == 0
    assert "PARTIAL:" in capsys.readouterr().out

    monkeypatch.setenv(REQUIRE_FULL, "1")
    assert main(argv) == 1


def test_another_data_root_is_partial_not_a_wall_of_differences(
    setup: _Setup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_record(setup.records, V2_ID, _v2())
    assert setup.run() == 0
    other = _v2()
    other["git_sha"] = "d" * 40
    _write_record(tmp_path / "fixture_build", "20261101T000000Z_ddddddd", other)
    argv = [
        "publish",
        "history",
        "--check",
        "--record-dir",
        str(tmp_path / "fixture_build"),
        "--out-dir",
        str(setup.out),
    ]
    monkeypatch.delenv(REQUIRE_FULL, raising=False)
    assert main(argv) == 0
    monkeypatch.setenv(REQUIRE_FULL, "1")
    assert main(argv) == 1


def test_an_unknown_record_version_fails(setup: _Setup) -> None:
    record = copy.deepcopy(_v1())
    record["schema_version"] = 3
    _write_record(setup.records, V1_ID, record)

    assert setup.run() == 1


def test_a_sha_with_no_contract_files_is_no_data_not_zero(setup: _Setup) -> None:
    for name in (setup.repo / "tests" / "contracts").glob("test_*.py"):
        name.rename(name.with_suffix(".txt"))
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "add", "-A"], cwd=setup.repo, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "y"], cwd=setup.repo, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=setup.repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    record = _v1()
    record["git_sha"] = sha
    _write_record(setup.records, V1_ID, record)

    assert setup.run() == 0

    assert setup.entries()[0]["quality"]["contracts"]["files"] is None


def test_a_v1_contract_count_stays_checkable_when_git_can_no_longer_give_it(
    setup: _Setup, tmp_path: Path
) -> None:
    record = _v1()
    record["git_sha"] = setup.sha
    _write_record(setup.records, V1_ID, record)
    assert setup.run() == 0
    assert setup.entries()[0]["quality"]["contracts"]["files"] == 2

    code = run_publish_history(
        record_dir=setup.records,
        out_dir=setup.out,
        check=True,
        dbt_target=setup.target,
        pipeline_dir=tmp_path,  # not a repo: git has no answer
    )

    assert code == 0
