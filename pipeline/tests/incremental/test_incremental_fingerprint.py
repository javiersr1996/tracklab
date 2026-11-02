"""Task 126: the fingerprint of each match's silver partitions, on a copy of the fixtures.

One test per class of input, each changing one file of a temporary copy and asserting which
matches move: a match's own bronze moves that match only, a season table every match of its sport,
an input no sport owns, the dbt project, the plugin or the engine every match. A second basketball
match (114244, the bytes of 114243 under another name) is there so that "every match of its sport"
and "that match only" are not the same assertion. Leaving any class out of the digest fails its
test (tasks/todo.md, task 126).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from tracklab.silver import dbt_plugin
from tracklab.silver.incremental import (
    Fingerprints,
    Inputs,
    engine_versions,
    fingerprints,
    silver_sources,
)

PIPELINE = Path(__file__).resolve().parents[2]
FIXTURES = PIPELINE / "tests" / "fixtures" / "data"
DBT_MANIFEST = PIPELINE / "dbt" / "target" / "manifest.json"
BB, BB2, FB = "basketball/114243", "basketball/114244", "football/1874553"
EVERY_MATCH = {BB, BB2, FB}


@pytest.fixture(scope="module")
def sources() -> list[tuple[str, str]]:
    return silver_sources(json.loads(DBT_MANIFEST.read_text(encoding="utf-8")))


@pytest.fixture
def inputs(tmp_path: Path) -> Inputs:
    data = tmp_path / "data"
    shutil.copytree(FIXTURES / "bronze", data / "bronze")
    for table in (data / "bronze" / "basketball").iterdir():
        if (table / "114243.parquet").is_file():
            shutil.copyfile(table / "114243.parquet", table / "114244.parquet")
    dbt = tmp_path / "dbt"
    for name in ("dbt_project.yml", "profiles.yml"):
        (dbt).mkdir(exist_ok=True)
        shutil.copyfile(PIPELINE / "dbt" / name, dbt / name)
    for folder in ("models", "macros", "seeds", "tests"):
        shutil.copytree(PIPELINE / "dbt" / folder, dbt / folder)
    (tmp_path / "reports").mkdir()
    shutil.copyfile(
        PIPELINE / "reports" / "orientation_basketball.csv",
        tmp_path / "reports" / "orientation_basketball.csv",
    )
    (tmp_path / "manifest").mkdir()
    shutil.copyfile(PIPELINE / "manifest" / "sources.json", tmp_path / "manifest" / "sources.json")
    plugin = tmp_path / "dbt_plugin.py"
    shutil.copyfile(dbt_plugin.__file__, plugin)
    return Inputs(data, tmp_path / "reports", tmp_path / "manifest", dbt, plugin, engine_versions())


def _touch(path: Path) -> None:
    """A change of content, whatever the file is."""
    with path.open("ab") as handle:
        handle.write(b"\n")


def _moved(before: Fingerprints, after: Fingerprints) -> set[str]:
    keys = set(before.matches) | set(after.matches)
    return {k for k in keys if before.matches.get(k) != after.matches.get(k)}


def _moved_by(sources: list[tuple[str, str]], inputs: Inputs, path: Path) -> set[str]:
    before = fingerprints(sources, inputs)
    _touch(path)
    return _moved(before, fingerprints(sources, inputs))


def test_silver_reads_the_tables_its_models_name_and_no_other(
    sources: list[tuple[str, str]],
) -> None:
    for wanted in (
        ("bronze_basketball", "tracking_objects"),
        ("bronze_basketball", "events_possessions"),
        ("bronze_basketball", "player_id_aliases"),
        ("bronze_football", "dynamic_events"),
        ("bronze_football", "match_periods"),
        ("bronze_common", "orientation"),
        ("reports", "orientation_basketball"),
        ("manifest", "sources"),
    ):
        assert wanted in sources
    tables = {table for _, table in sources}
    # gold's season aggregates, the pose, and what only the orientation probe reads.
    assert not tables & {"aggregates_shots", "aggregates_obr", "bodypose_players", "games"}
    assert ("bronze_football", "matches") not in sources


def test_every_match_with_a_per_match_file_has_a_fingerprint(
    sources: list[tuple[str, str]], inputs: Inputs
) -> None:
    assert set(fingerprints(sources, inputs).matches) == EVERY_MATCH


@pytest.mark.parametrize(
    ("relative", "match"),
    [
        ("basketball/tracking_objects/114243.parquet", BB),
        ("basketball/events_possessions/114243.parquet", BB),
        ("football/dynamic_events/1874553.parquet", FB),
        ("football/match_periods/1874553.parquet", FB),
    ],
)
def test_touching_one_match_changes_only_that_match(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str, match: str
) -> None:
    assert _moved_by(sources, inputs, inputs.data_dir / "bronze" / relative) == {match}


@pytest.mark.parametrize(
    "relative", ["basketball/matches/data.parquet", "basketball/player_id_aliases/data.parquet"]
)
def test_a_season_table_changes_every_match_of_its_sport(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str
) -> None:
    assert _moved_by(sources, inputs, inputs.data_dir / "bronze" / relative) == {BB, BB2}


@pytest.mark.parametrize(
    "relative",
    [
        "data/bronze/common/orientation/data.parquet",
        "reports/orientation_basketball.csv",
        "manifest/sources.json",
    ],
)
def test_an_input_no_sport_owns_changes_every_match(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str
) -> None:
    root = inputs.data_dir.parent
    assert _moved_by(sources, inputs, root / relative) == EVERY_MATCH


@pytest.mark.parametrize(
    "relative",
    [
        "models/silver/frames.sql",
        "models/silver/dim_entity.sql",
        "models/silver/schema.yml",
        "models/sources/football.yml",
        "macros/agg_long.sql",
        "seeds/event_type_map.csv",
        "tests/assert_frames_t_ms_increases.sql",
        "dbt_project.yml",
        "profiles.yml",
    ],
)
def test_the_dbt_project_changes_every_match(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str
) -> None:
    assert _moved_by(sources, inputs, inputs.dbt_dir / relative) == EVERY_MATCH


def test_the_dbt_plugin_changes_every_match(sources: list[tuple[str, str]], inputs: Inputs) -> None:
    assert _moved_by(sources, inputs, inputs.plugin) == EVERY_MATCH


@pytest.mark.parametrize("package", ["duckdb", "dbt-core", "dbt-adapters", "dbt-duckdb"])
def test_the_engine_changes_every_match(
    sources: list[tuple[str, str]], inputs: Inputs, package: str
) -> None:
    before = fingerprints(sources, inputs)
    upgraded = replace(inputs, engine={**inputs.engine, package: "999.0.0"})
    assert _moved(before, fingerprints(sources, upgraded)) == EVERY_MATCH


@pytest.mark.parametrize(
    "relative",
    [
        "data/bronze/basketball/aggregates_shots/data.parquet",
        "data/bronze/basketball/games/114243.parquet",
        "data/bronze/football/bodypose_players/1925299.parquet",
        "data/bronze/football/matches/data.parquet",
        "dbt/models/gold/agg_bb_shots.sql",
    ],
)
def test_what_silver_does_not_read_changes_nothing(
    sources: list[tuple[str, str]], inputs: Inputs, relative: str
) -> None:
    assert _moved_by(sources, inputs, inputs.data_dir.parent / relative) == set()


def test_a_source_of_an_unknown_family_fails(inputs: Inputs) -> None:
    with pytest.raises(ValueError, match="'elsewhere'"):
        fingerprints([("elsewhere", "table")], inputs)
