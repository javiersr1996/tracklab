"""The Dagster graph is whole: no asset reads something nothing writes (task 15).

Needs dbt/target/manifest.json (`dbt parse` or `dbt build` first, as CI does).
The bronze tables are hand-listed per builder, so they are checked against the two
things that cannot drift silently: the frozen schemas and the dbt sources.
"""

from __future__ import annotations

from pathlib import Path

from dagster import AssetKey

import tracklab.bronze.basketball.meta
import tracklab.bronze.basketball.tracking
import tracklab.bronze.football.meta
import tracklab.bronze.football.tracking
from tracklab.dagster_defs import defs
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
