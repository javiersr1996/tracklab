"""The Dagster graph is whole: no asset reads something nothing writes (task 15).

Needs dbt/target/manifest.json (`dbt parse` or `dbt build` first, as CI does).
The bronze tables are hand-listed per builder, so they are checked against the two
things that cannot drift silently: the frozen schemas and the dbt sources.
"""

from __future__ import annotations

from pathlib import Path

from dagster import AssetKey

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
