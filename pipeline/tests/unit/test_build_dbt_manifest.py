"""`tracklab build` keeps the dbt manifest up to date (P18, task 145).

The silver and gold fingerprints and `--select` read `dbt/target/manifest.json`; a manifest older
than a model hides the change. The build parses dbt when anything under `dbt/` (not dbt's own
output) is newer.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from dagster import AssetKey

from tracklab.build import RunResult, manifest_is_stale, refresh_dbt_manifest, run_build


def _dbt_tree(root: Path) -> tuple[Path, Path]:
    dbt = root / "dbt"
    (dbt / "models").mkdir(parents=True)
    (dbt / "target").mkdir()
    (dbt / "models" / "a.sql").write_text("select 1\n", encoding="utf-8", newline="\n")
    manifest = dbt / "target" / "manifest.json"
    manifest.write_text("{}", encoding="utf-8", newline="\n")
    os.utime(dbt / "models" / "a.sql", (1000, 1000))
    os.utime(manifest, (2000, 2000))
    return dbt, manifest


def test_the_manifest_is_stale_only_when_a_project_file_is_newer(tmp_path: Path) -> None:
    dbt, manifest = _dbt_tree(tmp_path)
    assert not manifest_is_stale(dbt, manifest)

    os.utime(dbt / "models" / "a.sql", (3000, 3000))
    assert manifest_is_stale(dbt, manifest)

    os.utime(dbt / "models" / "a.sql", (1000, 1000))
    (dbt / "logs").mkdir()
    (dbt / "logs" / "dbt.log").write_text("x", encoding="utf-8")
    (dbt / "target" / "run_results.json").write_text("{}", encoding="utf-8")
    os.utime(dbt / "logs" / "dbt.log", (3000, 3000))
    os.utime(dbt / "target" / "run_results.json", (3000, 3000))
    assert not manifest_is_stale(dbt, manifest)

    manifest.unlink()
    assert manifest_is_stale(dbt, manifest)


def test_a_stale_manifest_is_parsed_and_a_fresh_one_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dbt, manifest = _dbt_tree(tmp_path)
    calls: list[list[str]] = []

    class FakeRunner:
        def invoke(self, args: list[str]) -> SimpleNamespace:
            calls.append(args)
            return SimpleNamespace(success=True)

    monkeypatch.setattr("dbt.cli.main.dbtRunner", FakeRunner)

    assert refresh_dbt_manifest(dbt, manifest)
    assert calls == []

    os.utime(dbt / "models" / "a.sql", (3000, 3000))
    assert refresh_dbt_manifest(dbt, manifest)
    assert [c[0] for c in calls] == ["parse"]


def test_run_build_refreshes_the_manifest_and_stops_when_the_parse_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran: list[str] = []
    monkeypatch.setattr("tracklab.build.refresh_dbt_manifest", lambda: False)

    def execute(keys: Sequence[AssetKey] | None, record_dir: Path) -> RunResult:
        ran.append("job")
        return RunResult({}, [], "run", {})

    code = run_build(None, tmp_path / "build", tmp_path / "data", execute=execute)

    assert code == 1
    assert ran == []
    assert "dbt parse failed" in capsys.readouterr().out
