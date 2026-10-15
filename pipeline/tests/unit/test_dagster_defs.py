"""The Dagster graph is whole: no asset reads something nothing writes (task 15).

Needs dbt/target/manifest.json (`dbt parse` or `dbt build` first, as CI does).
The bronze tables are hand-listed per builder, so they are checked against the two
things that cannot drift silently: the frozen schemas and the dbt sources.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dagster import AssetKey, materialize

import tracklab.bronze.basketball.meta
import tracklab.bronze.basketball.tracking
import tracklab.bronze.football.meta
import tracklab.bronze.football.tracking
from tracklab.dagster_defs import assets_pose, assets_runs, defs
from tracklab.dagster_defs.assets_bronze import BRONZE_TABLES, bronze_key

SCHEMAS_DIR = Path("src/tracklab/bronze/schemas")


def _materializable() -> set[AssetKey]:
    graph = defs.resolve_asset_graph()
    return {key for key in graph.get_all_asset_keys() if graph.get(key).is_materializable}


def test_every_upstream_is_written_by_an_asset_except_the_manifest() -> None:
    graph = defs.resolve_asset_graph()
    written = _materializable()
    read = set().union(*(graph.get(key).parent_keys for key in written))
    assert read - written == {AssetKey("manifest_sources")}


def test_every_frozen_bronze_schema_has_an_asset() -> None:
    frozen = {
        bronze_key(path.parent.name, path.name.removesuffix(".schema.json"))
        for path in SCHEMAS_DIR.glob("*/*.schema.json")
    }
    assert frozen
    assert frozen <= _materializable()


def test_bronze_tables_are_listed_once_per_sport() -> None:
    for sport in ("basketball", "football"):
        tables = [t for (s, _), group in BRONZE_TABLES.items() if s == sport for t in group]
        assert len(tables) == len(set(tables)), sport


def test_schema_in_code_tables_match_their_builder() -> None:
    modules = {
        ("basketball", "meta"): tracklab.bronze.basketball.meta,
        ("basketball", "tracking"): tracklab.bronze.basketball.tracking,
        ("football", "meta"): tracklab.bronze.football.meta,
        ("football", "tracking"): tracklab.bronze.football.tracking,
    }
    for group, module in modules.items():
        assert set(BRONZE_TABLES[group]) == set(module.TABLES), group


def test_the_build_job_runs_every_asset() -> None:
    job = defs.resolve_job_def("build")
    assert set(job.asset_layer.executable_asset_keys) == _materializable()


def test_every_job_runs_the_dbt_steps_one_at_a_time() -> None:
    """The implicit job (`dagster asset materialize`, `dagster dev`) shares DuckDB too."""
    jobs = {
        "implicit": defs.resolve_implicit_global_asset_job_def(),
        "build": defs.resolve_job_def("build"),
    }
    for name, job in jobs.items():
        resolved = job.executor_def.config_schema.resolve_config({})  # type: ignore[attr-defined]
        assert resolved.success, name
        limits = resolved.value["config"]["tag_concurrency_limits"]
        assert limits == [{"key": "tracklab/duckdb", "value": "dbt", "limit": 1}], name


RUNS_ASSETS = {"runs_protocol", "runs_coverage", "runs_probe", "runs_effect", "publish_runs"}


def test_the_runs_group_holds_the_five_p5_assets() -> None:
    graph = defs.resolve_asset_graph()
    in_group = {
        k.to_user_string() for k in graph.get_all_asset_keys() if graph.get(k).group_name == "runs"
    }
    assert in_group == RUNS_ASSETS


def test_the_runs_assets_only_check_and_fail_when_the_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P5 is dead with its protocol in `design`: an asset that wrote would move `head` and
    `code_tree_sha` and then compare the file with itself. Each calls its command with
    `check=True`, and a non-zero exit fails the asset."""
    seen: dict[str, bool] = {}
    exit_code = {"value": 0}

    def fake(name: str):  # type: ignore[no-untyped-def]
        def run(*args: object, check: bool = False) -> int:
            seen[name] = check
            return exit_code["value"]

        return run

    for attr in (
        "run_runs_protocol",
        "run_runs_coverage",
        "run_runs_probe",
        "run_runs_effect",
        "run_publish_runs",
    ):
        monkeypatch.setattr(assets_runs, attr, fake(attr))

    assert materialize(assets_runs.runs_assets).success
    assert seen == dict.fromkeys(
        (
            "run_runs_protocol",
            "run_runs_coverage",
            "run_runs_probe",
            "run_runs_effect",
            "run_publish_runs",
        ),
        True,
    )

    exit_code["value"] = 1
    assert not materialize(assets_runs.runs_assets, raise_on_error=False).success


POSE_ASSETS = {"pose_coverage", "pose_protocol", "pose_metric", "publish_pose"}


def test_the_pose_group_holds_the_four_p6_assets() -> None:
    graph = defs.resolve_asset_graph()
    in_group = {
        k.to_user_string() for k in graph.get_all_asset_keys() if graph.get(k).group_name == "pose"
    }
    assert in_group == POSE_ASSETS


def test_the_pose_assets_only_check_and_fail_when_the_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Like the runs group: the metric and the publication read the confirmation match past a
    guard that refuses a dirty tree, so an asset that wrote would compare a file with itself.
    Each calls its command with `check=True`; a non-zero exit fails the asset."""
    seen: dict[str, bool] = {}
    exit_code = {"value": 0}

    def fake(name: str):  # type: ignore[no-untyped-def]
        def run(*args: object, check: bool = False) -> int:
            seen[name] = check
            return exit_code["value"]

        return run

    names = ("run_pose_coverage", "run_pose_protocol", "run_pose_metric", "run_publish_pose")
    for attr in names:
        monkeypatch.setattr(assets_pose, attr, fake(attr))

    assert materialize(assets_pose.pose_assets).success
    assert seen == dict.fromkeys(names, True)

    exit_code["value"] = 1
    assert not materialize(assets_pose.pose_assets, raise_on_error=False).success


def test_the_pose_checks_read_the_bronze_they_check() -> None:
    graph = defs.resolve_asset_graph()
    for name in POSE_ASSETS:
        parents = {k.to_user_string() for k in graph.get(AssetKey(name)).parent_keys}
        assert "bronze_football_bodypose_players" in parents, name
